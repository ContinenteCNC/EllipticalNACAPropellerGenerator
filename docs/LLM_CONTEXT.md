# LLM maintainer context

## Project identity

- Name: Elliptical NACA Propeller Generator
- Version: 1.0.0
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
- `propeller_defaults.json`: immutable distributed defaults.
- external `propeller_user_config.json`: last validated user settings.
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
initial: 460 x 620 px
minimum: 360 x 400 px
```

to the v0.19 compact width, then v0.21 reduced the height:

```text
initial: 360 x 500 px
minimum: 300 x 300 px
```

Do not restore the former width or height without a specific usability reason.
Restore Factory Defaults is deliberately the first full-width control. Generate automatically saves validated settings to the external user JSON. The native OK button is
localized as Generate.

Version 0.21 intentionally relies on Fusion's normal persistence of user-resized dialogs after establishing a safe 460 x 620 px initial size.

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


## Version 0.21 dialog organization

The visible groups are deliberately ordered as:

```text
Restore factory defaults
Propeller Geometry
Airfoil Profiles
Hub
Resolution
Tip Ring
Spinner
Display and Diagnostics
Advanced Construction
```

The JSON schema remains backward compatible. The GUI maps one Tip Ring
checkbox/type selector back to `Hoop` or `Airfoil_Ring`, and one Spinner
checkbox/type selector back to `Parabolic_Spinner_Yes` or
`Ogive_Spinner_Yes`. Only one type in each family can be generated per run.

When loading an older JSON that enables both types in a family, the first
legacy type is selected: rectangular ring for Tip Ring and parabolic for
Spinner.


## Version 0.21 configuration persistence

Configuration is layered:

```text
propeller_defaults.json
-> external propeller_user_config.json
-> legacy propeller_config.json only during migration
```

Generate validates and resolves the radial distribution, writes the user
configuration atomically, then begins B-Rep construction. A later geometry
failure therefore does not discard the parameter set being diagnosed.

The restore button applies factory values to every current command input and
deletes both the external user file and any legacy in-package override.

## Version 0.21 timeline grouping

Do not create TimelineGroups inside `Command.execute`. Features created there
are still inside the command transaction and may not yet appear in
`Timeline.count`.

Capture the starting index before geometry, queue the result, and create the
group from the global `UserInterface.commandTerminated` handler. Only after
that should the result message be displayed. Every unavailable or failed
grouping path must be reported; never return silently.

The visible command name is `<localized name> — v1.0.0`.

For timeline grouping, never use truthiness checks on `Design`, `Timeline`, or `TimelineGroup`. Use explicit `is None` and `isValid` checks so a valid empty timeline is not mistaken for a missing one.

## Version 0.21 active component

All generated geometry uses `Design.activeComponent`, never an unconditional
`Design.rootComponent`. Resolve the active component once, validate it, and
pass the same component through every geometry operation.

## Version 0.21 nested-component paths

Do not use static `adsk.fusion.Path.create` for the wrapped section curves.
Use `component.features.createPath(curves, False)` so sketch curves created in
an active child component retain their owning component context.

Before calling `TimelineGroups.add`, require at least two newly committed
timeline items. A single partial sketch cannot form a standard timeline group.


## Version 1.0 release status

Version 1.0.0 is a release-only promotion of the Fusion-tested v0.21.0
implementation. It must not contain intentional geometry or parameter changes.

The next planned feature lines are documented in `docs/ROADMAP.md`:

- v1.1: adaptive radial section distribution based on normalized geometric
  variation and bounded minimum/maximum spacing;
- v1.2: a sample-configuration library and GUI loader.
