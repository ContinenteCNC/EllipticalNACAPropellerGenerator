# LLM maintainer context

## Project identity

- Name: Elliptical NACA Propeller Generator
- Version: 1.1.0
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
The former Restore Factory Defaults control was removed; its values are available as the built-in 3 × 1.25-inch original configuration. Generate automatically saves validated settings to the external user JSON. The native OK button is
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
Load the built-in original 3 × 1.25-inch configuration
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

## Version 0.21 timeline grouping

Do not create TimelineGroups inside `Command.execute`. Features created there
are still inside the command transaction and may not yet appear in
`Timeline.count`.

Capture the starting index before geometry and queue the result. In v1.1 the
native Generate/OK action terminates the command. The global
`UserInterface.commandTerminated` handler is the primary post-commit step and
flushes the queued result only after Fusion has committed the transaction. Never
flush while the command remains active: later termination can otherwise revert
visibility changes and delete the timeline group. Every unavailable or failed
grouping path must be reported; never return silently.

The visible command name is `<localized name> — v1.1.0`.

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

The next planned feature lines are documented in `docs/ROADMAP.md`. Adaptive
radial distribution and more advanced configuration schema management remain future
work after the v1.1 split-trailing-edge release.

## Version 1.1 configurations

Both the bundled `configurations/` directory and the per-user `configurations/` directory are scanned recursively each time the command opens. Legacy per-user `samples/` JSON files are copied into the new directory without overwriting. The GUI can save a complete current configuration as a user configuration and refresh the open list.
Every syntactically valid JSON object appears automatically; no hard-coded
configuration list exists.

Supported forms:

- metadata wrapper with `Parameters`;
- ordinary flat configuration JSON.

Configuration loading updates the GUI only. `_dialog_config_base` holds the loaded
factory-plus-configuration state so Cancel does not persist it and Generate does.
`Interface_Language` is always preserved from the current user context.

The five bundled design configurations are adaptations of the original OpenSCAD
`demo_collection()` configurations.
## v1.1 configuration-discovery pitfall

`_discover_sample_configurations()` uses `Path(relative_path).stem`; `from pathlib import Path` is mandatory. The initial v1.1 package omitted this import, causing every JSON configuration to be caught and reported as invalid.


## Manual progress and logging in v1.1

Manual wrapped runs use a dedicated `_ManualProgressController`; Automatic
robust uses only `_RobustProgressController`, so the dialogs never overlap.
Cancellation is cooperative at named geometry checkpoints and commits partial
manual features for inspection. Manual logs include `generator_version`, Fusion
and Python/platform runtime, the complete parameter JSON, resolved radii, raw
result fields, errors, and the exact final displayed message after timeline
grouping.

## Version 1.1 loft controls

The default loft order is root-to-tip. The Computer Cooling Fan test confirmed
that root-to-tip converges while tip-to-root self-intersects after several
sections.

Public configuration keys:

- `Loft_Section_Order`: `root_to_tip`, `tip_to_root`, or `automatic`;
- `Loft_Guide_Rails`: `none` or `dual_trailing_edge`;
- `Loft_Merge_Tangent_Edges`: boolean.

Automatic robust mode creates a new LoftFeatureInput for each attempt. Dual
trailing-edge rails are based on the first and last points of each generated
NACA section, corresponding to the upper and lower trailing-edge endpoints.

## v1.1.0 Boundary Fill experiment

Boundary Fill is the default solid finalizer. Public keys are
`Blade_Finalization_Method` (`boundary_fill` or `legacy`) and
`Boundary_Fill_Diameter_Overlap_mm` (validated default `0.1`). The implementation
selects the largest positive-volume Boundary Fill cell; seed-point containment
is reserved as a future stronger selector. The old extend/trim/stitch code is
retained as the legacy method.

## Distributed rails and current test policy

Public loft keys:

```json
{
  "Loft_Section_Order": "root_to_tip",
  "Loft_Guide_Rails": "distributed",
  "Loft_Distributed_Rail_Count": 9,
  "Loft_Distributed_Rails_Use_TE_Vertices": false,
  "Loft_Merge_Tangent_Edges": true
}
```

`Loft_Guide_Rails` accepts `none`, `distributed`, and
`dual_trailing_edge` for the main surface. The validated split construction
uses `none` for the main surface. Independently, the separate trailing-edge
loft always uses its own two exact-vertex rails; those rails are part of the
validated v1.1 workflow.

