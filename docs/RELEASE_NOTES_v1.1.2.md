# Elliptical NACA Propeller Generator v1.1.2

Version 1.1.2 is a packaging and documentation maintenance release. It does not change the validated geometry-generation pipeline introduced in versions 1.1.0 and 1.1.1.

## Generated Fusion examples

The release now includes:

```text
examples/Examples.f3d
```

This Autodesk Fusion document contains the propellers generated from all bundled configurations. It is intended as a visual and geometric reference and is not required for the add-in to run.

The file was moved from the repository root into a dedicated `examples/` directory. An accompanying `examples/README.md` explains its purpose and notes that the binary Fusion document should only be updated when the reference models materially change.

## Compatibility

- No parameter schema changes.
- No changes to `Prop_Direction`, `Sweep_Angle`, pitch, loft, Stitch, Boundary Fill, hub, spinner, or final-orientation behavior.
- Existing user configurations remain compatible.

## Installation

Install the add-in normally by copying the `EllipticalNACAPropellerGenerator` folder into the Autodesk Fusion add-ins directory. The `examples/` folder may remain in the installation package; Fusion does not require it for execution.
