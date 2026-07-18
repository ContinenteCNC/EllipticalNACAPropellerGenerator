# Contributing

## Design rule

Preserve geometric equivalence with Alex Matulich's original OpenSCAD unless a change is
explicitly introduced as a new mode.

## Module boundaries

- Keep all reusable mathematics in `propeller_math.py`.
- Do not import `adsk` from `propeller_math.py`.
- Keep unit conversion at the Fusion API boundary.
- User and math units are millimetres; Fusion internal lengths are centimetres.

## Localization

Every new localization key must be added to all six JSON files:

- `pt-BR`
- `en`
- `es`
- `fr`
- `de`
- `ru`

English is the fallback locale.

## Testing

At minimum:

1. Run `py_compile` on all Python modules.
2. Parse every Python module with `ast.parse`.
3. Confirm all locale files contain identical key sets.
4. Test the add-in in Autodesk Fusion.
5. For geometry changes, compare against an OpenSCAD export by solid overlay.
6. Confirm the final result is a single solid when the requested bodies touch.

## Release checklist

- Increment the manifest version.
- Update `CHANGELOG.md`.
- Update `docs/LLM_CONTEXT.md` if architecture or behavior changed.
- Preserve the add-in UUID unless intentionally creating a separate add-in.
- Package one top-level `EllipticalNACAPropellerGenerator` folder.
- Do not include `__pycache__`, `.pyc` or temporary JSON files.

## Adding configurations

Add any valid `.json` file under `configurations/` or one of its subdirectories. The
add-in discovers it automatically the next time the command opens.

Prefer the metadata-wrapper format documented in `configurations/README.md`. Keep
configuration names unique, provide a concise description, and include only public
configuration keys inside `Parameters`. A configuration must not set
`Interface_Language`.
