# Elliptical NACA Propeller Generator

[English](README.md) | [Português do Brasil](README.pt-BR.md)


A multilingual Autodesk Fusion add-in for generating complete parametric
propellers with elliptical blade planforms and smoothly transitioning NACA
4-digit airfoils.

Current release: **v0.21.0**

## Features

- One to twelve blades with clockwise or counter-clockwise geometry.
- Constant geometric pitch and configurable blade sweep.
- Ellipse-constrained chord distribution.
- Independent root, mid and tip NACA 4-digit profiles.
- Smooth nonlinear airfoil transitions and configurable root fairing.
- Finite trailing-edge thickness intended for manufacturable geometry.
- Automatic radial sections by spacing or slice count.
- Native Fusion surface loft, exact radial trims and stitched B-Rep solid.
- Hub, shaft hole, rectangular hoop, aerodynamic NACA ring, and optional parabolic or ogive spinner.
- Portuguese, English, Spanish, French, German and Russian interface.
- Save-current-parameters button backed by an atomic JSON write.
- Compact dialog using collapsible groups.

## Installation

Copy the complete `EllipticalNACAPropellerGenerator` folder to the Autodesk
Fusion add-ins directory, then restart Fusion.

Windows:

```text
%appdata%\Autodesk\Autodesk Fusion\API\AddIns
```

macOS:

```text
~/Library/Application Support/Autodesk/Autodesk Fusion/API/AddIns
```

The folder, Python entry file and manifest share the same base name:

```text
EllipticalNACAPropellerGenerator/
├── EllipticalNACAPropellerGenerator.py
└── EllipticalNACAPropellerGenerator.manifest
```

## Original project

The blade and spinner mathematics are derived from:

**Elliptical-blade NACA airfoil propeller library**  
Alex Matulich / Amatulic  
https://www.thingiverse.com/thing:5300828

The original author explains the design approach in:

https://www.nablu.com/2022/03/elliptical-blade-naca-airfoil-propeller.html

See [ATTRIBUTION.md](ATTRIBUTION.md),
[UPSTREAM_LICENSE.txt](UPSTREAM_LICENSE.txt) and
[docs/SOURCE_LINEAGE.md](docs/SOURCE_LINEAGE.md).

## Changes made in this port

The original OpenSCAD library creates faceted blade polyhedra and provides
parabolic and ogive spinner modules. This project reimplements the equations
in Python and adds a complete Autodesk Fusion workflow:

- smooth native B-Rep geometry;
- graphical and multilingual parameter interface;
- JSON presets;
- radial trimming and solid verification;
- blade pattern, hub and shaft hole;
- optional peripheral hoop;
- automatic spinner assembly.

Direct overlay tests showed that the OpenSCAD mesh vertices coincide with or
are tangent to the Fusion loft. Pitch, section profiles and sweep direction
were separately confirmed.

## Repository map

- `EllipticalNACAPropellerGenerator.py`: Fusion API adapter and construction.
- `propeller_math.py`: pure Python implementation of the upstream equations.
- `localization.py` and `locales/`: interface localization.
- `propeller_defaults.json`: immutable factory defaults.
- `docs/GEOMETRY.md`: equations and coordinate conventions.
- `docs/FUSION_API_PIPELINE.md`: B-Rep construction sequence.
- `docs/LLM_CONTEXT.md`: compact maintainer context for humans and LLMs.

## Licensing

The repository combines original Python/Fusion implementation work with
adapted geometry and equations. The MIT grant in [LICENSE](LICENSE) applies
only to original contributions owned by this project. The upstream material
retains its Creative Commons attribution requirements. Read
[ATTRIBUTION.md](ATTRIBUTION.md) and
[UPSTREAM_LICENSE.txt](UPSTREAM_LICENSE.txt) together with the main license.


## Aerodynamic NACA ring

Version 0.20 formalizes the airfoil ring demonstrated inside the original
Thingiverse `demo_random()` module.

The upstream construction uses a NACA 0015 section by default, places its
trailing-edge reference line at the propeller-tip radius, rotates the section
so chord is axial, and revolves it 360 degrees around the shaft.

Parameters:

```text
Airfoil_Ring
Airfoil_Ring_NACA
Airfoil_Ring_Chord
Airfoil_Ring_Diameter
Airfoil_Ring_Axial_Offset
Airfoil_Ring_TE_Thickness
Airfoil_Ring_Profile_Points
```

A chord of zero enables the original automatic expression:

```text
min(20 mm, 0.5 * Propeller_Diameter * Max_Chord_Fraction)
```

The existing rectangular `Hoop` remains available as a separate feature.


### Interface organization

The command groups related parameters by purpose. Tip-ring and spinner
families each use one enable checkbox and one type selector, preventing
overlapping alternatives from being generated in the same run. Existing JSON
parameter names remain compatible.


### Automatic parameter persistence

Every validated parameter is saved automatically when **Generate** is pressed,
before Fusion starts constructing geometry. The immutable factory values remain
in `propeller_defaults.json`.

The last user configuration is stored outside the repository and add-in
installation:

```text
Windows: %APPDATA%\EllipticalNACAPropellerGenerator\propeller_user_config.json
macOS:   ~/Library/Application Support/EllipticalNACAPropellerGenerator/propeller_user_config.json
```

Use **Restore factory defaults** to reload the distributed values and remove
the saved user configuration. Restoring defaults does not generate geometry.

### Timeline organization

In parametric designs, each generation run is grouped only after Fusion fires
the global `commandTerminated` event, when the command transaction has ended
and its new timeline items are available. Groups are collapsed and named
sequentially:

```text
Elliptical NACA Propeller 01
Elliptical NACA Propeller 02
...
```

The final generation message is also delayed until this post-commit step, so it
always reports whether grouping succeeded, failed, or was intentionally
skipped. The visible command name includes the current version.

Timeline API objects are checked explicitly with `is None` and `isValid`, so a valid empty timeline on the first run is accepted.

### Active component

Geometry is created in the component currently activated in Fusion. When the
root component is active, the propeller is created there. When a child
component is active, all sketches, features, bodies, hub, rings, and spinners
are created in that component definition. The result dialog reports the target
component name.

### Nested-component section paths

Wrapped section paths are created with the active component's
`Features.createPath` method. This preserves the component/assembly context of
3D sketch curves owned by nested components.

If a failed run commits only one timeline item, no standard timeline group is
attempted because Fusion requires at least two items. The final message reports
that condition without an additional API traceback.
