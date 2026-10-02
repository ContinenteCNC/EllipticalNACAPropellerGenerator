# Elliptical NACA Propeller Generator v1.1.3

Version 1.1.3 is a user-interface and diagnostics maintenance release. It does
not change the propeller mathematics or the validated geometry-generation
pipeline.

## Changes

- `Centerline` now appears in **Propeller Geometry** instead of **Advanced
  Construction**. Its JSON key and mathematical meaning are unchanged.
- The propeller-direction dropdown now shows **CW** and **CCW** instead of
  `+1` and `-1`. Internally and in JSON configurations, the existing numeric
  convention is preserved: `CW = +1`, `CCW = -1`.
- The final generation result is displayed in a fixed-height, read-only summary
  box with 12 visible rows and automatic vertical scrolling.
- If the split trailing-edge workflow fails at **Stitch**, the summary reports
  the tolerance used and suggests increasing **Stitch tolerance**.
- If **Boundary Fill** fails, the summary reports the diameter overlap used and
  suggests increasing **Boundary overlap**.
- The Boundary Fill diameter-overlap default remains the validated **0.1 mm**.
- The base-cut and axial-offset sequence is unchanged. With the split
  trailing-edge Boundary Fill workflow, `Cut_Below_Hub_Base` resolves the
  source surfaces against global `Z=0` before Stitch; `Prop_Z_Offset` remains a
  later assembly offset.
- The Windows manual-installation path distributed in the documentation is
  `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`.
- The Boundary-overlap tooltip now reports the actual 0.1 mm default.

## Compatibility

Existing factory, bundled, and user JSON configurations remain compatible. No
configuration-key migration is required. `Prop_Direction` continues to be
stored numerically.

## Validation status

Static Python compilation, JSON parsing, locale-key parity, version metadata,
and configuration-value preservation were checked outside Fusion. Actual Fusion
B-Rep execution and the new summary-dialog behavior still require runtime
validation inside Autodesk Fusion.
