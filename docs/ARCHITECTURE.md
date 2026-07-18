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

The command uses Fusion's native OK button with localized text **Generate**.
Clicking it runs the normal validation and execute pipeline and terminates the
command after the run.

`Command.execute` validates the inputs, saves the complete configuration,
captures the current timeline boundary, and creates geometry inside Fusion's
command transaction. It queues the result rather than grouping immediately.

The global `commandTerminated` handler is the primary post-commit step. It
groups and collapses the committed contiguous timeline range and then displays
the final message. Never flush while the command remains active: Fusion can
otherwise revert visibility changes and remove the group when the transaction
is later terminated.

Timeline objects are tested explicitly for `None` and `isValid`; a first run can
begin with a valid timeline whose item count is zero.

## Active-component targeting

`_generate_sections` resolves and validates `Design.activeComponent` once at
the start of a run. That component is passed through the existing geometry
pipeline; `rootComponent` is not substituted. The target name is attached to `GenerationResult` so each repeated generation reports its destination component after the transaction commits.

## Component-context paths

Wrapped-section paths—open in split trailing-edge mode and closed in the legacy mode—are built with `component.features.createPath(ObjectCollection, False)` rather than the static `Path.create`. The component-scoped factory preserves the context of
native sketch curves in nested components.

Timeline grouping counts the committed range before calling
`TimelineGroups.add`; zero items are reported as an error and one item is
reported as an ungroupable partial run.

## Configuration discovery and dialog base

`_discover_sample_configurations` recursively scans both the bundled `configurations/`
tree and the per-user configurations tree. Metadata-wrapped and flat configurations
are normalized into `SampleConfiguration` records. User configurations sort before
bundled configurations, while duplicate display names receive a localized source
suffix.

Loading a configuration overlays its parameters on immutable factory defaults and
updates every command input through `_apply_config_to_dialog`. The result
becomes `_dialog_config_base`, separate from the saved last-run JSON. Close
therefore leaves persistence untouched; Generate serializes the loaded configuration
plus subsequent edits.

`_save_current_as_user_sample` writes the complete current GUI configuration,
excluding only `Interface_Language`, to the per-user configurations directory and
refreshes the open drop-down immediately.


## Manual progress, cancellation, and logs

Manual wrapped generation uses `_ManualProgressController`, a ProgressDialog
that is instantiated only when the selected loft order is not Automatic robust.
It reports validation, section creation, both split lofts, XY Trim, Stitch,
cylinders, Boundary Fill, and final assembly. Checkpoints call `adsk.doEvents()`
and raise `_ManualGenerationCancelledSignal` on cancellation; the execute handler
catches the signal so already-created features remain committed for inspection.
Cancellation is cooperative and cannot interrupt a Fusion kernel call already in
progress. The checkpoints intentionally avoid forcing a canvas/timeline refresh
after every feature; the entire run still belongs to one command transaction.

Manual JSON logs include the full parameter snapshot, resolved radii, generator
and Fusion/runtime versions, raw `GenerationResult`, feature-level errors, and
the exact post-commit message shown to the user including timeline grouping.

## Robust loft preflight

`_generate_sections` invokes `_find_robust_strategy` only when the selected
order is Automatic robust. Each candidate is built inside a new child component
created with an identity transform. The occurrence is hidden and always deleted
in `finally`, so failed lofts, rails, cylinders, and Boundary Fill features do
not remain in the active component.

The search order is:

1. preferred tangent-edge state, then its opposite;
2. root-to-tip, then tip-to-root;
3. rails `0, 3, 5, 7...` through the selected maximum;
4. after loft and quality succeed, overlap `initial, 10×initial...` up to
   0.1 mm when Boundary Fill is required.

The successful settings are rebuilt once in the active component using manual
order, exact rail count, exact tangent-edge state, and the accepted overlap.

## Loft surface-quality evaluation

`_evaluate_loft_surface_quality` calculates theoretical wrapped sections at the
midpoint of every interior radial interval. Exact root/tip-adjacent intervals
are excluded when enough stations exist because the intentional Boundary Fill
overlap dominates them.

At each station, up to 25 interior NACA contour points are projected to every
bounded BRep face using `BRepFace.evaluator.getParameterAtPoint`,
`isParameterOnFace`, and `getPointAtParameter`. The nearest valid face distance
is converted from Fusion centimetres to millimetres and normalized by local
chord. The three intervals with the largest midpoint error are sampled again at
25% and 75%.

