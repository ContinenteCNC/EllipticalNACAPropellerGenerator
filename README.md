# Elliptical NACA Propeller Generator

[English](README.md) | [Português do Brasil](README.pt-BR.md)


A multilingual Autodesk Fusion add-in for generating complete parametric
propellers with elliptical blade planforms and smoothly transitioning NACA
4-digit airfoils.

Current release: **v1.1.2**

## Features

- One to twelve blades with clockwise or counter-clockwise geometry.
- Constant geometric pitch and configurable blade sweep.
- Ellipse-constrained chord distribution.
- Independent root, mid and tip NACA 4-digit profiles.
- Smooth nonlinear airfoil transitions and configurable root fairing.
- Finite trailing-edge thickness intended for manufacturable geometry.
- Automatic radial sections by spacing or slice count.
- Native Fusion surface loft, exact radial trims and stitched B-Rep solid.
- Hub, shaft hole, rectangular hoop, aerodynamic NACA ring, and optional parabolic or ogive spinner.
- Portuguese, English, Spanish, French, German and Russian interface.
- Automatic persistence of validated parameters, with immutable distributed defaults.
- Native **Generate** action closes the command after each committed run.
- Built-in and user-created JSON configurations, plus detailed manual-run JSON logs.
- Validated split trailing-edge loft with pre-Stitch XY trimming and Boundary Fill.
- Compact dialog using collapsible groups, per-run timeline organization, manual progress, and automatically discovered JSON configurations.

## Installation

Copy the complete `EllipticalNACAPropellerGenerator` folder to the Autodesk
Fusion add-ins directory, then restart Fusion.

Windows:

```text
%appdata%\Autodesk\Autodesk Fusion\API\AddIns
```

macOS:

```text
~/Library/Application Support/Autodesk/Autodesk Fusion/API/AddIns
```

The folder, Python entry file and manifest share the same base name:

```text
EllipticalNACAPropellerGenerator/
├── EllipticalNACAPropellerGenerator.py
└── EllipticalNACAPropellerGenerator.manifest
```

## Original project

The blade and spinner mathematics are derived from:

**Elliptical-blade NACA airfoil propeller library**  
Alex Matulich / Amatulic  
https://www.thingiverse.com/thing:5300828

The original author explains the design approach in:

https://www.nablu.com/2022/03/elliptical-blade-naca-airfoil-propeller.html

See [ATTRIBUTION.md](ATTRIBUTION.md),
[UPSTREAM_LICENSE.txt](UPSTREAM_LICENSE.txt) and
[docs/SOURCE_LINEAGE.md](docs/SOURCE_LINEAGE.md).

## Changes made in this port

The original OpenSCAD library creates faceted blade polyhedra and provides
parabolic and ogive spinner modules. This project reimplements the equations
in Python and adds a complete Autodesk Fusion workflow:

- smooth native B-Rep geometry;
- graphical and multilingual parameter interface;
- JSON presets;
- radial trimming and solid verification;
- blade pattern, hub and shaft hole;
- optional peripheral hoop;
- automatic spinner assembly.

Direct overlay tests showed that the OpenSCAD mesh vertices coincide with or
are tangent to the Fusion loft. Pitch, section profiles and sweep direction
were separately confirmed.

## Repository map

- `EllipticalNACAPropellerGenerator.py`: Fusion API adapter and construction.
- `propeller_math.py`: pure Python implementation of the upstream equations.
- `localization.py` and `locales/`: interface localization.
- `propeller_defaults.json`: immutable factory defaults.
- `configurations/`: bundled configurations; user configurations are stored per-user.
- `examples/Examples.f3d`: Fusion document containing all bundled configurations generated as models.
- `docs/GEOMETRY.md`: equations and coordinate conventions.
- `docs/FUSION_API_PIPELINE.md`: B-Rep construction sequence.
- `docs/LLM_CONTEXT.md`: compact maintainer context for humans and LLMs.
- `docs/ROADMAP.md`: planned post-1.0 development.

