# LLM maintainer context

## Project identity

- Name: Elliptical NACA Propeller Generator
- Version: 0.20.0
- Previous development name: `PropellerFlatSections`
- Fusion add-in UUID: `e9d0f388-6b7d-4fb7-88fb-cdbba6743fd6`
- Maintainer: Bruno Martins
- Upstream source: Alex Matulich's / Amatulic's Thingiverse OpenSCAD library.
- Main goal: reproduce that parametric propeller as native smooth Autodesk
  Fusion B-Rep geometry and provide a complete user-facing generator.

## Current verified status

Confirmed in Fusion:

- flat and wrapped section generation;
- 3D wrapped sections;
- surface loft;
- root/tip extension;
- exact cylindrical trimming;
- stitch to a valid blade solid;
- base cut;
- blade pattern;
- hub and shaft hole;
- corrected Sweep_Angle behavior by overlay;
- parabolic spinner;
- ogive spinner;
- saved JSON defaults;
- multilingual GUI.

The user visually confirmed both spinner modes. Hoop geometry follows its
documented dimensions; keep the join fallback because offsets can intentionally
prevent contact.

## Upstream versus port additions

The Thingiverse library supplies the blade equations, the two spinner
modules, and an aerodynamic NACA ring example inside `demo_random()`. This Fusion project adds the GUI, persistence, B-Rep pipeline, final
hub, shaft hole, peripheral hoop and automated assembly.

The uppercase JSON names are the public names of this Fusion project.
`propeller_math.py` documents their mapping to the lowercase upstream
`propblade()` arguments.

## Core files

- `EllipticalNACAPropellerGenerator.py`: all Autodesk Fusion API work.
- `propeller_math.py`: upstream equations and section coordinates.
- `localization.py`: language selection and fallback.
- `propeller_config.json`: editable defaults.
- `locales/*.json`: translated strings.

## Non-negotiable conventions

1. Math uses millimetres; Fusion uses centimetres.
2. `propeller_math.py` must not import `adsk`.
3. `Root_Length` and `Hub_Length` are different concepts.
4. Keep the negative sign in the Fusion Sweep_Angle conversion.
5. Automatic section generation must include root, transition and tip exactly.
6. Do not trust B-Rep result ordering.
7. Use `isLightBulbOn`, not assignment to read-only `isVisible`.
8. Retain event handlers in `_handlers`.
9. Add every localization key to all six locale files.
10. Keep the dialog intentionally narrow; users can enlarge it manually.
11. A geometry change is not verified until tested in Fusion; OpenSCAD overlay
    is the preferred equivalence test.

## Dialog sizing

Version 0.19 intentionally changed the dialog from:

```text
initial: 980 x 900 px
minimum: 820 x 720 px
```

to:

```text
initial: 360 x 900 px
minimum: 300 x 720 px
```

Do not restore the former width without a specific usability reason.

## Construction order

```text
section math
-> wrapped 3D splines
-> surface loft
-> root/tip extension
-> cylindrical caps and trims
-> stitch to one blade solid
-> cut below Z=0
-> Prop_Z_Offset
-> circular pattern
-> hub
-> hoop
-> spinner(s)
-> combine joins
```

## Typical extension workflow

1. Add pure equations to `propeller_math.py` when possible.
2. Add Fusion construction in the main module.
3. Add configuration keys and GUI inputs.
4. Add six translations.
5. Extend result reporting without making optional failures fatal.
6. Update architecture, geometry and this context file.
7. Run local static validation.
8. Test in Fusion.
9. Compare with the original SCAD output when implementing upstream behavior.

## Licensing context

The supplied Thingiverse ZIP states `Creative Commons - Attribution`, but its
bundled notice does not identify a version. Preserve attribution to Alex
Matulich / Amatulic and do not describe the entire repository as exclusively
MIT. Read `LICENSE`, `ATTRIBUTION.md` and `UPSTREAM_LICENSE.txt`.


## Aerodynamic ring implementation

`Airfoil_Ring` is distinct from the rectangular `Hoop`.

The ring contour is produced in `propeller_math.airfoil_ring_profile_points()`
using the exact upstream orientation:

```text
NACA_profile(..., origin=1, dir=1)
-> rotate -90 degrees
-> translate to reference radius
-> revolve 360 degrees
```

The reference diameter locates the airfoil chord/reference line, not the
outer diameter. Airfoil thickness extends both inward and outward.

When `Airfoil_Ring_Chord == 0`, resolve:

```text
min(20, 0.5 * Propeller_Diameter * Max_Chord_Fraction)
```
