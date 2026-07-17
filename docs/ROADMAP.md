# Roadmap

This roadmap records planned ideas after the first stable release. It is not a
guarantee of dates or final implementation details.

## v1.1 — Adaptive radial section distribution

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
5. Start conservatively near the root and clamp every calculated spacing to
   the configured limits.
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

## v1.2 — Sample configuration library

Goal: provide useful starting points without replacing the user's saved
configuration or factory defaults.

Proposed repository structure:

```text
samples/
├── basic_two_blade.json
├── basic_three_blade.json
├── rectangular_tip_ring.json
├── aerodynamic_naca_ring.json
├── parabolic_spinner.json
└── rounded_ogive_spinner.json
```

Proposed GUI:

```text
Sample configuration: [ Basic two-blade propeller ▼ ]
[ Load sample ]
```

Loading a sample should:

- populate the current dialog;
- not generate geometry automatically;
- not change immutable factory defaults;
- not overwrite the saved user configuration until **Generate** is pressed;
- display a short sample description;
- validate the same public parameter schema used by normal configuration.

A future sample format may include metadata:

```json
{
  "Sample_Name": "Basic two-blade propeller",
  "Sample_Description": "A simple starting point for a compact propeller.",
  "Schema_Version": 1,
  "Parameters": {
    "Number_of_Blades": 2
  }
}
```

## Later possibilities

- schema-version migration for user configurations and samples;
- import/export buttons for sharing configurations;
- optional geometric quality diagnostics;
- automated regression models for representative configurations.
