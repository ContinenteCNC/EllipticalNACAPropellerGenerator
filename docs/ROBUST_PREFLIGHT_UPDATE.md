# Robust preflight refinement (unreleased)

This update keeps project version `1.1.0` unchanged and revises only the
Automatic robust preflight policy and diagnostics.

## Expected behavior

### Computer Cooling Fan

The search must continue to prefer a candidate that passes every configured
quality target. With the current sample and limits, the previously observed
reference result is root-to-tip with seven uniformly distributed rails.

### Two-blade Model Airplane

If the zero-rail loft is geometrically valid and Boundary Fill succeeds, but
the configured fidelity limits are missed, the search must retain it as a
valid fallback. If no later candidate passes the strict targets, the fallback
is selected and final geometry is generated with a visible quality warning.

## Performance changes

Wrapped section sketches are created once for each tested overlap value and
reused by all candidates. Candidate cleanup removes only temporary guide rails,
lofts, cylinders, Boundary Fill features, and orphan bodies.

The candidate policy also:

- runs the preferred zero-rail loft once;
- prunes higher rail counts after two consecutive self-intersection errors in
  the same order/placement/merge family;
- tries alternate rail placement before broad direction and merge fallbacks;
- skips equivalent zero-rail permutations after a valid zero-rail loft exists.

## Log schema

Robust log schema is now version 2. New fields include:

- `strict_accepted`;
- `valid_fallback`;
- `sections_reused`;
- `selection` (`strict` or `best_valid_fallback`);
- `adaptive_candidate_plan`;
- pruning and section-reuse configuration metadata.

The previous `wave` quantity is presented to the user as an **equivalent
deviation angle**. The mathematical calculation is retained for strict
comparison and regression testing, but it is explicitly not described as a
direct measurement of curvature or zebra-stripe waviness.
## Regional quality policy

Quality is now reported separately for the root fairing and the aerodynamic blade. A candidate is accepted with a fairing warning when it is geometrically finalizable, every sampled aerodynamic station satisfies both strict targets, and any remaining exceedance is confined to the configured root-fairing span (`root radius` through `root radius + Fairing_Size`). This prevents a deliberately aggressive hub transition from forcing unsuccessful rail searches while preserving the strict behavior on the lifting surface.

The log schema is now version 3 and includes `quality.fairing`, `quality.aerodynamic`, `accepted_tolerating_fairing`, and the fairing end radius.


## Post-fairing tolerance and execution safeguards

The automatic quality evaluator now separates three radial regions: fairing,
post-fairing transition, and strict aerodynamic region. The post-fairing
transition length is configured by
`Loft_Quality_Post_Fairing_Margin_Multiplier` and defaults to `2.0`, meaning
that the tolerated margin after the fairing is twice `Fairing_Size`.

Actual robust attempts are capped at 15, including overlap retries. Reusable
section sketches are retained, but Fusion `Path` wrappers are recreated for
each loft candidate to prevent stale `pathEnt` references after cleanup.

## Separate trailing-edge surface strategy

Automatic robust mode now treats each wrapped section as two open paths. The NACA contour forms the principal loft, while the formerly closing trailing-edge spline forms a second, narrow loft. Fusion stitches those two surface bodies before quality analysis and solid finalization. This reduces the topological burden on the main loft and directly addresses cases where the closing segment forces `ASM_LOFT_SURFACE_SELF_INTERSECTS`. The original closed-section loft remains available as a late compatibility fallback.
