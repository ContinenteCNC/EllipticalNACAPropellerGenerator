# Changelog

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

## 1.1 development history

### Robust preflight regional margin update

- Added a configurable post-fairing quality-tolerance margin, defaulting to 2× Fairing Size.
- The strict aerodynamic quality region now begins after the fairing plus this margin.
- Capped actual robust attempts at 15, including overlap retries.
- Recreates Fusion Path wrappers for every candidate to avoid `InternalValidationError: pathEnt` after cleanup.


## Unreleased — robust preflight refinement
- Separated strict quality acceptance from geometric validity and finalization.
  A candidate that creates a valid loft and completes Boundary Fill is now kept
  as a valid fallback even when it misses the configured fidelity targets.
- Automatic robust now selects the best finalizable fallback when no candidate
  passes every strict target, instead of reporting a complete failure while the
  equivalent manual loft is usable.
- Preserved strict candidates as the first priority, so configurations such as
  Computer Cooling Fan can still progress from 3 to 5 to 7 rails until the
  configured deviation targets are met.
- Reused wrapped section sketches across robust candidates with the same
  Boundary Fill overlap. Each attempt now rebuilds only guide rails, loft,
  cylinders, and Boundary Fill resources.
- Replaced the exhaustive 2 × 2 × N Cartesian search with an adaptive candidate
  plan. Equivalent zero-rail variants are skipped after a valid zero-rail loft,
  and higher rail counts are pruned after two consecutive self-intersection
  failures in the same strategy family.
- Added early tests of alternate distributed-rail placements before repeating
  broad direction and tangent-edge permutations.
- Corrected zero-rail strategy reporting so a selected no-guide loft remains
  rail count 0 instead of being recorded internally as 3.
- Renamed user-facing “wave angle” wording to “equivalent deviation angle” and
  clarified that it is derived from positional deviation and section spacing,
  not a direct curvature or zebra-stripe measurement.
- Expanded robust JSON/TXT diagnostics with strict/fallback status, section
  reuse, adaptive plan details, pruning policy, and selected fallback metadata.

## 1.1.0
- Replaced the default solid-blade finalization with Boundary Fill using the
  loft surface and nominal inner/outer cylindrical surfaces as tools.
- Root and tip sections receive a configurable infinitesimal diameter overlap
  (default 0.0001 mm) while aerodynamic calculations remain at nominal radii.
- Boundary Fill selects the positive-volume cell with the largest volume,
  records the two largest volumes, removes the tool bodies, and validates that
  exactly one solid was produced.
- Closed the trailing edge in the planar section before wrapping it, replacing
  the straight 3D chord with a fitted wrapped closing spline.
- Retained the previous extend/trim/stitch pipeline as an Advanced Construction
  legacy option.

- Fixed configuration discovery by importing `pathlib.Path`; all bundled and user-added valid JSON configurations are now detected instead of being reported as invalid.
- Added an automatically discovered example-configuration menu.
- Recursively scans every `.json` file under `configurations/` whenever the command
  opens; adding a new sample requires no Python changes.
- Supports metadata-wrapped configurations and ordinary flat configuration JSON.
- Loading a sample fills the dialog without generating geometry or overwriting
  the saved user configuration until **Generate** is pressed.
- Added localized sample names/descriptions and GUI controls in all six
  interface languages.
- Added five initial configurations adapted from the original OpenSCAD
  `demo_collection()` module.
- Preserves the selected configuration as the dialog configuration base so automatic
  mode does not accidentally retain stale values from the previous user JSON.
- Moved adaptive radial section distribution to the proposed v1.2 roadmap.
- Changed the default automatic loft section order from tip-to-root to
  root-to-tip, matching the successful manual Computer Cooling Fan workflow.
- Added selectable Root-to-tip, Tip-to-root, and Automatic robust loft modes.
- Added optional dual trailing-edge guide rails through the two natural
  trailing-edge corners of every section.
- Added a Merge tangent edges option and reports the successful loft strategy.
- Automatic robust mode retries order, guide-rail, and tangent-edge variants
  while preserving all section sketches if every attempt fails.