Distributed counts are odd and at least three. For N points per surface:

- unchecked/default: anchors `1`, `N`, `2N-1`; maximum `2N-1`;
- checked: anchors `0`, `N`, `2N`; maximum `2N+1`.

Additional rails are inserted in symmetric upper/lower pairs. Automatic robust
mode uses no rails followed by `3 -> 5 -> 7 -> 9 -> ... -> requested`. Legacy even saved
values are normalized downward, e.g. `10 -> 9`.

Boundary Fill uses:

```json
"Boundary_Fill_Diameter_Overlap_mm": 0.1
```

The largest positive-volume cell remains the current selector; seed-point
containment is reserved as the stronger future selector.

Generated spacing/slice distributions do not force the exact transition
radius. Preserve Mid_NACA interpolation independently of station placement.

## Automatic robust surface-quality search

Current persistent keys:

```json
{
  "Loft_Quality_Check": true,
  "Loft_Quality_Max_Deviation_Percent": 0.1
}
```

Automatic robust is a preflight, not merely a sequence inside
`_create_surface_loft`. Temporary child components isolate each candidate and
are deleted after evaluation. Rails increase `0, 3, 5, 7...` to the selected
maximum. The first loft that both converges and passes the worst-local-error
criterion proceeds to Boundary Fill overlap retries. Overlap multiplies by ten
from the configured value through at most 0.1 mm diameter.

Surface quality samples all interior interval midpoints and refines the three
worst intervals at 25%/75%. It projects up to 25 theoretical NACA contour points
onto bounded loft faces. Decision uses maximum percent of local chord; do not
replace it with RMS alone because user tests produced a loft with only half the
blade visibly wavy.

The default 0.1% threshold is temporary and must be recalibrated from Fusion
runtime results. Fusion runtime behavior cannot be validated by static tests.

## Fusion 2026 design-intent compatibility

Do not unconditionally call `parent_component.occurrences.addNewComponent`
during a command. A Part Design supports only one component.

Current robust isolation:

```text
Hybrid Design   -> disposable hidden child component
Part/Assembly   -> active-component entity-token snapshot and cleanup
```

Tracked collections are sketches, loft features, extrude features, Boundary
Fill features, and B-Rep bodies. Cleanup order is Boundary Fill -> extrudes ->
loft -> sketches -> orphan bodies. Any remaining candidate entity is a hard
failure.

## Current robust loft policy

```json
{
  "Loft_Distributed_Rail_Placement": "uniform_chord",
  "Loft_Distributed_Rail_Count": 9,
  "Loft_Quality_Max_Deviation_Percent": 0.1,
  "Loft_Quality_Max_Wave_Angle_Deg": 0.2
}
```

Automatic robust searches at least through nine rails when possible. Never use
RMS alone for acceptance; the global worst positional and angular values decide.

## Robust cancellation and logs

Automatic robust now always creates a progress dialog and attempts to save
JSON/TXT diagnostics in `USER_CONFIG_DIRECTORY/robust_search_logs`.

Cancellation is cooperative. Preserve these invariants:

1. `_RobustSearchCancelledSignal` must propagate through loft, quality, and
   Boundary Fill exception handlers.
2. Candidate cleanup must run in `finally`.
3. A cancelled partial attempt must be included in the saved session.
4. Log-write failure must not invalidate an otherwise accepted strategy.
5. Full logs keep all attempts; the result dialog may cap its compact summary.

## Progress UI invariants

- Dialog localization must contain real newline characters.
- Never send full kernel exceptions to `ProgressDialog.message`.
- Progress counts loft strategies, not overlap executions.
- Unexpected closure after the dialog was shown means cancellation.
- JSON/TXT logs retain complete errors and all overlap executions.

## Version 1.1 final release state

The validated manual default is split trailing-edge construction, root-to-tip,
no main-surface guides, and 0.1 mm Boundary Fill diameter overlap. The main
open NACA surface and trailing-edge surface are lofted separately; the latter
uses two exact-vertex rails. When base cutting is enabled, both surfaces are
trimmed by XY before Stitch, and Boundary Fill includes XY with the stitched
shell and both limit cylinders.

The command uses Fusion's native Generate/OK lifecycle and terminates after
each run. Manual checkpoints call `adsk.doEvents()` for real-time progress, but
progress messages must remain bounded in width. All real GUI parameters
serialize to the per-user last-run JSON. User configurations and detailed
manual-generation JSON logs are stored outside the add-in installation.
