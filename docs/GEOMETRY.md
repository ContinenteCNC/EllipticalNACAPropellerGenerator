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
