# Configurations

Version 1.1 discovers configurations from two locations whenever the Fusion command
opens:

```text
Built in: <add-in folder>/configurations/
User:     <per-user configuration folder>/configurations/
```

The **Save current configuration** button writes a persistent user
configuration and refreshes the open drop-down immediately. Built-in
configurations remain unchanged. Existing JSON files in the former per-user
`samples/` directory are copied here on first discovery without overwriting
files already present.

Loading a configuration only fills the dialog. It does not generate geometry or
replace the last-run user configuration until **Generate** is pressed.

## Metadata wrapper

```json
{
  "Schema_Version": 1,
  "Sample_Name": "My propeller",
  "Sample_Description": "A useful starting point.",
  "Parameters": {
    "Number_of_Blades": 2,
    "Propeller_Diameter": 100
  }
}
```

Optional `Sample_Name_i18n` and `Sample_Description_i18n` objects may contain
translations keyed by locale: `en`, `pt-BR`, `es`, `fr`, `de`, and `ru`.

## Flat configuration

A normal flat configuration JSON is also accepted. The menu name is derived
from the filename unless `Sample_Name` is present.

## Validated v1.1 construction settings

All bundled configurations use:

```json
{
  "Loft_Construction_Mode": "split_trailing_edge",
  "Loft_Section_Order": "root_to_tip",
  "Loft_Guide_Rails": "none",
  "Loft_Merge_Tangent_Edges": true,
  "Blade_Finalization_Method": "boundary_fill",
  "Boundary_Fill_Diameter_Overlap_mm": 0.1
}
```

In split-trailing-edge mode, `Loft_Guide_Rails` controls only the open main
surface. The narrow trailing-edge loft always uses two rails through the exact
trailing-edge vertices.

When `Cut_Below_Hub_Base` is enabled, the two source surfaces are trimmed by
the XY plane before Stitch when required. Boundary Fill always includes the XY
plane in this workflow, even when no material crosses below `Z=0`.

Accepted section orders are `root_to_tip`, `tip_to_root`, and `automatic`.
Accepted main-surface guide modes are `none`, `distributed`, and
`dual_trailing_edge`. Closed-profile and legacy finalization settings remain
available for compatibility.

## Automatic robust settings

Automatic mode may additionally use:

```json
{
  "Loft_Quality_Check": true,
  "Loft_Quality_Max_Deviation_Percent": 0.1,
  "Loft_Quality_Max_Wave_Angle_Deg": 0.2,
  "Loft_Quality_Post_Fairing_Margin_Multiplier": 2.0,
  "Loft_Distributed_Rail_Placement": "uniform_chord"
}
```

Automatic mode treats the distributed-rail count as a search upper bound and
keeps a true maximum of 15 executed candidates, including overlap variants.

## Final orientation

Every configuration should explicitly include:

```json
"Propeller_Orientation": "standard"
```

Use `"flipped_180"` to reproduce the final transform used by
`demo_boatpropblades()`: `translate([0,0,Root_Length]) rotate([180,0,0])`.
This is a rigid assembly transform and does not change `Prop_Direction`,
`Sweep_Angle`, or geometric pitch. The validated default Stitch tolerance is
`0.1 mm`.
