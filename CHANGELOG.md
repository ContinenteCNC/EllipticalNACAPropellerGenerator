# Changelog

## 1.1.2 — 2026-07-19

- Added `examples/Examples.f3d`, an Autodesk Fusion document containing the models generated from all bundled configurations.
- Added `examples/README.md` to clarify that the Fusion document is an optional reference and is not required for add-in execution.
- Moved the generated examples document out of the repository root into the dedicated `examples/` directory.
- No geometry-generation behavior or configuration values changed in this maintenance release.

## 1.1.1 — 2026-07-19

- Moved the `flipped_180` orientation so it acts on the first blade immediately after Boundary Fill, before patterning and before hub/spinner creation, matching `demo_boatpropblades()`.
- Set `Hub_Length = 25.0 mm` in `03_toy_boat_propeller.json` so the hub blends cleanly with the blade roots.

- Added `Propeller_Orientation` with backward-compatible `standard` and
  `flipped_180` values. The flipped mode reproduces
  `translate([0,0,Root_Length]) rotate([180,0,0])` from
  `demo_boatpropblades()` without changing `Prop_Direction`, `Sweep_Angle`,
  pitch, or blade-generation equations.
- Updated every bundled configuration to include the orientation field; only
  Toy Boat Propeller uses `flipped_180`.
- Increased the default and bundled Stitch tolerance from 0.01 mm to 0.1 mm
  after successful validation across all examples.
- Split manual diagnostics into main-surface loft, trailing-edge loft, XY Trim,
  and surface Stitch failures while preserving partial Fusion features.

## 1.1.0 — 2026-07-18

- Delivered a major stability improvement to native Fusion lofting and solid
  finalization.
- Validated the split trailing-edge workflow on all five bundled examples with
  root-to-tip order, no main-surface guides, and `0.1 mm` Boundary Fill
  diameter overlap.
- Lofted the open NACA surface separately from the trailing-edge closure; the
  trailing-edge loft always uses two rails through the exact vertices.
- Added pre-Stitch XY trimming of both source surfaces and included the XY plane
  in Boundary Fill whenever base cutting is requested.
- Corrected parabolic and ogive spinner placement to start at `Z = Hub_Length`.
- Restored Fusion's native Generate/OK lifecycle: each run closes and commits
  the command before timeline grouping and result display, preventing visibility
  changes and timeline groups from being reverted on a later Close action.
- Kept real-time manual viewport/timeline updates through named `adsk.doEvents()`
  checkpoints and bounded progress-message width to prevent late dialog growth.
- Renamed the library and filesystem folders to **Configurations** /
  `configurations/`, expanded it by default, added persistent user-created
  configurations with immediate refresh, and migrated legacy user `samples/`
  JSON files without overwriting.
- Removed Restore Factory Defaults and added its original 3 × 1.25-inch values
  as a built-in configuration.
- Added a separate cancelable manual progress dialog with current-stage text;
  Automatic robust keeps its independent legacy/research dialog.
- Added detailed manual-run JSON logs containing the complete parameter JSON,
  generator/Fusion/runtime versions, resolved radii, raw result fields, the
  substantive final-screen text, timings, cancellations, and errors.
- Audited all 67 real GUI parameters against JSON serialization; UI-only
  controls remain intentionally excluded.
- Expanded the Configurations group by default.
- Standardized factory defaults and all bundled examples on split trailing
  edge, root-to-tip, no main guides, and `0.1 mm` Boundary Fill overlap.
- Added robust-search fallback selection, reusable preflight sections, regional
  root-transition quality handling, a true 15-attempt cap, and transient Path
  recreation to avoid stale `pathEnt` errors.
- Preserved closed-profile, reverse-order, guide-rail, and legacy finalization
  paths as advanced compatibility options.

## 1.0.0

First public stable release.

- Promoted the fully tested v0.21.0 implementation to v1.0.0.
- No intended change to propeller mathematics, geometry, parameters, or JSON
  keys relative to the tested v0.21.0 build.
- Generates complete propellers in the currently active Fusion component.
- Creates wrapped section paths with the owning component context, including
  nested child components.
- Organizes each successful parametric run in a collapsed, sequential timeline
  group after the Fusion command transaction is committed.
- Supports automatic radial section distribution by spacing or slice count,
  plus manual section radii.
- Includes root, mid, and tip NACA profiles, sweep, hub, shaft hole, tip-ring
  alternatives, and parabolic or rounded-ogive spinner alternatives.
- Saves validated parameters automatically and restores immutable factory
  defaults on request.
- Provides a localized interface in Portuguese, English, Spanish, French,
  German, and Russian.
- Includes public documentation, source attribution, licensing notices,
  release notes, and a post-1.0 roadmap.

## 0.21.0

