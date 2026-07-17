# Changelog

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
