# Fusion API construction pipeline

## 1. Section sketches

Each wrapped section is a 3D fitted spline plus a 3D line closing the trailing
edge. A closed `Path` is created for loft input.

## 2. Surface loft

Fusion creates an open surface loft through the section paths. The current
implementation adds sections from tip to root because that order proved more
robust with a heavily thickened root profile.

## 3. Natural extension

The free root and tip boundary loops are extended slightly. This guarantees
that later analytical cylindrical trims intersect cleanly at the requested
radii.

## 4. Analytical limit cylinders

Open circular profiles are extruded as cylindrical surfaces at:

```text
R = Hub_Diameter / 2
R = Propeller_Diameter / 2
```

## 5. Trim operations

The blade surface trims the cylinders into small cap patches. The cylinders
then trim the blade back to the exact root and tip radii.

Fusion exposes multiple B-Rep cells. The code selects cells by area and average
radius instead of relying on unstable collection ordering.

## 6. Stitch

The trimmed blade surface and two cylindrical caps are stitched. The result is
verified to be a solid B-Rep body.

## 7. Printable base and position

The blade is split by the global XY plane and all geometry below `Z=0` is
removed. `Prop_Z_Offset` is then applied.

## 8. Assembly

```text
single blade
-> circular blade pattern
-> hub with shaft hole
-> optional hoop
-> optional parabolic and/or ogive spinner
-> Join operations
```

Optional features that do not intersect can remain as separate bodies, with a
diagnostic message.

## API pitfalls already encountered

- Fusion internal lengths are centimetres.
- Construction object `isVisible` is read-only; use `isLightBulbOn`.
- Trim inputs begin a partial transaction and must be cancelled when abandoned.
- Event handlers must be retained in a module-level list.
- Pattern and combine result body ordering must not be assumed.
