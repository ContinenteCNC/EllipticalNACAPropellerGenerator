# Roadmap

This roadmap records planned ideas after the first stable release. It is not a
guarantee of dates or final implementation details.

## v1.1 — Configuration library (implemented)

Version 1.1 provides a dynamically discovered `configurations/` directory and a GUI
drop-down. Any valid JSON file added under that directory appears the next time
the command opens. The initial library contains five configurations adapted
from the original OpenSCAD `demo_collection()` module.

## v1.2 — Adaptive radial section distribution

Goal: place more section profiles where blade geometry changes rapidly and
fewer profiles where it varies smoothly.

Proposed direction:

1. Evaluate quantities that vary from root to tip, such as:
   - chord;
   - geometric angle/pitch contribution;
   - sweep;
   - maximum camber;
   - camber position;
   - relative or physical thickness;
   - other profile-shape descriptors.
2. Normalize the quantities before combining their rates of change, because
   millimetres, angles, and dimensionless airfoil parameters cannot be
   compared directly.
3. Compute a weighted geometric-variation metric between candidate radial
   positions.
4. Convert that metric into a requested section spacing bounded by:
   - minimum section spacing;
   - maximum section spacing.
5. Begin from the configured minimum spacing near the root and clamp every
   calculated spacing to the minimum/maximum limits.
6. Always insert mandatory locations exactly:
   - root;
   - profile transition point;
   - tip;
   - any future discontinuity or user-defined mandatory station.

A possible later refinement is error-based subdivision: compare the actual
intermediate profile with the profile predicted by interpolation and subdivide
until the geometric error is below a tolerance.

Open design questions:

- Which quantities should be enabled by default?
- How should each gradient be normalized and weighted?
- Should the user choose a simple quality level or expose all tolerances?
- How should the algorithm avoid excessive profile counts around numerical
  noise?

## Later possibilities

- schema-version migration for user configurations;
- import/export buttons for sharing configurations;
- optional geometric quality diagnostics;
- automated regression models for representative configurations.