## Licensing

The repository combines original Python/Fusion implementation work with
adapted geometry and equations. The MIT grant in [LICENSE](LICENSE) applies
only to original contributions owned by this project. The upstream material
retains its Creative Commons attribution requirements. Read
[ATTRIBUTION.md](ATTRIBUTION.md) and
[UPSTREAM_LICENSE.txt](UPSTREAM_LICENSE.txt) together with the main license.


## Aerodynamic NACA ring

Version 0.20 formalizes the airfoil ring demonstrated inside the original
Thingiverse `demo_random()` module.

The upstream construction uses a NACA 0015 section by default, places its
trailing-edge reference line at the propeller-tip radius, rotates the section
so chord is axial, and revolves it 360 degrees around the shaft.

Parameters:

```text
Airfoil_Ring
Airfoil_Ring_NACA
Airfoil_Ring_Chord
Airfoil_Ring_Diameter
Airfoil_Ring_Axial_Offset
Airfoil_Ring_TE_Thickness
Airfoil_Ring_Profile_Points
```

A chord of zero enables the original automatic expression:

```text
min(20 mm, 0.5 * Propeller_Diameter * Max_Chord_Fraction)
```

The existing rectangular `Hoop` remains available as a separate feature.


### Interface organization

The command groups related parameters by purpose. Tip-ring and spinner
families each use one enable checkbox and one type selector, preventing
overlapping alternatives from being generated in the same run. Existing JSON
parameter names remain compatible.


### Automatic parameter persistence

Every validated parameter is saved automatically when **Generate** is pressed,
before Fusion starts constructing geometry. The immutable factory values remain
in `propeller_defaults.json`.

The last generated configuration is stored outside the repository and add-in
installation:

```text
Windows: %APPDATA%\EllipticalNACAPropellerGenerator\propeller_user_config.json
macOS:   ~/Library/Application Support/EllipticalNACAPropellerGenerator/propeller_user_config.json
```

It is restored when the command is opened again, including after Fusion is
restarted. Closing the dialog without generating does not save unexecuted
edits. The former factory-default action is now the built-in **3 × 1.25-inch
propeller — original configuration**, so every starting point is loaded through
the same Configurations workflow.

### Generation, progress and timeline organization

Version 1.1 uses Fusion's native **Generate** (OK) action. A successful or
handled manual run terminates the command, commits its single transaction, and
then displays the result. Open the command again for another run; the last
validated configuration is restored automatically.

Manual generation displays a separate cancelable progress dialog with the
current geometry stage. Automatic robust keeps its independent legacy/research
progress dialog. Cancellation is cooperative: a long Fusion kernel operation
finishes before the next checkpoint can observe the request.

The manual checkpoints call `adsk.doEvents()`, so the viewport and timeline can
show features as they are created. An earlier release candidate omitted these
UI checkpoints and therefore refreshed mostly at the end; that could feel
faster because it performed fewer redraws, but provided less useful feedback.
Progress text is wrapped to bounded-width lines so late-stage details do not
expand the dialog across the screen.

Only after the command transaction is committed are the new timeline items
grouped, collapsed, and named sequentially:

```text
Elliptical NACA Propeller 01
Elliptical NACA Propeller 02
...
```

The result message reports whether grouping succeeded, failed, or was skipped.
Grouping is performed by the global `commandTerminated` handler after commit;
this prevents later command cancellation from reverting visibility changes or
removing the group.

### Active component

Geometry is created in the component currently activated in Fusion. When the
root component is active, the propeller is created there. When a child
component is active, all sketches, features, bodies, hub, rings, and spinners
are created in that component definition. The result dialog reports the target
component name.

### Nested-component section paths

Wrapped section paths are created with the active component's
`Features.createPath` method. This preserves the component/assembly context of
3D sketch curves owned by nested components.