Acceptance uses the global maximum percentage. RMS, absolute maximum, worst
radius, contour index, and sample count are retained in `GenerationResult` for
diagnostics. This intentionally rejects a localized half-blade waviness even
when the global RMS remains low.


## Boundary Fill finalization

`wrapped_section_geometry` separates nominal radius from physical wrap radius.
Only the first and last sections receive the infinitesimal radial overlap used
for Boundary Fill. The planar trailing-edge segment is sampled and wrapped as a
second fitted spline.

`_create_boundary_fill_blade_solid` uses the loft body and the two nominal open
cylindrical bodies as tools. In the manual split trailing-edge workflow with
`Cut_Below_Hub_Base`, the main and trailing-edge surfaces are first trimmed in
one Trim feature by the global XY plane, then stitched. The XY plane is added
as a fourth Boundary Fill tool, even if no surface required trimming, so the
open lower boundary is closed directly by the fill cell rather than by a
fragile Split Body operation on the finished solid.

The function inspects `BoundaryFillFeatureInput.bRepCells`, keeps the largest
positive-volume cell, sets `isRemoveTools`, calls `add`, and requires exactly
one solid result. Every pre-add failure cancels the partial Boundary Fill
transaction.

## Distributed profile rails

Every wrapped section stores its complete `points_xyz_mm` sequence. Since all
stations in one run use the same `Profile_Points`, the same contour index
identifies the same NACA sampling location in every section.

`_distributed_rail_indices(N, count, use_trailing_edge_vertices)` accepts only
odd counts of at least three. Mandatory indices are:

- upper TE anchor: `0` or `1`;
- leading edge: `N`;
- lower TE anchor: `2N` or `2N-1`.

The remaining `(count-3)/2` indices are selected independently and evenly from
each surface, giving exact upper/lower symmetry. The temporary checkbox is
threaded through command creation, JSON persistence, generation signatures,
strategy reporting, and rail construction.

Manual loft order uses the requested count exactly. Automatic order starts
without rails and then uses the duplicate-free odd progression
`3 -> 5 -> 7 -> 9 -> ... -> requested`. Failed-attempt rail sketches are deleted after a
later strategy succeeds and retained only if every attempt fails.

## Robust candidate isolation by design intent

`_robust_can_use_internal_component` checks `Design.designIntent`.

- Hybrid intent uses the original disposable-occurrence isolation.
- Part and Assembly intents use `_RobustComponentSnapshot`, which stores stable
  entity tokens for sketches, lofts, extrudes, Boundary Fills, and B-Rep
  bodies.

`_cleanup_robust_component_candidate` deletes only entities absent from the
snapshot. Deletion follows dependency order and verifies that no new tracked
entity remains. This avoids relying on internal components in Part Design,
which supports only its default component.

## Uniform-chord rails and wave-angle metric

`_uniform_chord_sample_indices` assigns cosine-spaced NACA fit points to equal
x/c targets without duplicate indices.

For interval length `h` and sample fraction `f`, the estimated artificial slope
is `error / (h*f*(1-f))`; the reported wave angle is its arctangent. Every
interval is checked at 50%, and the worst positional and angular intervals are
refined at 25% and 75%.

## Robust progress, cancellation, and logging

`_RobustProgressController` owns a Fusion `ProgressDialog`, calls
`adsk.doEvents()`, and raises `_RobustSearchCancelledSignal` when the button is
pressed. The signal is never converted into a loft, quality, or Boundary Fill
failure. Candidate `finally` cleanup runs before it reaches the search loop.

`_find_robust_strategy` maintains a JSON-safe session dictionary and persists
it for all terminal states. Candidate timing uses `time.perf_counter()`.
Logging failure does not discard a successfully selected geometry strategy;
the log error is returned separately and displayed to the user.

## Progress-dialog closure semantics

`_RobustProgressController` records whether `ProgressDialog.isShowing` has ever
been true. After that point, `isShowing == false` outside normal `__exit__`
cleanup raises `_RobustSearchCancelledSignal`, even when `wasCancelled` is
false.

The progress denominator is `len(merge) * len(order) * len(rail_values)`.
Overlap escalation is a substep and advances the bar only when its loft strategy
is terminal.
