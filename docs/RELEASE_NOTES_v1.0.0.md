# Elliptical NACA Propeller Generator v1.0.0

First public stable release of the multilingual Autodesk Fusion add-in for
generating complete parametric elliptical NACA propellers.

## Highlights

- Native smooth Fusion B-Rep construction.
- One to twelve blades.
- Clockwise and counter-clockwise geometry.
- Root, mid, and tip NACA 4-digit profiles.
- Automatic or manual radial section distribution.
- Configurable pitch, sweep, chord distribution, fairing, and trailing edge.
- Hub and shaft hole.
- Rectangular or aerodynamic NACA tip ring.
- Parabolic or rounded-ogive spinner.
- Generation inside the currently active component, including nested child
  components.
- Collapsed sequential timeline group for each generation run.
- Automatic persistence of validated parameters.
- Restore-factory-defaults action.
- Interface in Portuguese, English, Spanish, French, German, and Russian.

## Installation

1. Download `EllipticalNACAPropellerGenerator_v1.0.0.zip`.
2. Extract the `EllipticalNACAPropellerGenerator` folder.
3. Copy that folder to the Autodesk Fusion add-ins directory.
4. Restart Fusion and open **Utilities → Add-Ins → Scripts and Add-Ins**.
5. Select the add-in and click **Run**.

Windows add-ins directory:

```text
%appdata%\Autodesk\Autodesk Fusion\API\AddIns
```

macOS add-ins directory:

```text
~/Library/Application Support/Autodesk/Autodesk Fusion/API/AddIns
```

## Source and attribution

The blade, airfoil-transition, and spinner mathematics are derived from Alex
Matulich's / Amatulic's **Elliptical-blade NACA airfoil propeller library**.

Read `ATTRIBUTION.md`, `UPSTREAM_LICENSE.txt`, `LICENSE`, and
`docs/SOURCE_LINEAGE.md` before redistributing adapted material.

## Safety notice

Generated propellers are not certified or validated for structural strength,
fatigue life, balance, rotational speed, impact safety, or aerodynamic
performance. The user is responsible for engineering validation, material
selection, manufacturing quality, balancing, containment, and safe testing.

## Compatibility

This release preserves the public JSON parameter keys used by the tested
v0.21.0 build. The release promotion contains no intended geometry change.

## Planned development

See `docs/ROADMAP.md` for the proposed adaptive section distribution and sample
configuration library.
