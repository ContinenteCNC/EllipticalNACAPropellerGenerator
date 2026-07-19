# Geometry and coordinate conventions

## Basic radii

```text
root_radius = Hub_Diameter / 2
tip_radius = Propeller_Diameter / 2
blade_length = tip_radius - root_radius
```

When `Blade_Pitch < 0`, the effective pitch is `blade_length`, matching the
OpenSCAD library.

## Constant-pitch angle

At absolute shaft radius `r`:

```text
alpha = -Prop_Direction * atan(Blade_Pitch / (2*pi*r))
```

The sign determines the handedness.

## Ellipse-constrained chord

The unconstrained blade planform uses:

```text
ellipse_semimajor = Elen_Fraction * blade_length
maximum_chord = 2 * Max_Chord_Fraction * blade_length
```

The axial constraint is:

```text
minor_axis = min(maximum_chord, Root_Length)
```

The final airfoil chord is the diameter of that ellipse measured at the local
pitch angle. This avoids a discontinuity near the hub.

## NACA transitions

The root-to-mid interpolation factor is:

```text
sin(pi/2 * fraction)
```

The mid-to-tip factor is:

```text
1 - cos(pi/2 * fraction)
```

Camber, camber position and thickness are interpolated independently.

## Fairing

`Fairing_Size` adds physical root thickness and eases it to zero over the same
radial distance. It is not a conventional Fusion fillet.

## Trailing edge

The standard NACA thickness polynomial uses the closed-edge coefficient. A
linear physical offset is then added so the final trailing-edge gap equals
`Trailing_Edge_Thickness` regardless of chord.

## Cylindrical wrapping

After pitch rotation, the chordwise coordinate becomes an azimuthal
displacement around the shaft. Every wrapped point satisfies:

```text
X^2 + Y^2 = radius^2
```

to floating-point precision.

## Sweep sign

The upstream SCAD computes an internal azimuth from:

```text
radius * Sweep_Angle * sign(Prop_Direction)
```

After converting the final SCAD propeller orientation to the Fusion reference
orientation, the add-in uses:

```text
Fusion_sweep = -radius * Sweep_Angle * sign(Prop_Direction)
```

Do not remove this negative sign. It was confirmed by direct solid overlay.

## Axial references

- Blade base trimming occurs at global `Z=0`.
- `Prop_Z_Offset` is applied after that trim.
- The final hub starts at global `Z=0`.
- `Hoop_Offset` is also measured from global `Z=0`, independently of
  `Prop_Z_Offset`.
- Spinners start at global `Z=0`.


## Aerodynamic airfoil ring

The upstream example constructs:

```text
translate([reference_radius, 0])
rotate(-90 deg)
NACA_profile(origin=1, dir=1)
rotate_extrude(360 deg)
```

In radial/axial coordinates:

```text
radial = reference_radius + chord * airfoil_y
axial  = axial_offset + chord * (1 - airfoil_x)
```

Thus the trailing edge lies at the axial offset and the rounded leading edge
is approximately one chord in +Z. The reference diameter is not the body's
outside diameter.

## Nominal and physical end radii

For Boundary Fill, aerodynamic geometry is evaluated at the nominal radius.
Only the cylindrical placement changes:

```text
root wrap radius = root nominal radius - overlap_diameter / 2
tip wrap radius  = tip nominal radius  + overlap_diameter / 2
```

The angular map still divides tangential distance by the nominal radius. This
makes the overlap a purely radial perturbation. The planar trailing-edge closing
segment is sampled before wrapping and becomes a second 3D fitted spline.

## Radial stations and Transition_Point

`Transition_Point` is a continuous NACA interpolation boundary, not a required
geometric station. Spacing mode now creates its regular root-origin grid and
adds only the exact tip. Slice mode returns exactly `slices + 1` stations.

The exact transition radius can still appear naturally when it coincides with
the regular grid or when the user includes it in Manual radii.

## Rail positions by normalized chord

With `2m+1` rails, the leading edge is constrained and each surface receives
`m` rails at `x/c = 1/(m+1), ..., m/(m+1)`.

## Propeller direction, sweep, and final orientation

`Prop_Direction` already multiplies the effective sweep sign, matching the
OpenSCAD equations. Do not manually negate `Sweep_Angle` when changing
`Prop_Direction`. `Propeller_Orientation` is independent. Its `flipped_180`
mode is applied only after the assembly is complete and maps
`(x, y, z)` to `(x, -y, Root_Length-z)`, reproducing
`translate([0,0,Root_Length]) rotate([180,0,0])`. OpenSCAD `hublen` maps to `Root_Length` in this add-in.
