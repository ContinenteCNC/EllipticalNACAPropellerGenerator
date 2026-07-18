# Elliptical NACA Propeller Generator v1.1.0

Version 1.1 delivers a major stability improvement to the native Fusion blade
workflow. The split trailing-edge construction, pre-Stitch XY trimming, and
Boundary Fill finalization completed every bundled configuration in manual
validation, while the release also adds configuration, logging, progress, and
command-dialog improvements.

## Validated blade workflow

The default manual workflow is now:

1. create one wrapped 3D NACA contour and one trailing-edge closing spline per
   radial section;
2. loft the open NACA contours from root to tip without main-surface guide
   rails;
3. loft the trailing-edge closures separately using two rails through the exact
   trailing-edge vertices;
4. when requested, trim both source surfaces below the global XY plane before
   Stitch;
5. Stitch the two surface bodies;
6. create the inner and outer limit cylinders;
7. Boundary Fill with the stitched shell, both cylinders, and the XY plane;
8. create the blade pattern, hub, shaft hole, optional ring, and optional
   spinner.

The five design configurations were manually validated in Autodesk Fusion with:

```text
Loft construction: Open main surface + separate trailing edge
Loft section order: Root to tip
Loft guides: None
Boundary overlap — diameter: 0.1 mm
```

The validated design configurations cover two- and three-blade model-airplane propellers, a
toy-boat propeller with ogive spinner, a rubber-band airplane propeller that
requires pre-Stitch XY trimming, and a five-blade computer cooling fan.

## Command dialog

- Fusion's native OK button is labeled **Generate** and terminates the command
  after each run, following the standard Fusion command lifecycle.
- The **Configurations** group starts expanded and combines built-in and
  user-saved JSON configurations.
- The former Restore Factory Defaults action is represented by the built-in
  **3 × 1.25-inch propeller — original configuration**.
- Manual generation displays an independent cancelable progress dialog with
  the current stage; Automatic robust retains its separate legacy/research
  dialog. Cancellation is cooperative between named geometry checkpoints.
- Geometry remains inside one command transaction. UI events are processed at
  named manual checkpoints so features remain visible during creation. Progress
  text is wrapped to prevent the dialog from expanding near completion.
- After command termination commits the transaction, the run is grouped in the
  timeline and reported. This avoids visibility and grouping rollback.

## Configuration persistence

All 67 geometric, construction, finalization, assembly, and display parameters
represented by the dialog are serialized to JSON. Interface-only controls such
as buttons, group containers, configuration descriptions, and the
new-configuration name are
not configuration parameters.

Validated settings are saved before geometry creation to the per-user file:

```text
Windows: %APPDATA%\EllipticalNACAPropellerGenerator\propeller_user_config.json
macOS:   ~/Library/Application Support/EllipticalNACAPropellerGenerator/propeller_user_config.json
```

The last generated configuration is therefore restored after Fusion restarts.
Closing the dialog without generating does not overwrite the saved
configuration.

## Configuration library

- Bundled configurations are discovered recursively under the add-in
  `configurations/` directory.
- User-created configurations are stored outside the installation in the
  per-user `configurations/` directory. Existing user `samples/` JSON files are
  copied into it once without overwriting.
- The GUI can save the complete current configuration as a new configuration and
  refresh the open configuration list immediately.
- Loading a configuration fills the dialog but does not generate geometry or replace
  the last-run configuration until **Generate** is pressed.

## Logs

Every wrapped manual run writes a detailed JSON log to the per-user
`manual_generation_logs/` directory. The file records:

- complete parameter JSON;
- resolved radial stations;
- selected construction/order/guide modes;
- final `GenerationResult` fields;
- elapsed time, status, generator version, Fusion version, Python/platform
  runtime, and any exception detail;
- the same substantive result text shown in the final dialog, plus the raw
  `GenerationResult` fields. Runs completed with feature-level errors are marked
  `completed_with_errors`; unexpected exceptions and user cancellation are
  recorded explicitly.

Automatic robust mode retains its existing JSON and text candidate logs.

## Additional corrections

- Corrected parabolic and ogive spinner profiles to start at `Z = Hub_Length`.
- Recreated transient Fusion `Path` wrappers between robust candidates to avoid
  stale `pathEnt` errors.
- Added a true maximum of 15 robust execution attempts.
- Added root-fairing and configurable post-fairing quality regions.
- Preserved partial manual features after failure for timeline diagnosis.
- Retained closed-profile and legacy finalization options for compatibility.

## Compatibility

Existing v1.0 user JSON keys remain supported. The previous
`Loft_Distributed_Rails_Use_TE_Vertices` key is retained for downgrade and
legacy compatibility.

## Safety notice

Generated propellers are not certified for structural strength, fatigue life,
balance, rotational speed, impact safety, or aerodynamic performance. The user
remains responsible for engineering validation, manufacturing quality, and
safe testing.