If a failed run commits only one timeline item, no standard timeline group is
attempted because Fusion requires at least two items. The final message reports
that condition without an additional API traceback.

## Version 1.0

Version 1.0 is the first public stable release. It promotes the fully tested
v0.21 codebase without changing the propeller mathematics or intended
geometry.

The release includes active-component generation, post-transaction timeline
groups, automatic parameter persistence, multilingual controls, tip-ring
alternatives, and spinner alternatives.

See [docs/RELEASE_NOTES_v1.0.0.md](docs/RELEASE_NOTES_v1.0.0.md) for the
release notes and [docs/ROADMAP.md](docs/ROADMAP.md) for planned development.

## Configurations

Version 1.1 discovers configurations from both the bundled
`configurations/` directory and a persistent per-user `configurations/`
directory. The **Configurations** group starts expanded. Existing user JSON
files under the former `samples/` directory are copied into the new directory
on first discovery without overwriting newer files.

The dialog can save the complete current configuration as a new user
configuration. The list refreshes immediately without restarting the command.
Loading a configuration fills the dialog but does not generate geometry or
overwrite the saved last-run configuration until **Generate** is pressed. The
former factory-default action is available as the built-in **3 × 1.25-inch
propeller — original configuration**.

Both metadata-wrapped and normal flat configuration JSON files are accepted.
See `configurations/README.md` for the schemas and storage locations.

### Validated split trailing-edge construction

The five design configurations validated in Fusion use the v1.1 defaults:

```text
Loft construction: Open main surface + separate trailing edge
Loft section order: Root to tip
Loft guides: None
Boundary overlap — diameter: 0.1 mm
```

The open NACA surface is lofted without the trailing-edge closure. A second
narrow loft closes the trailing edge and always uses two rails through the exact
trailing-edge vertices. When base cutting is requested, both surfaces are
trimmed by the XY plane before Stitch. Boundary Fill then uses the stitched
shell, the inner and outer cylinders, and the XY plane.

Closed-profile construction, distributed main-surface rails, reverse section
order, legacy finalization, and Automatic robust remain available as advanced
or compatibility options.

### Refreshing the version in Scripts and Add-Ins

Fusion reads the version shown before an add-in runs from the `.manifest`
file. Stop the add-in, replace the entire add-in folder—including the
manifest—and restart Fusion. Replacing only the Python file can leave the old
version visible in the Scripts and Add-Ins dialog.

### Boundary Fill solid finalization

Boundary Fill is now the default blade-solid workflow. The root section is
placed radially inward and the tip section radially outward by half of the
configured diameter overlap (default `0.1 mm`). Chord, pitch, sweep and
section interpolation still use the nominal radii. Nominal inner and outer
cylindrical surfaces plus the blade loft define the available cells. The add-in
selects the positive-volume cell with the largest volume and verifies that the
feature produced exactly one solid body.

In manual **Open main surface + separate trailing edge** construction, the
open NACA contour and the trailing-edge closure are lofted separately. The
trailing-edge loft always uses two rails through the exact trailing-edge
vertices. When `Cut_Below_Hub_Base` is enabled, both source surfaces are
trimmed together by the global XY plane before Stitch. Boundary Fill then uses
the stitched open shell, the nominal inner/outer cylinders, and the XY plane.
The XY plane is also included when there is no material below `Z=0`.

The closed-profile construction and the previous extend/trim/stitch workflow
remain as legacy Advanced Construction options.

### Distributed loft rails

Advanced Construction includes **Distributed profile rails**. The temporary
test policy is:

- accepted counts: `3, 5, 7, 9...`;
- temporary default: `9`;
- two rails anchor the upper and lower trailing-edge regions;
- one rail always follows the leading edge;
- every additional pair is distributed symmetrically over the upper and lower
  surfaces.

A temporary checkbox selects whether the first pair uses the exact
trailing-edge vertices or the first NACA profile points after those vertices.
The unchecked/default state uses the first points after the vertices. With
`N = Profile_Points`, the maximum is `2N+1` in vertex mode and `2N-1` in
first-point mode.

