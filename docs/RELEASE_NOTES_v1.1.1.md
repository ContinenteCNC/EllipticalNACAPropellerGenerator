# Elliptical NACA Propeller Generator v1.1.1

Version 1.1.1 is a maintenance release that preserves the validated v1.1
geometry pipeline while correcting the Toy Boat configuration and improving
manual failure diagnostics.

## Boat-propeller orientation

- Added `Propeller_Orientation` with backward-compatible `standard` and
  `flipped_180` values.
- `flipped_180` reproduces the blade-only transform used by Alex Matulich's
  `demo_boatpropblades()`:

  `translate([0,0,hublen]) rotate([180,0,0]) propeller(...);`

- The transform is applied to the first solid blade immediately after Boundary
  Fill, before the circular pattern, hub, and spinner are created.
- `Root_Length` is the direct mapping of the original OpenSCAD `hublen` value.
- The transform does not change `Prop_Direction`, `Sweep_Angle`, geometric
  pitch, or any blade-generation equation.

## Configuration updates

- Every bundled JSON configuration now includes `Propeller_Orientation`.
- `03_toy_boat_propeller.json` uses `flipped_180`; the other configurations use
  `standard`.
- The Toy Boat configuration now uses both `Root_Length = 25.0 mm` and
  `Hub_Length = 25.0 mm`, improving the hub-to-blade-root blend.
- The default and every bundled configuration now use
  `Stitch_Tolerance_mm = 0.1`.

## Diagnostics

Manual surface-generation failures now identify the actual failing stage:

- main open-surface loft;
- separate trailing-edge loft;
- XY surface Trim;
- surface Stitch.

Partial Fusion features remain in the timeline for inspection, and the detailed
manual JSON log retains the stage-specific error.

## Compatibility

Existing JSON files without `Propeller_Orientation` remain compatible and use
`standard`. Existing `Prop_Direction` and `Sweep_Angle` conventions are
unchanged.

## Safety notice

Generated propellers are not certified for structural strength, fatigue life,
balance, rotational speed, impact safety, or aerodynamic performance. The user
remains responsible for engineering validation, manufacturing quality, and safe
testing.
