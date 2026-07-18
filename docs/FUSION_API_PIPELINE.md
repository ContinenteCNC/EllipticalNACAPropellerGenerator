# Fusion API construction pipeline

## 1. Wrapped section sketches

Each radial station creates two independent 3D fitted splines:

- the open wrapped NACA contour;
- the wrapped trailing-edge closing segment.

The open contour intentionally excludes the trailing-edge closure.

## 2. Main surface loft

The validated manual default lofts the open NACA contours from root to tip with
no guide rails. Optional main-surface guides remain available as advanced
controls.

## 3. Separate trailing-edge loft

A second narrow surface loft joins the trailing-edge closing splines. It always
uses two rails passing through the exact upper and lower trailing-edge vertices
of every section.

Separating this surface avoids the self-intersection failures observed when the
closing segment was part of one closed loft path.

## 4. Optional XY Trim before Stitch

When `Cut_Below_Hub_Base` is enabled, the code checks both source surfaces. If
either crosses below `Z=0`, one Trim operation uses the global XY plane to
remove the lower pieces before the surfaces are stitched.

## 5. Stitch

The main surface and trailing-edge surface are stitched up to the configured
tolerance. After an XY Trim, a deliberate opening can remain at the blade base.

## 6. Analytical limit cylinders

Open circular profiles are extruded as cylindrical surfaces at the nominal
root and tip radii:

```text
R = Hub_Diameter / 2
R = Propeller_Diameter / 2
```

The configured Boundary Fill diameter overlap shifts only the first and last
loft-section construction radii. Aerodynamic calculations remain at nominal
radii.

## 7. Boundary Fill

The validated split workflow supplies:

- the stitched blade shell;
- the inner cylindrical surface;
- the outer cylindrical surface;
- the global XY plane.

The XY plane is included whenever base cutting is enabled, even when neither
surface crosses it. The largest positive-volume cell is selected and verified
as one solid body.

## 8. Assembly

```text
single solid blade
-> optional Z offset
-> circular blade pattern
-> hub with shaft hole
-> optional rectangular or aerodynamic ring
-> optional parabolic or ogive spinner based at Z = Hub_Length
-> Join operations
```

Optional features that cannot be joined may remain as separate bodies with a
diagnostic message.

## Legacy and automatic paths

Closed-profile loft construction and the former extend/trim/stitch finalization
remain available for compatibility. Automatic robust mode remains an advanced
closed-profile preflight path in v1.1.

## API pitfalls already handled

- Fusion internal lengths are centimetres.
- Construction object `isVisible` is read-only; use `isLightBulbOn`.
- Trim inputs begin a partial transaction and must be cancelled when abandoned.
- Event handlers must be retained in a module-level list.
- Pattern, Stitch, Combine, and Boundary Fill result ordering must not be
  assumed.
- Transient `Path` wrappers are recreated between robust candidates.
