# Source lineage

## Original library

Alex Matulich / Amatulic created the OpenSCAD
**Elliptical-blade NACA airfoil propeller library** in March 2022.

- Thingiverse: https://www.thingiverse.com/thing:5300828
- Printables: https://www.printables.com/model/159163-elliptical-blade-naca-airfoil-propeller-library
- Article: https://www.nablu.com/2022/03/elliptical-blade-naca-airfoil-propeller.html

The original library contains the core blade geometry:

- NACA 4-digit airfoil equations;
- smooth root, mid and tip profile transitions;
- elliptical chord constraint;
- constant geometric pitch;
- finite trailing-edge thickness;
- root fairing;
- cylindrical wrapping;
- sweep;
- parabolic and rounded-ogive spinner modules.

Its `propeller()` module generates the blades; the original documentation
explicitly leaves the final hub to the user.

## Autodesk Fusion port

This repository ports that geometry to Python and native Autodesk Fusion
features.

It is a geometric and mathematical port, not a textual translation of
OpenSCAD syntax. The output is a smooth B-Rep model rather than a polygon mesh.

The Fusion project adds:

- grouped and translated GUI parameters;
- JSON persistence;
- automatic radial resolution;
- native loft, trim and stitch operations;
- printable blade-base handling;
- blade pattern;
- hub and shaft hole;
- optional peripheral hoop;
- final spinner assembly.

## Attribution statement

The original author is credited because the blade and spinner mathematics are
derived from his work. No affiliation or endorsement is implied.

## v1.1 configuration lineage

Five bundled JSON configurations are parameter adaptations of the five examples
assembled by `module demo_collection()` in the upstream
`elliptical_propblade.scad`; a sixth file preserves the generator's original
3 × 1.25-inch factory configuration. OpenSCAD scene translations, colors, and
rotations are generally not reproduced. The deliberate exception is
`demo_boatpropblades()`: its final
`translate([0,0,hublen]) rotate([180,0,0])` is exposed as
`Propeller_Orientation="flipped_180"`, with upstream `hublen` mapped to the
add-in's `Root_Length`. Hub, bore, spinner, automatic profile-point, and slice
values are mapped to the closest native Fusion generator controls and documented
in each configuration's `Source` metadata.
