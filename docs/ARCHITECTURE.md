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
propeller_defaults.json + per-user propeller_user_config.json
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

## Timeline grouping

`Command.execute` validates, saves settings, captures the current end index,
and creates geometry inside Fusion's command transaction. It does not attempt
to create a timeline group.

The execute handler queues the formatted result and the captured design/index.
A global `UserInterface.commandTerminated` handler then creates the collapsed
group from the now-committed contiguous range and finally displays the result.
All skip and failure paths produce an explicit localized status.

Timeline-related API objects must be tested explicitly for `None` and `isValid`. Truthiness is not used because the first run can begin with a valid timeline whose count is zero.

## Active-component targeting

`_generate_sections` resolves and validates `Design.activeComponent` once at
the start of a run. That component is passed through the existing geometry
pipeline; `rootComponent` is not substituted. The target name is attached to
`GenerationResult` because the result dialog is displayed after command
termination.

## Component-context paths

Closed wrapped-section paths are built with
`component.features.createPath(ObjectCollection, False)` rather than the
static `Path.create`. The component-scoped factory preserves the context of
native sketch curves in nested components.

Timeline grouping counts the committed range before calling
`TimelineGroups.add`; zero items are reported as an error and one item is
reported as an ungroupable partial run.