- Adjusted and reorganized the command interface while keeping the established
  460 × 620 px default and 360 × 400 px minimum dimensions.
- Combined tip-ring and spinner alternatives under mutually exclusive type
  selectors.
- Renamed the native **OK** button to **Generate** in all six languages.
- Split configuration into immutable `propeller_defaults.json` and an external
  per-user `propeller_user_config.json`.
- Automatically saves every validated parameter when **Generate** is pressed,
  before B-Rep construction begins.
- Replaced the manual Save Defaults action with **Restore factory defaults**.
- Restoring defaults updates every dialog input and removes current and legacy
  user overrides without generating geometry.
- Added migration support for legacy `propeller_config.json` files.
- Preserved the existing JSON parameter keys and geometry pipeline.
  marker is not at the end.
- Defers timeline grouping to the global `commandTerminated` event so the
  command transaction is committed before timeline indices are inspected.
- Delays the final result dialog until grouping completes and explicitly
  reports every success, failure, and intentional skip path.
- Creates collapsed sequential groups for committed runs and marks committed
  partial runs with `(incomplete)`.
- Displays `v0.21.0` in the visible localized command name.
- Fixed first-run timeline detection: a valid timeline with zero existing items is no longer mistaken for an unavailable timeline.
- Creates all geometry in Fusion's currently active component instead of always using the root component, and reports the target component in the result dialog.
- Creates wrapped-section Paths through the active component's `Features.createPath` collection, preserving nested-component context.
- Avoids calling `TimelineGroups.add` for a one-item partial run and reports the minimum-two-items condition explicitly.

## 0.20.0

- Added a native revolved aerodynamic ring based on the original
  Thingiverse `demo_random()` airfoil-ring example.
- Added configurable NACA code, chord, reference diameter, axial offset,
  physical trailing-edge thickness and profile resolution.
- Added the original automatic ring-chord expression when chord is zero.
- Preserved the rectangular Hoop as an independent alternative.
- Added six-language GUI, JSON persistence and partial-success reporting for
  the aerodynamic ring.

## 0.19.0

- Reframed the public source lineage directly around Alex Matulich's /
  Amatulic's original Thingiverse project.
- Removed all references to intermediate distribution sites and adaptations
  from source comments and repository documentation.
- Added the exact archived Thingiverse licensing notice as
  `UPSTREAM_LICENSE.txt`.
- Reduced dialog width from 980/820 px to 360/300 px while preserving the
  previous heights.
- Added named dialog-size constants and maintenance comments.
- No intended geometry or parameter behavior change from v0.18.

## 0.18.0

- Renamed the project to **Elliptical NACA Propeller Generator**.
- Renamed the add-in folder, Python entry file and manifest.
- Updated localized command names and descriptions.
- Added source-lineage and licensing notices.
- Added maintainer comments and module documentation.
- Added GitHub documentation for architecture, geometry, Fusion pipeline and
  LLM-assisted maintenance.
- No intended geometry change from v0.17.

## 0.17.0

- Added atomic saving of current GUI parameters to JSON.
- Reorganized the dialog using progressive disclosure.

## 0.16.1

- Replaced read-only `isVisible` assignments with `isLightBulbOn`.

## 0.16.0

- Added parabolic and rounded-ogive spinners with partial shaft holes.

## 0.15.0

- Added the optional peripheral hoop.

## 0.14.0

- Corrected the Sweep_Angle sign using a direct SCAD/Fusion overlay.
- Added original SCAD variable names to translated GUI labels.

## 0.13.0

- Added initial Sweep_Angle support.

## 0.12.0

- Added automatic localization in six languages.

## 0.11.0

- Added automatic radial sections by spacing and slice count.

## 0.10.0

- Added printable base cut, axial offset, circular blade pattern, hub, shaft
  hole and final solid assembly.

## 0.9.0

- Added the grouped parameter dialog, editable NACA codes and JSON defaults.

## 0.8.0

- Automated trims, stitching and blade-solid verification.

## 0.7.0–0.7.1

- Added surface-end extensions and analytical limit cylinders.
- Fixed a missing math import.

## 0.6.0

- Added automatic surface loft generation.

## 0.5.0

- Added wrapped 3D section sketches.

## 0.1.0–0.4.0

- Established Fusion command integration, root-component creation, section
  orientation and pitch-sign equivalence.
### Robust preflight regional-quality update (2026-07-18)

- Separates quality samples into the root-fairing and aerodynamic regions.
- Accepts a finalizable candidate immediately when all sampled aerodynamic stations meet the strict targets and only the root fairing exceeds them.
- Keeps root-fairing deviations visible as warnings and in schema-3 JSON/TXT logs.
- Ranks fallbacks primarily by aerodynamic-region fidelity.
- Includes one-time shared-section construction in the first candidate elapsed time.

