# Elliptical NACA Propeller Generator

A multilingual Autodesk Fusion add-in for generating complete parametric
propellers with elliptical blade planforms and smoothly transitioning NACA
4-digit airfoils.

Current release: **v0.20.0**

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
- `propeller_config.json`: persisted defaults.
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