Manual Root-to-tip or Tip-to-root mode uses exactly the requested count.
Automatic robust mode starts without rails and then tries the odd progression
`3 -> 5 -> 7 -> 9 -> ... -> requested`, omitting duplicates and values above the request.
Dual trailing-edge rails remain an explicit experimental mode.

Generated spacing and slice distributions do not insert a mandatory station at
`Transition_Point`. The mid NACA profile still controls continuous
interpolation, but it does not create an unusually short loft interval.

The factory default and all bundled configurations use a Boundary Fill diameter overlap of `0.1 mm`, matching the validated v1.1 workflow.
Existing user overrides remain unchanged until **Generate** is pressed with a
new set of validated values.

### Automatic robust full-chain search and surface-quality metric

Automatic robust now evaluates complete candidates in isolated temporary
components before generating the accepted strategy in the active component.
For each loft direction and tangent-edge state it tests rail counts
`0, 3, 5, 7, 9...` through the selected maximum. A candidate must:

1. create a valid surface loft;
2. pass the theoretical-to-loft surface-quality threshold;
3. complete Boundary Fill when solid finalization is requested.

Quality is measured at the midpoint of every interior interval between section
profiles. The three worst intervals are also sampled at 25% and 75%. The global
maximum deviation, normalized by local chord, decides acceptance; RMS is
reported only as supporting diagnostics. This catches a wavy region even when
only half of the blade is affected.

```json
{
  "Loft_Quality_Check": true,
  "Loft_Quality_Max_Deviation_Percent": 0.1
}
```

The 0.1 value is a temporary 0.1%-of-local-chord calibration threshold. After a
loft passes quality, Boundary Fill starts with the configured overlap and
rebuilds the candidate at 10× increments up to a 0.1 mm diameter overlap.

### Part Design compatibility

Fusion's Part Design intent supports a single component. Robust preflight
therefore uses two isolation strategies:

- **Hybrid Design:** each candidate is created in a disposable hidden child
  component;
- **Part or Assembly Design:** each candidate is created in the active
  component, then removed by comparing entity tokens with a snapshot captured
  immediately before the attempt.

Cleanup runs in dependency order: Boundary Fill, cylinder extrusions, loft,
rail/section sketches, and orphan bodies. A cleanup mismatch aborts the search
instead of silently leaving diagnostic geometry in the user's model.

### Uniform-chord rails and wave-angle quality

The recommended placement is **Uniform along chord**. One rail follows the
leading edge and the remaining rails are paired at equal x/c locations on the
upper and lower surfaces.

Automatic robust treats the rail count as an upper limit but searches at least
`0 -> 3 -> 5 -> 7 -> 9` whenever resolution permits. Quality approval requires
both positional deviation and estimated short-period wave angle. The factory
wave-angle limit is `0.2°`.

### Cancelable robust search and diagnostic logs

Automatic robust displays a native Fusion progress dialog with a **Cancel
search** button. Cancellation is cooperative: it is checked while sections and
quality samples are being created and between kernel operations. A single long
Fusion kernel call must return before cancellation can be honored.

Every robust search writes two files under the per-user configuration folder:

```text
robust_search_logs/robust_search_<UTC timestamp>_<session>.json
robust_search_logs/robust_search_<UTC timestamp>_<session>.txt
```

The JSON file is intended for machine comparison. The text file contains the
same information in a readable form. Both retain all started candidates,
including partial cancelled attempts, stage timings, quality values, Boundary
Fill volumes, errors, and cleanup results.

### Progress-dialog behavior

The progress maximum counts distinct loft strategies only:

```text
section order × rail count × merge-tangent state
```

Boundary Fill overlap retries remain separate log attempts but do not inflate
the displayed strategy total. Closing the progress window is interpreted as
cancellation after it has appeared. The dialog shows compact status text; full
kernel messages remain in the saved logs.