- Updated the manifest description and installation guidance so the
  Scripts and Add-Ins version refreshes after replacing the full folder and
  restarting Fusion.
- Stopped forcing an extra loft section exactly at Transition_Point; generated
  spacing/slice distributions now contain only their regular stations plus the
  exact root and tip.
- Added configurable distributed guide rails through matching NACA fit
  points and exposed their count in Advanced Construction and presets.
- Restricted distributed counts to the odd sequence 3, 5, 7, 9..., with a
  temporary default/sample value of 9 and symmetric upper/lower placement.
- Automatic robust mode tests no rails and then every odd distributed-rail
  count from 3 through the requested maximum; dual trailing-edge rails remain
  explicit/experimental.
- Changed distributed rails to an odd, symmetric sequence: 3, 5, 7, 9...
  with a temporary default of 9.
- Distributed rails now always include two trailing-edge anchors and one
  leading-edge rail; every additional pair is split symmetrically between
  upper and lower surfaces.
- Added temporary `Loft_Distributed_Rails_Use_TE_Vertices` comparison control:
  exact trailing-edge vertices versus the first profile points after them.
- Increased the factory/configuration Boundary Fill diameter overlap from 0.000001 mm
  to the manually validated 0.0001 mm.
- Added a complete Automatic robust preflight in isolated temporary
  components. Each candidate must create a valid loft, pass the surface-quality
  criterion, and—when requested—complete Boundary Fill before final geometry is
  generated in the active component.
- Added theoretical-to-loft quality evaluation at the midpoint of every
  interior radial interval. The three worst intervals are refined at 25% and
  75%, and approval uses the global maximum rather than RMS alone.
- Added `Loft_Quality_Check` and
  `Loft_Quality_Max_Deviation_Percent` (temporary default 0.1% of local chord).
- Automatic robust Boundary Fill retries multiply the diameter overlap by 10,
  starting at the configured value and stopping at 0.1 mm.
- Robust rail search now follows `0, 3, 5, 7, 9...` through the selected odd
  maximum, then tries the opposite loft direction and tangent-edge state only
  as fallbacks.
- Made robust preflight compatible with the January 2026 Part Design intent:
  disposable internal components are used only in Hybrid designs.
- In Part and Assembly designs, each candidate is created in the active
  component and removed using a pre-candidate entity-token snapshot.
- Added dependency-ordered cleanup for temporary Boundary Fill, extrusions,
  lofts, sketches, and orphan bodies.
- Corrected preflight-failure reporting so it no longer claims that wrapped
  sections were created or preserved when the search stopped before final
  geometry generation.
- Added recommended uniform-chord rail placement with equal x/c targets.
- Replaced the temporary trailing-edge checkbox with a three-mode placement
  dropdown while retaining the legacy JSON boolean for compatibility.
- Automatic robust now searches at least through 9 rails when resolution
  permits, even if the saved upper-limit field is smaller.
- Added a short-period waviness criterion reported as estimated wave angle;
  the factory limit is 0.2 degree.
- Fixed no-geometry preflight reporting and timeline handling.
- Added a cancelable Fusion ProgressDialog to Automatic robust searches.
- Cancellation is checked between temporary sections, quality stations,
  candidates, overlaps, and before final reconstruction; active candidates are
  cleaned before control returns.
- Added complete JSON and text logs for successful, exhausted, cancelled, and
  unexpected-error searches.
- Logs include every started candidate, stable strategy fields, stage timings,
  quality metrics, Boundary Fill volumes, kernel errors, and cleanup status.
- Final messages show a compact candidate summary and the absolute paths of the
  saved logs; long summaries are capped while the files retain every entry.
- Fixed literal `\n` sequences in progress and final-result messages.
- Progress now counts loft strategies (`order × rails × merge`) instead of
  multiplying the displayed total by all possible Boundary Fill overlaps.
- Closing or unexpectedly hiding the ProgressDialog is treated as cancellation
  after the dialog has been observed on screen.
- Progress messages no longer include multiline kernel exceptions; complete
  diagnostics remain in JSON/TXT logs.
- Candidate summaries reduce kernel failures to a stable short error code.

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

