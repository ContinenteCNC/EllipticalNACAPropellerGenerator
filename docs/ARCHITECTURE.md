# Architecture

## Files

### `EllipticalNACAPropellerGenerator.py`

Fusion-facing adapter. It owns:

- command creation and event handlers;
- input parsing and JSON persistence;
- 2D and 3D sketch creation;
- loft, extension, trim and stitch operations;
- blade pattern, hub, hoop and spinner construction;
- localized result messages.

### `propeller_math.py`

Pure-Python geometry. It owns:

- validation and mapping to the original Thingiverse propblade() parameters;
- NACA 4-digit equations;
- radial airfoil interpolation;
- fairing and trailing-edge modifications;
- chord and pitch equations;
- cylindrical section wrapping;
- automatic radial section distributions.

It must remain importable without Autodesk Fusion.

### `localization.py`

Detects the Fusion language, applies the optional JSON override and loads a
locale with English fallback.

## Data flow

```text
propeller_config.json
        +
command dialog values
        |
        v
BladeConfig + assembly parameters
        |
        v
propeller_math.py section coordinates
        |
        v
Fusion 3D sketches and section paths
        |
        v
surface loft -> trims -> stitch -> blade solid
        |
        v
pattern + hub + hoop + spinner assembly
```

## Error philosophy

Optional stages record partial success. A valid blade should not be destroyed
because an optional hoop or spinner cannot be joined. When geometrically
reasonable, optional bodies remain as separate solids and the result dialog
reports the failure.
