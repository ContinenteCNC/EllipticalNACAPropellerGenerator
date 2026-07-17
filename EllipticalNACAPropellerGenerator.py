"""
Elliptical NACA Propeller Generator for Autodesk Fusion
=======================================================

A multilingual parametric Autodesk Fusion add-in that generates complete
propellers from elliptical blade planforms and smoothly transitioning NACA
4-digit airfoil sections.

ORIGINAL SOURCE
---------------

The blade and spinner mathematics are a geometric port of:

    "Elliptical-blade NACA airfoil propeller library"
    by Alex Matulich / Amatulic
    https://www.thingiverse.com/thing:5300828

The original OpenSCAD source also identifies:

    https://www.printables.com/model/159163-
    elliptical-blade-naca-airfoil-propeller-library

The geometric approach is explained in detail in:

    "Elliptical-blade NACA airfoil propeller"
    Alex Matulich, March 25, 2022
    https://www.nablu.com/2022/03/
    elliptical-blade-naca-airfoil-propeller.html

The downloaded Thingiverse archive states that the original work is licensed
under "Creative Commons - Attribution". Its bundled LICENSE.txt does not state
a Creative Commons version. See ATTRIBUTION.md, UPSTREAM_LICENSE.txt and
LICENSE.

WHAT THIS PORT ADDS
-------------------

The original OpenSCAD library provides the blade generator and parabolic and
ogive spinner modules. This Fusion port preserves those equations while adding
a complete native CAD workflow and product interface:

    translated and grouped graphical interface
    -> persistent JSON presets
    -> automatic radial section distribution
    -> 3D section splines
    -> smooth surface loft
    -> natural root/tip extension
    -> exact analytical cylindrical trims
    -> stitched B-Rep blade solid
    -> printable base cut and axial offset
    -> circular blade pattern
    -> hub and shaft hole
    -> optional rectangular or aerodynamic airfoil ring
    -> optional spinner assembly
    -> final Join operations when bodies intersect

The OpenSCAD blade is a faceted polyhedron. Direct overlay tests performed
during development confirmed that its vertices coincide with, or are tangent
to, the smooth Fusion loft. Sweep_Angle was also validated by direct overlay.

IMPORTANT CONVENTIONS FOR MAINTAINERS AND LLMS
----------------------------------------------

* User-facing dimensions and all mathematical helpers use millimetres.
* Fusion's API returns and accepts length values internally in centimetres.
  Every API boundary must therefore convert mm <-> cm explicitly.
* propeller_math.py must remain independent of adsk so it can be tested outside
  Fusion.
* The first blade uses the Fusion coordinate system documented in
  docs/GEOMETRY.md. Do not change signs by visual intuition alone.
* Sweep_Angle intentionally has an extra sign inversion when mapped from the
  final OpenSCAD orientation to the Fusion orientation. This was experimentally
  verified; see sweep_origin_angle_deg().
* Root_Length is the upstream propblade() axial root constraint named hublen.
* The aerodynamic ring reproduces the NACA airfoil ring demonstrated in
  the original Thingiverse OpenSCAD demo_random() module.
  Hub_Length is a separate final cylindrical-hub parameter added by this port.
* The technical construction controls are kept in the GUI for diagnostics.
  Normal users generally should not need to change them.
* All localization keys must exist in all six locale JSON files.
* Geometry changes should be checked against an OpenSCAD solid overlay before
  being considered equivalent.

See docs/LLM_CONTEXT.md for the current architecture, verified behavior,
release procedure and known API pitfalls.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import adsk.core
import adsk.fusion
import json
import math
import os
import re
import sys
import traceback

try:
    from .localization import create_localizer
    from .propeller_math import (
        BladeConfig,
        airfoil_ring_profile_points,
        section_geometry,
        section_radii_from_slices,
        section_radii_from_spacing,
        sweep_origin_angle_deg,
        validate_radii,
        wrapped_section_geometry,
    )
except ImportError:
    from localization import create_localizer
    from propeller_math import (
        BladeConfig,
        airfoil_ring_profile_points,
        section_geometry,
        section_radii_from_slices,
        section_radii_from_spacing,
        sweep_origin_angle_deg,
        validate_radii,
        wrapped_section_geometry,
    )


APP = adsk.core.Application.get()
UI = APP.userInterface

BASE_DIRECTORY = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CONFIG_FILENAME = "propeller_defaults.json"
USER_CONFIG_FILENAME = "propeller_user_config.json"
LEGACY_CONFIG_FILENAME = "propeller_config.json"

DEFAULT_CONFIG_PATH = os.path.join(
    BASE_DIRECTORY,
    DEFAULT_CONFIG_FILENAME,
)
LEGACY_CONFIG_PATH = os.path.join(
    BASE_DIRECTORY,
    LEGACY_CONFIG_FILENAME,
)


def _platform_user_config_directory() -> str:
    """Return a stable per-user folder outside the add-in installation."""
    if sys.platform.startswith("win"):
        root = os.environ.get(
            "APPDATA",
            os.path.expanduser("~"),
        )
    elif sys.platform == "darwin":
        root = os.path.join(
            os.path.expanduser("~"),
            "Library",
            "Application Support",
        )
    else:
        root = os.environ.get(
            "XDG_CONFIG_HOME",
            os.path.join(os.path.expanduser("~"), ".config"),
        )

    return os.path.join(
        root,
        "EllipticalNACAPropellerGenerator",
    )


USER_CONFIG_DIRECTORY = _platform_user_config_directory()
USER_CONFIG_PATH = os.path.join(
    USER_CONFIG_DIRECTORY,
    USER_CONFIG_FILENAME,
)

_LOCALIZER = create_localizer(
    APP,
    BASE_DIRECTORY,
    (
        USER_CONFIG_PATH,
        LEGACY_CONFIG_PATH,
        DEFAULT_CONFIG_PATH,
    ),
)
_t = _LOCALIZER.text
ACTIVE_LOCALE = _LOCALIZER.locale_code

PROJECT_NAME = "Elliptical NACA Propeller Generator"
PROJECT_VERSION = "1.0.0"
UPSTREAM_SOURCES = {
    "thingiverse": "https://www.thingiverse.com/thing:5300828",
    "printables": (
        "https://www.printables.com/model/"
        "159163-elliptical-blade-naca-airfoil-propeller-library"
    ),
    "blog": (
        "https://www.nablu.com/2022/03/"
        "elliptical-blade-naca-airfoil-propeller.html"
    ),
}

CMD_ID = "bruno_elliptical_naca_propeller_generator_command"
CMD_NAME = f"{_t('command.name')} — v{PROJECT_VERSION}"
CMD_DESCRIPTION = _t("command.description")
WORKSPACE_ID = "FusionSolidEnvironment"
PANEL_IDS = ("SolidCreatePanel", "SolidScriptsAddinsPanel")

# Intentionally moderate default dialog size. The 460 px width reduces label
# truncation and the 620 px height keeps the native Generate and Cancel buttons
# visible on ordinary 1080p displays. Fusion may remember later user resizing,
# which is desirable once a safe initial size has been established.
DIALOG_INITIAL_WIDTH = 460
DIALOG_INITIAL_HEIGHT = 620
DIALOG_MINIMUM_WIDTH = 360
DIALOG_MINIMUM_HEIGHT = 400

_handlers: list[object] = []
_control = None

# One Fusion command can be active at a time. A successful execute handler
# stores its result here so timeline grouping and the final message occur only
# after UserInterface.commandTerminated fires and the transaction is committed.
_pending_timeline_run = None


# =============================================================================
# CONFIGURATION, LOCALIZATION AND COMMAND-INPUT HELPERS
#
# Functions in this block are deliberately small and side-effect free except
# for layered factory/user JSON loading. GUI lengths cross the Fusion API boundary
# here and are immediately converted from internal centimetres to millimetres.
# =============================================================================


def _read_config_object(path: str, description: str) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            f"O arquivo {description} deve conter um objeto JSON."
        )
    return data


def _load_factory_config() -> dict:
    """Load the immutable defaults distributed with the add-in."""
    return _read_config_object(
        DEFAULT_CONFIG_PATH,
        DEFAULT_CONFIG_FILENAME,
    )


def _load_raw_config() -> dict:
    """Load factory defaults overlaid by user or legacy configuration."""
    config = _load_factory_config()

    # The per-user file is authoritative. The legacy in-package file is read
    # only when updating from versions that predate split configuration.
    overlay_path = None
    if os.path.isfile(USER_CONFIG_PATH):
        overlay_path = USER_CONFIG_PATH
    elif os.path.isfile(LEGACY_CONFIG_PATH):
        overlay_path = LEGACY_CONFIG_PATH

    if overlay_path:
        try:
            config.update(
                _read_config_object(
                    overlay_path,
                    os.path.basename(overlay_path),
                )
            )
        except Exception:
            # Atomic writes make corruption unlikely. A malformed externally
            # edited user file must not prevent the command from opening.
            pass

    return config


def _delete_user_configuration() -> None:
    """Remove current and legacy user overrides."""
    for path in (USER_CONFIG_PATH, LEGACY_CONFIG_PATH):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except FileNotFoundError:
            pass


def _parse_radii(text: str) -> list[float]:
    # O separador recomendado é ponto e vírgula. Também são aceitos espaços e
    # vírgula seguida de espaço como separadores, preservando vírgula decimal.
    tokens = [
        token.strip()
        for token in re.split(r"\s*;\s*|,\s+(?=[+-]?\d)|\s+", text.strip())
        if token.strip()
    ]
    if not tokens:
        raise ValueError("Informe pelo menos um raio.")
    try:
        return [float(token.replace(",", ".")) for token in tokens]
    except ValueError as error:
        raise ValueError(
            "Não foi possível interpretar os raios. Separe os valores por "
            "ponto e vírgula, por exemplo: 4.15; 14.335; 38.1"
        ) from error


def _parse_float_text(value: object, label: str) -> float:
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError as error:
        raise ValueError(
            f"Não foi possível interpretar {label}: {value!r}."
        ) from error


def _find_command_input(
    inputs: adsk.core.CommandInputs,
    input_id: str,
):
    """Procura recursivamente um input, inclusive dentro de grupos."""
    direct = inputs.itemById(input_id)
    if direct:
        return direct

    for index in range(inputs.count):
        item = inputs.item(index)
        if not item:
            continue

        try:
            children = item.children
        except Exception:
            children = None

        if children:
            found = _find_command_input(children, input_id)
            if found:
                return found

    return None


def _required_command_input(
    inputs: adsk.core.CommandInputs,
    input_id: str,
):
    item = _find_command_input(inputs, input_id)
    if not item:
        raise RuntimeError(
            f"Input interno não encontrado na janela: {input_id}."
        )
    return item


def _value_input_mm(
    inputs: adsk.core.CommandInputs,
    input_id: str,
) -> float:
    # ValueCommandInput devolve comprimentos em cm, unidade interna do Fusion.
    return float(_required_command_input(inputs, input_id).value) * 10.0


def _string_input_value(
    inputs: adsk.core.CommandInputs,
    input_id: str,
) -> str:
    return str(_required_command_input(inputs, input_id).value).strip()


def _selected_dropdown_name(
    inputs: adsk.core.CommandInputs,
    input_id: str,
) -> str:
    drop_down = adsk.core.DropDownCommandInput.cast(
        _required_command_input(inputs, input_id)
    )
    if not drop_down or not drop_down.selectedItem:
        raise ValueError(f"Selecione uma opção em {input_id}.")
    return drop_down.selectedItem.name


def _collect_blade_config_overrides(
    inputs: adsk.core.CommandInputs,
    profile_points: int,
) -> dict:
    return {
        "Propeller_Diameter": _value_input_mm(inputs, "propellerDiameter"),
        "Hub_Diameter": _value_input_mm(inputs, "hubDiameter"),
        "Blade_Pitch": _value_input_mm(inputs, "bladePitch"),
        "Max_Chord_Fraction": _parse_float_text(
            _string_input_value(inputs, "maxChordFraction"),
            "Max_Chord_Fraction",
        ),
        "Root_Length": _value_input_mm(inputs, "rootLength"),
        "Elen_Fraction": _parse_float_text(
            _string_input_value(inputs, "elenFraction"),
            "Elen_Fraction",
        ),
        "Prop_Direction": int(
            _selected_dropdown_name(inputs, "propDirection")
        ),
        "Centerline": _parse_float_text(
            _string_input_value(inputs, "centerline"),
            "Centerline",
        ),
        "Sweep_Angle": _parse_float_text(
            _string_input_value(inputs, "sweepAngle"),
            "Sweep_Angle",
        ),
        "Trailing_Edge_Thickness": _value_input_mm(
            inputs,
            "trailingEdgeThickness",
        ),
        "Fairing_Size": _value_input_mm(inputs, "fairingSize"),
        "Root_NACA_Airfoil": _string_input_value(inputs, "rootNaca"),
        "Mid_NACA_Airfoil": _string_input_value(inputs, "midNaca"),
        "Tip_NACA_Airfoil": _string_input_value(inputs, "tipNaca"),
        "Transition_Point": _parse_float_text(
            _string_input_value(inputs, "transitionPoint"),
            "Transition_Point",
        ),
        "Profile_Points": int(profile_points),
    }



def _collect_final_assembly_parameters(
    inputs: adsk.core.CommandInputs,
) -> dict:
    number_of_blades = int(
        _required_command_input(inputs, "numberOfBlades").value
    )
    if number_of_blades < 1:
        raise ValueError("Number_of_Blades deve ser pelo menos 1.")

    hub_length_mm = _value_input_mm(inputs, "hubLength")
    hole_diameter_mm = _value_input_mm(inputs, "holeDiameter")
    prop_z_offset_mm = _value_input_mm(inputs, "propZOffset")

    create_tip_ring = bool(
        _required_command_input(inputs, "createTipRing").value
    )
    tip_ring_type = _selected_dropdown_name(inputs, "tipRingType")
    create_hoop = (
        create_tip_ring
        and tip_ring_type == TIP_RING_TYPE_RECTANGULAR
    )
    create_airfoil_ring = (
        create_tip_ring
        and tip_ring_type == TIP_RING_TYPE_AERODYNAMIC
    )

    hoop_thickness_mm = _value_input_mm(inputs, "hoopThickness")
    hoop_height_mm = _value_input_mm(inputs, "hoopHeight")
    hoop_offset_mm = _value_input_mm(inputs, "hoopOffset")

    airfoil_ring_naca = _string_input_value(
        inputs,
        "airfoilRingNaca",
    )
    airfoil_ring_chord_mm = _value_input_mm(
        inputs,
        "airfoilRingChord",
    )
    airfoil_ring_diameter_mm = _value_input_mm(
        inputs,
        "airfoilRingDiameter",
    )
    airfoil_ring_axial_offset_mm = _value_input_mm(
        inputs,
        "airfoilRingAxialOffset",
    )
    airfoil_ring_te_thickness_mm = _value_input_mm(
        inputs,
        "airfoilRingTeThickness",
    )
    airfoil_ring_profile_points = int(
        _required_command_input(
            inputs,
            "airfoilRingProfilePoints",
        ).value
    )

    create_spinner = bool(
        _required_command_input(inputs, "createSpinner").value
    )
    spinner_type = _selected_dropdown_name(inputs, "spinnerType")
    create_parabolic_spinner = (
        create_spinner
        and spinner_type == SPINNER_TYPE_PARABOLIC
    )
    create_ogive_spinner = (
        create_spinner
        and spinner_type == SPINNER_TYPE_OGIVE
    )

    spinner_diameter_mm = _value_input_mm(inputs, "spinnerDiameter")
    spinner_length_mm = _value_input_mm(inputs, "spinnerLength")
    ogive_spinner_diameter_mm = _value_input_mm(
        inputs,
        "ogiveSpinnerDiameter",
    )
    ogive_spinner_length_mm = _value_input_mm(
        inputs,
        "ogiveSpinnerLength",
    )
    nose_radius_fraction = _parse_float_text(
        _string_input_value(inputs, "noseRadius"),
        "Nose_Radius",
    )

    if hub_length_mm <= 0.0:
        raise ValueError("Hub_Length deve ser positivo.")
    if hole_diameter_mm < 0.0:
        raise ValueError("Hole_Diameter não pode ser negativo.")

    if create_hoop:
        if hoop_thickness_mm <= 0.0:
            raise ValueError("Hoop_Thickness deve ser positivo.")
        if hoop_height_mm <= 0.0:
            raise ValueError("Hoop_Height deve ser positivo.")

    if create_airfoil_ring:
        normalize_ring_naca = re.sub(r"\s+", "", airfoil_ring_naca)
        if not (
            len(normalize_ring_naca) == 4
            and normalize_ring_naca.isdigit()
        ):
            raise ValueError(
                "Airfoil_Ring_NACA deve conter quatro dígitos."
            )
        if airfoil_ring_chord_mm < 0.0:
            raise ValueError(
                "Airfoil_Ring_Chord deve ser zero (automático) "
                "ou positivo."
            )
        if airfoil_ring_diameter_mm <= 0.0:
            raise ValueError(
                "Airfoil_Ring_Diameter deve ser positivo."
            )
        if airfoil_ring_te_thickness_mm < 0.0:
            raise ValueError(
                "Airfoil_Ring_TE_Thickness não pode ser negativa."
            )
        if airfoil_ring_profile_points < 2:
            raise ValueError(
                "Airfoil_Ring_Profile_Points deve ser pelo menos 2."
            )

    if create_parabolic_spinner:
        if spinner_diameter_mm <= 0.0:
            raise ValueError("Spinner_Diameter deve ser positivo.")
        if spinner_length_mm <= 0.0:
            raise ValueError("Spinner_Length deve ser positivo.")
        if hole_diameter_mm >= spinner_diameter_mm:
            raise ValueError(
                "Hole_Diameter deve ser menor que Spinner_Diameter."
            )

    if create_ogive_spinner:
        if ogive_spinner_diameter_mm <= 0.0:
            raise ValueError("Ogive_Spinner_Diameter deve ser positivo.")
        if ogive_spinner_length_mm <= 0.0:
            raise ValueError("Ogive_Spinner_Length deve ser positivo.")
        if hole_diameter_mm >= ogive_spinner_diameter_mm:
            raise ValueError(
                "Hole_Diameter deve ser menor que Ogive_Spinner_Diameter."
            )
        if not 0.0 < nose_radius_fraction < 0.25:
            raise ValueError(
                "Nose_Radius deve ser maior que zero e menor que 0,25."
            )
        if ogive_spinner_length_mm <= 0.5 * ogive_spinner_diameter_mm:
            raise ValueError(
                "Para reproduzir a ogiva do SCAD, Ogive_Spinner_Length deve "
                "ser maior que metade de Ogive_Spinner_Diameter."
            )

    return {
        "number_of_blades": number_of_blades,
        "hub_length_mm": hub_length_mm,
        "hole_diameter_mm": hole_diameter_mm,
        "prop_z_offset_mm": prop_z_offset_mm,
        "cut_below_hub_base": bool(
            _required_command_input(inputs, "cutBelowHubBase").value
        ),
        "create_blade_pattern": bool(
            _required_command_input(inputs, "createBladePattern").value
        ),
        "create_hub_and_join": bool(
            _required_command_input(inputs, "createHubAndJoin").value
        ),
        "create_hoop": create_hoop,
        "hoop_thickness_mm": hoop_thickness_mm,
        "hoop_height_mm": hoop_height_mm,
        "hoop_offset_mm": hoop_offset_mm,
        "create_airfoil_ring": create_airfoil_ring,
        "airfoil_ring_naca": re.sub(
            r"\s+",
            "",
            airfoil_ring_naca,
        ).zfill(4),
        "airfoil_ring_chord_mm": airfoil_ring_chord_mm,
        "airfoil_ring_diameter_mm": airfoil_ring_diameter_mm,
        "airfoil_ring_axial_offset_mm": (
            airfoil_ring_axial_offset_mm
        ),
        "airfoil_ring_te_thickness_mm": (
            airfoil_ring_te_thickness_mm
        ),
        "airfoil_ring_profile_points": (
            airfoil_ring_profile_points
        ),
        "create_parabolic_spinner": create_parabolic_spinner,
        "spinner_diameter_mm": spinner_diameter_mm,
        "spinner_length_mm": spinner_length_mm,
        "create_ogive_spinner": create_ogive_spinner,
        "ogive_spinner_diameter_mm": ogive_spinner_diameter_mm,
        "ogive_spinner_length_mm": ogive_spinner_length_mm,
        "nose_radius_fraction": nose_radius_fraction,
    }


# =============================================================================
# PERSISTED PRESETS AND DIALOG STATE
#
# Generate serializes every validated visible parameter to the per-user JSON
# before geometry construction. Factory defaults remain immutable and can be
# restored from the button at the top of the dialog. Interface_Language is
# preserved because localization is selected before the dialog exists.
# =============================================================================


def _radius_distribution_mode_to_storage(mode: str) -> str:
    if mode == RADIUS_MODE_MANUAL:
        return "manual"
    if mode == RADIUS_MODE_SPACING:
        return "spacing"
    if mode == RADIUS_MODE_SLICES:
        return "slices"
    raise ValueError(
        f"Modo de distribuição radial desconhecido: {mode!r}."
    )


def _section_mode_to_storage(mode: str) -> str:
    if mode == MODE_FLAT:
        return "flat_2d"
    if mode == MODE_WRAPPED:
        return "wrapped_3d"
    raise ValueError(f"Modo de seção desconhecido: {mode!r}.")


def _collect_current_config(
    inputs: adsk.core.CommandInputs,
) -> dict:
    """Lê todos os inputs da janela e produz o JSON de configuração.

    O arquivo existente é usado como base para preservar opções que não fazem
    parte da janela, especialmente Interface_Language.
    """
    profile_points = int(
        _required_command_input(inputs, "profilePoints").value
    )
    blade_values = _collect_blade_config_overrides(
        inputs,
        profile_points,
    )
    assembly = _collect_final_assembly_parameters(inputs)

    radius_mode = _selected_dropdown_name(
        inputs,
        "radiusDistributionMode",
    )
    section_mode = _selected_dropdown_name(inputs, "sectionMode")

    config = _load_raw_config()
    config.update(blade_values)

    # A lista manual só é validada e substituída quando esse modo está ativo.
    # Nos modos automáticos, ela permanece disponível como preset alternativo.
    if radius_mode == RADIUS_MODE_MANUAL:
        config["Section_Radii"] = _parse_radii(
            _string_input_value(inputs, "radii")
        )

    config.update(
        {
            "Apply_Geometric_Angle": bool(
                _required_command_input(inputs, "applyAngle").value
            ),
            "Section_Mode": _section_mode_to_storage(section_mode),
            "Create_Surface_Loft": bool(
                _required_command_input(inputs, "createSurfaceLoft").value
            ),
            "Extend_Surface_Ends": bool(
                _required_command_input(inputs, "extendSurfaceEnds").value
            ),
            "Surface_Extension_mm": _value_input_mm(
                inputs,
                "extensionDistance",
            ),
            "Create_Limit_Cylinders": bool(
                _required_command_input(
                    inputs,
                    "createLimitCylinders",
                ).value
            ),
            "Cylinder_Axial_Margin_mm": _value_input_mm(
                inputs,
                "cylinderAxialMargin",
            ),
            "Finalize_Solid": bool(
                _required_command_input(inputs, "finalizeSolid").value
            ),
            "Stitch_Tolerance_mm": _value_input_mm(
                inputs,
                "stitchTolerance",
            ),
            "Hide_Created_Sketches": bool(
                _required_command_input(
                    inputs,
                    "hideCreatedSketches",
                ).value
            ),
            "Number_of_Blades": assembly["number_of_blades"],
            "Hub_Length": assembly["hub_length_mm"],
            "Hole_Diameter": assembly["hole_diameter_mm"],
            "Prop_Z_Offset": assembly["prop_z_offset_mm"],
            "Cut_Below_Hub_Base": assembly["cut_below_hub_base"],
            "Create_Blade_Pattern": assembly["create_blade_pattern"],
            "Create_Hub_And_Join": assembly["create_hub_and_join"],
            "Section_Distribution_Mode": (
                _radius_distribution_mode_to_storage(radius_mode)
            ),
            "Section_Spacing_mm": _value_input_mm(
                inputs,
                "sectionSpacing",
            ),
            "Section_Slices": int(
                _required_command_input(inputs, "sectionSlices").value
            ),
            "Hoop": assembly["create_hoop"],
            "Hoop_Thickness": assembly["hoop_thickness_mm"],
            "Hoop_Height": assembly["hoop_height_mm"],
            "Hoop_Offset": assembly["hoop_offset_mm"],
            "Airfoil_Ring": assembly["create_airfoil_ring"],
            "Airfoil_Ring_NACA": assembly["airfoil_ring_naca"],
            "Airfoil_Ring_Chord": (
                assembly["airfoil_ring_chord_mm"]
            ),
            "Airfoil_Ring_Diameter": (
                assembly["airfoil_ring_diameter_mm"]
            ),
            "Airfoil_Ring_Axial_Offset": (
                assembly["airfoil_ring_axial_offset_mm"]
            ),
            "Airfoil_Ring_TE_Thickness": (
                assembly["airfoil_ring_te_thickness_mm"]
            ),
            "Airfoil_Ring_Profile_Points": (
                assembly["airfoil_ring_profile_points"]
            ),
            "Parabolic_Spinner_Yes": (
                assembly["create_parabolic_spinner"]
            ),
            "Spinner_Diameter": assembly["spinner_diameter_mm"],
            "Spinner_Length": assembly["spinner_length_mm"],
            "Ogive_Spinner_Yes": assembly["create_ogive_spinner"],
            "Ogive_Spinner_Diameter": (
                assembly["ogive_spinner_diameter_mm"]
            ),
            "Ogive_Spinner_Length": (
                assembly["ogive_spinner_length_mm"]
            ),
            "Nose_Radius": assembly["nose_radius_fraction"],
        }
    )
    return config


def _write_user_config_atomically(config: dict) -> None:
    """Replace the user JSON only after the complete file is durable."""
    os.makedirs(USER_CONFIG_DIRECTORY, exist_ok=True)
    temporary_path = USER_CONFIG_PATH + ".tmp"

    try:
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(
                config,
                file,
                indent=2,
                ensure_ascii=False,
            )
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, USER_CONFIG_PATH)
    except Exception:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except Exception:
            pass
        raise


def _save_current_config(
    inputs: adsk.core.CommandInputs,
) -> None:
    config = _collect_current_config(inputs)
    _write_user_config_atomically(config)


RADIUS_MODE_MANUAL = _t("radius.manual")
RADIUS_MODE_SPACING = _t("radius.spacing")
RADIUS_MODE_SLICES = _t("radius.slices")

TIP_RING_TYPE_RECTANGULAR = _t("tip_ring.rectangular")
TIP_RING_TYPE_AERODYNAMIC = _t("tip_ring.aerodynamic")

SPINNER_TYPE_PARABOLIC = _t("spinner_type.parabolic")
SPINNER_TYPE_OGIVE = _t("spinner_type.ogive")


def _normalize_radius_distribution_mode(value: object) -> str:
    normalized = str(value).strip().lower()
    aliases = {
        "manual": RADIUS_MODE_MANUAL,
        "list": RADIUS_MODE_MANUAL,
        "lista": RADIUS_MODE_MANUAL,
        "lista manual": RADIUS_MODE_MANUAL,
        "spacing": RADIUS_MODE_SPACING,
        "space": RADIUS_MODE_SPACING,
        "espacamento": RADIUS_MODE_SPACING,
        "espaçamento": RADIUS_MODE_SPACING,
        "espacamento radial": RADIUS_MODE_SPACING,
        "espaçamento radial": RADIUS_MODE_SPACING,
        "slices": RADIUS_MODE_SLICES,
        "slice": RADIUS_MODE_SLICES,
        "quantidade de slices": RADIUS_MODE_SLICES,
        "manual list": RADIUS_MODE_MANUAL,
        "lista manual": RADIUS_MODE_MANUAL,
        "liste manuelle": RADIUS_MODE_MANUAL,
        "manuelle liste": RADIUS_MODE_MANUAL,
        "ручной список": RADIUS_MODE_MANUAL,
        "radial spacing": RADIUS_MODE_SPACING,
        "espaciado radial": RADIUS_MODE_SPACING,
        "espacement radial": RADIUS_MODE_SPACING,
        "radialer abstand": RADIUS_MODE_SPACING,
        "радиальный шаг": RADIUS_MODE_SPACING,
        "number of slices": RADIUS_MODE_SLICES,
        "cantidad de slices": RADIUS_MODE_SLICES,
        "nombre de tranches": RADIUS_MODE_SLICES,
        "anzahl der slices": RADIUS_MODE_SLICES,
        "количество срезов": RADIUS_MODE_SLICES,
        RADIUS_MODE_MANUAL.lower(): RADIUS_MODE_MANUAL,
        RADIUS_MODE_SPACING.lower(): RADIUS_MODE_SPACING,
        RADIUS_MODE_SLICES.lower(): RADIUS_MODE_SLICES,
    }
    return aliases.get(normalized, RADIUS_MODE_MANUAL)


def _resolve_section_radii(
    config: BladeConfig,
    distribution_mode: str,
    manual_text: str,
    spacing_mm: float,
    slices: int,
) -> list[float]:
    if distribution_mode == RADIUS_MODE_MANUAL:
        return validate_radii(config, _parse_radii(manual_text))
    if distribution_mode == RADIUS_MODE_SPACING:
        return section_radii_from_spacing(config, spacing_mm)
    if distribution_mode == RADIUS_MODE_SLICES:
        return section_radii_from_slices(config, slices)
    raise ValueError(
        f"Modo de distribuição radial desconhecido: {distribution_mode!r}."
    )


def _update_radius_distribution_inputs(
    inputs: adsk.core.CommandInputs,
) -> None:
    mode = _selected_dropdown_name(inputs, "radiusDistributionMode")
    _required_command_input(inputs, "radii").isEnabled = (
        mode == RADIUS_MODE_MANUAL
    )
    _required_command_input(inputs, "sectionSpacing").isEnabled = (
        mode == RADIUS_MODE_SPACING
    )
    _required_command_input(inputs, "sectionSlices").isEnabled = (
        mode == RADIUS_MODE_SLICES
    )


def _update_tip_ring_inputs(
    inputs: adsk.core.CommandInputs,
) -> None:
    create_enabled = bool(
        _required_command_input(inputs, "createTipRing").value
    )
    ring_type_input = _required_command_input(inputs, "tipRingType")
    ring_type_input.isEnabled = create_enabled

    selected_type = _selected_dropdown_name(inputs, "tipRingType")
    rectangular_enabled = (
        create_enabled
        and selected_type == TIP_RING_TYPE_RECTANGULAR
    )
    aerodynamic_enabled = (
        create_enabled
        and selected_type == TIP_RING_TYPE_AERODYNAMIC
    )

    for input_id in (
        "hoopThickness",
        "hoopHeight",
        "hoopOffset",
    ):
        _required_command_input(inputs, input_id).isEnabled = (
            rectangular_enabled
        )

    for input_id in (
        "airfoilRingNaca",
        "airfoilRingChord",
        "airfoilRingDiameter",
        "airfoilRingAxialOffset",
        "airfoilRingTeThickness",
        "airfoilRingProfilePoints",
    ):
        _required_command_input(inputs, input_id).isEnabled = (
            aerodynamic_enabled
        )


def _update_spinner_inputs(
    inputs: adsk.core.CommandInputs,
) -> None:
    create_enabled = bool(
        _required_command_input(inputs, "createSpinner").value
    )
    spinner_type_input = _required_command_input(inputs, "spinnerType")
    spinner_type_input.isEnabled = create_enabled

    selected_type = _selected_dropdown_name(inputs, "spinnerType")
    parabolic_enabled = (
        create_enabled
        and selected_type == SPINNER_TYPE_PARABOLIC
    )
    ogive_enabled = (
        create_enabled
        and selected_type == SPINNER_TYPE_OGIVE
    )

    for input_id in ("spinnerDiameter", "spinnerLength"):
        _required_command_input(inputs, input_id).isEnabled = (
            parabolic_enabled
        )

    for input_id in (
        "ogiveSpinnerDiameter",
        "ogiveSpinnerLength",
        "noseRadius",
    ):
        _required_command_input(inputs, input_id).isEnabled = ogive_enabled


MODE_FLAT = _t("mode.flat")
MODE_WRAPPED = _t("mode.wrapped")


def _set_value_input_mm(
    inputs: adsk.core.CommandInputs,
    input_id: str,
    value: object,
) -> None:
    item = adsk.core.ValueCommandInput.cast(
        _required_command_input(inputs, input_id)
    )
    if not item:
        raise RuntimeError(f"{input_id} não é um ValueCommandInput.")
    item.expression = f"{float(value):g} mm"


def _set_string_input(
    inputs: adsk.core.CommandInputs,
    input_id: str,
    value: object,
) -> None:
    item = adsk.core.StringValueCommandInput.cast(
        _required_command_input(inputs, input_id)
    )
    if not item:
        raise RuntimeError(f"{input_id} não é um StringValueCommandInput.")
    item.value = str(value)


def _set_integer_input(
    inputs: adsk.core.CommandInputs,
    input_id: str,
    value: object,
) -> None:
    item = adsk.core.IntegerSpinnerCommandInput.cast(
        _required_command_input(inputs, input_id)
    )
    if not item:
        raise RuntimeError(f"{input_id} não é um IntegerSpinnerCommandInput.")
    item.value = int(value)


def _set_bool_input(
    inputs: adsk.core.CommandInputs,
    input_id: str,
    value: object,
) -> None:
    item = adsk.core.BoolValueCommandInput.cast(
        _required_command_input(inputs, input_id)
    )
    if not item:
        raise RuntimeError(f"{input_id} não é um BoolValueCommandInput.")
    item.value = bool(value)


def _select_dropdown_item(
    inputs: adsk.core.CommandInputs,
    input_id: str,
    item_name: str,
) -> None:
    drop_down = adsk.core.DropDownCommandInput.cast(
        _required_command_input(inputs, input_id)
    )
    if not drop_down:
        raise RuntimeError(f"{input_id} não é um DropDownCommandInput.")

    for index in range(drop_down.listItems.count):
        item = drop_down.listItems.item(index)
        if item and item.name == item_name:
            item.isSelected = True
            return

    raise ValueError(
        f"Opção {item_name!r} não encontrada em {input_id}."
    )


def _apply_config_to_dialog(
    inputs: adsk.core.CommandInputs,
    config: dict,
) -> None:
    """Apply a complete stored configuration to the current command dialog."""
    _set_integer_input(
        inputs,
        "numberOfBlades",
        max(1, min(12, int(config.get("Number_of_Blades", 2)))),
    )
    _set_value_input_mm(
        inputs,
        "propellerDiameter",
        config["Propeller_Diameter"],
    )
    _set_value_input_mm(inputs, "bladePitch", config["Blade_Pitch"])
    _select_dropdown_item(
        inputs,
        "propDirection",
        "+1" if int(config.get("Prop_Direction", -1)) == 1 else "-1",
    )
    _set_value_input_mm(
        inputs,
        "propZOffset",
        config.get("Prop_Z_Offset", 0.0),
    )
    _set_string_input(
        inputs,
        "maxChordFraction",
        f"{float(config['Max_Chord_Fraction']):g}",
    )
    _set_value_input_mm(inputs, "rootLength", config["Root_Length"])
    _set_string_input(
        inputs,
        "elenFraction",
        f"{float(config['Elen_Fraction']):g}",
    )
    _set_string_input(
        inputs,
        "sweepAngle",
        f"{float(config.get('Sweep_Angle', 0.0)):g}",
    )

    _set_string_input(
        inputs,
        "rootNaca",
        str(config["Root_NACA_Airfoil"]).zfill(4),
    )
    _set_string_input(
        inputs,
        "midNaca",
        str(config["Mid_NACA_Airfoil"]).zfill(4),
    )
    _set_string_input(
        inputs,
        "tipNaca",
        str(config["Tip_NACA_Airfoil"]).zfill(4),
    )
    _set_string_input(
        inputs,
        "transitionPoint",
        f"{float(config['Transition_Point']):g}",
    )
    _set_value_input_mm(
        inputs,
        "trailingEdgeThickness",
        config["Trailing_Edge_Thickness"],
    )
    _set_value_input_mm(inputs, "fairingSize", config["Fairing_Size"])

    _set_bool_input(
        inputs,
        "createHubAndJoin",
        config.get("Create_Hub_And_Join", True),
    )
    _set_value_input_mm(inputs, "hubDiameter", config["Hub_Diameter"])
    _set_value_input_mm(
        inputs,
        "hubLength",
        config.get("Hub_Length", 5.0),
    )
    _set_value_input_mm(
        inputs,
        "holeDiameter",
        config.get("Hole_Diameter", 3.0),
    )

    profile_points = int(config.get("Profile_Points", 41))
    if profile_points == 0:
        profile_points = 41
    _set_integer_input(
        inputs,
        "profilePoints",
        max(2, min(401, profile_points)),
    )

    radius_mode = _normalize_radius_distribution_mode(
        config.get("Section_Distribution_Mode", "spacing")
    )
    _select_dropdown_item(
        inputs,
        "radiusDistributionMode",
        radius_mode,
    )

    radii = config.get(
        "Section_Radii",
        [4.15, 5.15, 6.15, 7.15, 8.15, 14.335, 38.1],
    )
    _set_string_input(
        inputs,
        "radii",
        "; ".join(f"{float(value):g}" for value in radii),
    )
    spacing_mm = float(config.get("Section_Spacing_mm", 1.0))
    _set_value_input_mm(inputs, "sectionSpacing", spacing_mm)

    default_blade_length_mm = 0.5 * (
        float(config["Propeller_Diameter"])
        - float(config["Hub_Diameter"])
    )
    slices = int(
        config.get(
            "Section_Slices",
            max(
                1,
                round(
                    default_blade_length_mm
                    / max(spacing_mm, 1e-9)
                ),
            ),
        )
    )
    _set_integer_input(
        inputs,
        "sectionSlices",
        max(1, min(998, slices)),
    )

    create_hoop = bool(config.get("Hoop", False))
    create_airfoil_ring = bool(config.get("Airfoil_Ring", False))
    create_tip_ring = create_hoop or create_airfoil_ring
    _set_bool_input(inputs, "createTipRing", create_tip_ring)
    _select_dropdown_item(
        inputs,
        "tipRingType",
        (
            TIP_RING_TYPE_AERODYNAMIC
            if create_airfoil_ring and not create_hoop
            else TIP_RING_TYPE_RECTANGULAR
        ),
    )
    _set_value_input_mm(
        inputs,
        "hoopThickness",
        config.get("Hoop_Thickness", 1.2),
    )
    _set_value_input_mm(
        inputs,
        "hoopHeight",
        config.get("Hoop_Height", 6.0),
    )
    _set_value_input_mm(
        inputs,
        "hoopOffset",
        config.get("Hoop_Offset", 0.0),
    )
    _set_string_input(
        inputs,
        "airfoilRingNaca",
        str(config.get("Airfoil_Ring_NACA", "0015")).zfill(4),
    )
    _set_value_input_mm(
        inputs,
        "airfoilRingChord",
        config.get("Airfoil_Ring_Chord", 0.0),
    )
    _set_value_input_mm(
        inputs,
        "airfoilRingDiameter",
        config.get(
            "Airfoil_Ring_Diameter",
            config["Propeller_Diameter"],
        ),
    )
    _set_value_input_mm(
        inputs,
        "airfoilRingAxialOffset",
        config.get("Airfoil_Ring_Axial_Offset", 0.0),
    )
    _set_value_input_mm(
        inputs,
        "airfoilRingTeThickness",
        config.get("Airfoil_Ring_TE_Thickness", 0.4),
    )
    _set_integer_input(
        inputs,
        "airfoilRingProfilePoints",
        max(
            2,
            min(
                200,
                int(config.get("Airfoil_Ring_Profile_Points", 20)),
            ),
        ),
    )

    parabolic = bool(config.get("Parabolic_Spinner_Yes", False))
    ogive = bool(config.get("Ogive_Spinner_Yes", False))
    create_spinner = parabolic or ogive
    _set_bool_input(inputs, "createSpinner", create_spinner)
    _select_dropdown_item(
        inputs,
        "spinnerType",
        (
            SPINNER_TYPE_OGIVE
            if ogive and not parabolic
            else SPINNER_TYPE_PARABOLIC
        ),
    )
    _set_value_input_mm(
        inputs,
        "spinnerDiameter",
        config.get("Spinner_Diameter", 20.0),
    )
    _set_value_input_mm(
        inputs,
        "spinnerLength",
        config.get("Spinner_Length", 20.0),
    )
    _set_value_input_mm(
        inputs,
        "ogiveSpinnerDiameter",
        config.get("Ogive_Spinner_Diameter", 20.0),
    )
    _set_value_input_mm(
        inputs,
        "ogiveSpinnerLength",
        config.get("Ogive_Spinner_Length", 20.0),
    )
    _set_string_input(
        inputs,
        "noseRadius",
        f"{float(config.get('Nose_Radius', 0.24)):g}",
    )

    _set_bool_input(
        inputs,
        "hideCreatedSketches",
        config.get("Hide_Created_Sketches", True),
    )

    raw_section_mode = str(
        config.get("Section_Mode", "wrapped_3d")
    ).strip().lower()
    _select_dropdown_item(
        inputs,
        "sectionMode",
        (
            MODE_FLAT
            if raw_section_mode in {"flat", "flat_2d", "2d", "planar"}
            else MODE_WRAPPED
        ),
    )
    _set_bool_input(
        inputs,
        "applyAngle",
        config.get("Apply_Geometric_Angle", True),
    )
    _set_string_input(
        inputs,
        "centerline",
        f"{float(config.get('Centerline', 1.0)):g}",
    )
    _set_bool_input(
        inputs,
        "createSurfaceLoft",
        config.get("Create_Surface_Loft", True),
    )
    _set_bool_input(
        inputs,
        "extendSurfaceEnds",
        config.get("Extend_Surface_Ends", True),
    )
    _set_value_input_mm(
        inputs,
        "extensionDistance",
        config.get("Surface_Extension_mm", 0.1),
    )
    _set_bool_input(
        inputs,
        "createLimitCylinders",
        config.get("Create_Limit_Cylinders", True),
    )
    _set_value_input_mm(
        inputs,
        "cylinderAxialMargin",
        config.get("Cylinder_Axial_Margin_mm", 1.0),
    )
    _set_bool_input(
        inputs,
        "finalizeSolid",
        config.get("Finalize_Solid", True),
    )
    _set_value_input_mm(
        inputs,
        "stitchTolerance",
        config.get("Stitch_Tolerance_mm", 0.01),
    )
    _set_bool_input(
        inputs,
        "cutBelowHubBase",
        config.get("Cut_Below_Hub_Base", True),
    )
    _set_bool_input(
        inputs,
        "createBladePattern",
        config.get("Create_Blade_Pattern", True),
    )

    _update_radius_distribution_inputs(inputs)
    _update_tip_ring_inputs(inputs)
    _update_spinner_inputs(inputs)

    tip_group = _required_command_input(inputs, "tipRingGroup")
    spinner_group = _required_command_input(inputs, "spinnerGroup")
    tip_group.isExpanded = create_tip_ring
    spinner_group.isExpanded = create_spinner


# =============================================================================
# GENERATION RESULT MODEL AND SECTION-CURVE CREATION
#
# GenerationResult records each optional stage independently. The command can
# therefore report partial success instead of discarding a valid blade when a
# later optional assembly feature fails.
# =============================================================================


@dataclass(frozen=True)
class GenerationResult:
    section_count: int
    section_mode: str
    component_name: str = ""

    surface_loft_requested: bool = False
    surface_loft_created: bool = False
    surface_loft_name: str = ""
    surface_loft_error: str = ""

    extension_requested: bool = False
    root_extension_created: bool = False
    tip_extension_created: bool = False
    extension_error: str = ""

    cylinders_requested: bool = False
    inner_cylinder_created: bool = False
    outer_cylinder_created: bool = False
    inner_cylinder_name: str = ""
    outer_cylinder_name: str = ""
    cylinders_error: str = ""

    finalization_requested: bool = False
    cylinder_caps_created: bool = False
    blade_trimmed: bool = False
    stitch_created: bool = False
    solid_created: bool = False
    solid_body_name: str = ""
    finalization_error: str = ""

    assembly_requested: bool = False
    underside_cut_completed: bool = False
    underside_cut_applied: bool = False
    z_offset_applied: bool = False
    blade_pattern_created: bool = False
    blade_body_count: int = 0
    hub_created: bool = False
    hub_joined: bool = False
    final_propeller_created: bool = False
    final_propeller_name: str = ""

    hoop_requested: bool = False
    hoop_created: bool = False
    hoop_joined: bool = False
    hoop_body_name: str = ""
    hoop_error: str = ""

    airfoil_ring_requested: bool = False
    airfoil_ring_created: bool = False
    airfoil_ring_joined: bool = False
    airfoil_ring_body_name: str = ""
    airfoil_ring_error: str = ""

    parabolic_spinner_requested: bool = False
    parabolic_spinner_created: bool = False
    parabolic_spinner_joined: bool = False
    parabolic_spinner_body_name: str = ""
    parabolic_spinner_error: str = ""

    ogive_spinner_requested: bool = False
    ogive_spinner_created: bool = False
    ogive_spinner_joined: bool = False
    ogive_spinner_body_name: str = ""
    ogive_spinner_error: str = ""

    assembly_error: str = ""


def _add_closed_spline_2d(
    sketch: adsk.fusion.Sketch,
    points_mm: tuple[tuple[float, float], ...],
    radius_mm: float,
) -> tuple[adsk.fusion.SketchFittedSpline, adsk.fusion.SketchLine]:
    fit_points = adsk.core.ObjectCollection.create()
    for x_mm, z_mm in points_mm:
        # No esboço sobre XZ, o eixo Y local aponta no sentido oposto ao +Z
        # global. O sinal negativo mantém Z visual para cima.
        fit_points.add(
            adsk.core.Point3D.create(
                x_mm / 10.0,
                -z_mm / 10.0,
                0.0,
            )
        )

    spline = sketch.sketchCurves.sketchFittedSplines.add(fit_points)
    if not spline:
        raise RuntimeError(f"Falha ao criar a spline da seção R={radius_mm:g} mm.")

    closing_line = sketch.sketchCurves.sketchLines.addByTwoPoints(
        spline.endSketchPoint,
        spline.startSketchPoint,
    )
    if not closing_line:
        raise RuntimeError(f"Falha ao fechar o bordo de fuga em R={radius_mm:g} mm.")

    return spline, closing_line


def _add_closed_spline_3d(
    sketch: adsk.fusion.Sketch,
    points_xyz_mm: tuple[tuple[float, float, float], ...],
    radius_mm: float,
) -> tuple[adsk.fusion.SketchFittedSpline, adsk.fusion.SketchLine]:
    fit_points = adsk.core.ObjectCollection.create()
    for x_mm, y_mm, z_mm in points_xyz_mm:
        # O esboço-base está no plano XY, cujos eixos locais coincidem com
        # X, Y e Z globais. O uso de Z diferente de zero cria a curva 3D.
        fit_points.add(
            adsk.core.Point3D.create(
                x_mm / 10.0,
                y_mm / 10.0,
                z_mm / 10.0,
            )
        )

    spline = sketch.sketchCurves.sketchFittedSplines.add(fit_points)
    if not spline:
        raise RuntimeError(
            f"Falha ao criar a spline 3D da seção R={radius_mm:g} mm."
        )

    # A seção enrolada é não planar. Esta reta 3D fecha os extremos do bordo
    # de fuga, mas não produz uma região sombreada de perfil, o que é esperado.
    closing_line = sketch.sketchCurves.sketchLines.addByTwoPoints(
        spline.endSketchPoint,
        spline.startSketchPoint,
    )
    if not closing_line:
        raise RuntimeError(
            f"Falha ao fechar o bordo de fuga 3D em R={radius_mm:g} mm."
        )

    return spline, closing_line


def _create_closed_section_path(
    component: adsk.fusion.Component,
    spline: adsk.fusion.SketchFittedSpline,
    closing_line: adsk.fusion.SketchLine,
    radius_mm: float,
) -> adsk.fusion.Path:
    """
    Cria um Path fechado no contexto do componente dono das curvas.

    Features.createPath evita perder o caminho de montagem quando o sketch
    pertence a um componente filho ativo.
    """
    if component is None or not component.isValid:
        raise RuntimeError(
            "O componente da seção não é mais válido."
        )

    curves = adsk.core.ObjectCollection.create()
    curves.add(spline)
    curves.add(closing_line)

    path = component.features.createPath(
        curves,
        False,
    )
    if path is None or not path.isValid:
        raise RuntimeError(
            f"Não foi possível criar o Path fechado em R={radius_mm:g} mm."
        )
    return path


# =============================================================================
# SURFACE LOFT, EXACT RADIAL TRIMMING AND STITCHING
#
# The original SCAD directly creates a closed polygon mesh. Fusion lofts the
# section paths as an open surface; root and tip are extended slightly, trimmed
# against analytical cylindrical surfaces, capped and stitched into a solid.
# =============================================================================


def _create_surface_loft(
    component: adsk.fusion.Component,
    section_paths: list[tuple[float, adsk.fusion.Path]],
) -> adsk.fusion.LoftFeature:
    """Cria um loft de superfície usando as seções da ponta para a raiz."""
    if len(section_paths) < 2:
        raise ValueError(
            "São necessárias pelo menos duas seções para criar o loft."
        )

    loft_features = component.features.loftFeatures
    loft_input = loft_features.createInput(
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    if not loft_input:
        raise RuntimeError("Não foi possível criar a entrada do loft.")

    loft_input.isSolid = False
    loft_input.isClosed = False
    loft_input.isTangentEdgesMerged = True
    loft_input.startLoftEdgeAlignment = (
        adsk.fusion.LoftEdgeAlignments.FreeEdgesLoftEdgeAlignment
    )
    loft_input.endLoftEdgeAlignment = (
        adsk.fusion.LoftEdgeAlignments.FreeEdgesLoftEdgeAlignment
    )

    loft_sections = loft_input.loftSections

    # Nos testes manuais, iniciar pela ponta foi mais robusto quando a raiz
    # engrossada diferia muito das demais seções.
    for radius_mm, path in sorted(
        section_paths,
        key=lambda item: item[0],
        reverse=True,
    ):
        loft_section = loft_sections.add(path)
        if not loft_section:
            raise RuntimeError(
                f"Não foi possível adicionar ao loft a seção R={radius_mm:g} mm."
            )

    loft_feature = loft_features.add(loft_input)
    if not loft_feature:
        raise RuntimeError("O Fusion não conseguiu criar o loft de superfície.")

    loft_feature.name = _t(
        "feature.loft",
        count=len(section_paths),
        root=min(r for r, _ in section_paths),
        tip=max(r for r, _ in section_paths),
    )
    return loft_feature



def _feature_first_body(
    feature: adsk.fusion.Feature,
    feature_description: str,
) -> adsk.fusion.BRepBody:
    bodies = feature.bodies
    if not bodies or bodies.count < 1:
        raise RuntimeError(
            f"{feature_description} não retornou um corpo de superfície."
        )
    body = bodies.item(0)
    if not body:
        raise RuntimeError(
            f"Não foi possível obter o corpo resultante de {feature_description}."
        )
    return body


def _boundary_edges_near_radius(
    body: adsk.fusion.BRepBody,
    target_radius_mm: float,
) -> adsk.core.ObjectCollection:
    """Localiza todas as arestas livres do loop mais próximo do raio indicado.

    Uma aresta de fronteira de um corpo de superfície possui apenas um coedge.
    Uma eventual aresta de costura longitudinal possui dois coedges e, por
    isso, não entra na seleção.
    """
    candidates: list[tuple[float, float, adsk.fusion.BRepEdge]] = []

    for index in range(body.edges.count):
        edge = body.edges.item(index)
        if not edge or edge.coEdges.count != 1:
            continue

        point = edge.pointOnEdge
        radius_mm = 10.0 * math.hypot(point.x, point.y)
        error_mm = abs(radius_mm - target_radius_mm)
        candidates.append((error_mm, radius_mm, edge))

    if not candidates:
        raise RuntimeError(
            "O corpo do loft não possui arestas livres que possam ser estendidas."
        )

    minimum_error_mm = min(item[0] for item in candidates)

    # Reúne todas as arestas do mesmo contorno. A tolerância cobre pequenas
    # diferenças numéricas entre a aresta curva e a reta do bordo de fuga,
    # sem alcançar o loop da extremidade oposta.
    selection_tolerance_mm = max(0.02, minimum_error_mm + 0.01)

    selected = adsk.core.ObjectCollection.create()
    selected_radii: list[float] = []

    for error_mm, radius_mm, edge in candidates:
        if error_mm <= selection_tolerance_mm:
            selected.add(edge)
            selected_radii.append(radius_mm)

    if selected.count < 1:
        raise RuntimeError(
            f"Não foi possível localizar o contorno em R={target_radius_mm:g} mm."
        )

    average_radius_mm = sum(selected_radii) / len(selected_radii)
    if abs(average_radius_mm - target_radius_mm) > 0.1:
        raise RuntimeError(
            "O contorno identificado para extensão está distante do raio "
            f"esperado: alvo={target_radius_mm:g} mm, "
            f"encontrado≈{average_radius_mm:g} mm."
        )

    return selected


def _extend_surface_end(
    component: adsk.fusion.Component,
    body: adsk.fusion.BRepBody,
    target_radius_mm: float,
    distance_mm: float,
    feature_name: str,
) -> tuple[adsk.fusion.ExtendFeature, adsk.fusion.BRepBody]:
    if distance_mm <= 0.0:
        raise ValueError("A distância de extensão deve ser positiva.")

    edges = _boundary_edges_near_radius(body, target_radius_mm)

    distance = adsk.core.ValueInput.createByReal(distance_mm / 10.0)
    extend_features = component.features.extendFeatures
    extend_input = extend_features.createInput(
        edges,
        distance,
        adsk.fusion.SurfaceExtendTypes.NaturalSurfaceExtendType,
        False,
    )
    if not extend_input:
        raise RuntimeError(
            f"Não foi possível preparar a extensão em R={target_radius_mm:g} mm."
        )

    extend_input.extendAlignment = (
        adsk.fusion.SurfaceExtendAlignment.FreeEdges
    )

    extend_feature = extend_features.add(extend_input)
    if not extend_feature:
        raise RuntimeError(
            f"O Fusion não conseguiu estender o contorno em "
            f"R={target_radius_mm:g} mm."
        )

    extend_feature.name = feature_name
    result_body = _feature_first_body(extend_feature, feature_name)
    return extend_feature, result_body


def _extend_both_surface_ends(
    component: adsk.fusion.Component,
    loft_feature: adsk.fusion.LoftFeature,
    root_radius_mm: float,
    tip_radius_mm: float,
    distance_mm: float,
) -> tuple[
    adsk.fusion.ExtendFeature,
    adsk.fusion.ExtendFeature,
    adsk.fusion.BRepBody,
]:
    """Estende primeiro a raiz e depois a ponta, recuperando o corpo a cada etapa."""
    loft_body = _feature_first_body(loft_feature, "o loft de superfície")

    root_feature, body_after_root = _extend_surface_end(
        component,
        loft_body,
        root_radius_mm,
        distance_mm,
        _t("feature.root_extension", distance=distance_mm),
    )

    # A primeira extensão modifica a topologia. Por isso as arestas da ponta
    # são localizadas novamente no corpo resultante, em vez de reutilizar
    # referências obtidas antes da operação.
    tip_feature, final_body = _extend_surface_end(
        component,
        body_after_root,
        tip_radius_mm,
        distance_mm,
        _t("feature.tip_extension", distance=distance_mm),
    )

    return root_feature, tip_feature, final_body


def _create_cylindrical_surface(
    component: adsk.fusion.Component,
    radius_mm: float,
    half_height_cm: float,
    label: str,
) -> tuple[
    adsk.fusion.ExtrudeFeature,
    adsk.fusion.BRepBody,
    adsk.fusion.Sketch,
]:
    """Cria uma superfície cilíndrica analítica por extrusão de círculo aberto."""
    if radius_mm <= 0.0:
        raise ValueError("O raio do cilindro deve ser positivo.")
    if half_height_cm <= 0.0:
        raise ValueError("A meia-altura do cilindro deve ser positiva.")

    sketch = component.sketches.add(component.xYConstructionPlane)
    if not sketch:
        raise RuntimeError(f"Não foi possível criar o esboço do {label}.")
    sketch.name = f"Esboço {label}"

    circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(0.0, 0.0, 0.0),
        radius_mm / 10.0,
    )
    if not circle:
        raise RuntimeError(f"Não foi possível criar a circunferência do {label}.")

    open_profile = component.createOpenProfile(circle, False)
    if not open_profile:
        raise RuntimeError(
            f"Não foi possível criar o perfil aberto para o {label}."
        )

    extrudes = component.features.extrudeFeatures
    extrude_input = extrudes.createInput(
        open_profile,
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    if not extrude_input:
        raise RuntimeError(
            f"Não foi possível preparar a extrusão do {label}."
        )

    extrude_input.isSolid = False

    # A extrusão simétrica evita depender do sentido normal do plano XY e
    # garante cobertura axial para valores Z positivos e negativos.
    half_height = adsk.core.ValueInput.createByReal(half_height_cm)
    if not extrude_input.setSymmetricExtent(half_height, False):
        raise RuntimeError(
            f"Não foi possível definir a altura do {label}."
        )

    extrude_feature = extrudes.add(extrude_input)
    if not extrude_feature:
        raise RuntimeError(f"O Fusion não conseguiu criar o {label}.")

    extrude_feature.name = label
    body = _feature_first_body(extrude_feature, label)
    body.name = label
    return extrude_feature, body, sketch


def _create_limit_cylinders(
    component: adsk.fusion.Component,
    blade_surface_body: adsk.fusion.BRepBody,
    root_radius_mm: float,
    tip_radius_mm: float,
    axial_margin_mm: float,
    hide_created_sketches: bool,
) -> tuple[
    adsk.fusion.ExtrudeFeature,
    adsk.fusion.BRepBody,
    adsk.fusion.ExtrudeFeature,
    adsk.fusion.BRepBody,
]:
    if axial_margin_mm < 0.0:
        raise ValueError("A margem axial não pode ser negativa.")

    bounding_box = blade_surface_body.boundingBox
    if not bounding_box:
        raise RuntimeError(
            "Não foi possível calcular os limites axiais da superfície da pá."
        )

    maximum_abs_z_cm = max(
        abs(bounding_box.minPoint.z),
        abs(bounding_box.maxPoint.z),
    )
    half_height_cm = maximum_abs_z_cm + axial_margin_mm / 10.0

    # Evita uma extrusão degenerada mesmo em uma configuração quase plana.
    half_height_cm = max(half_height_cm, 0.1)

    inner_label = _t("feature.inner_cylinder", radius=root_radius_mm)
    outer_label = _t("feature.outer_cylinder", radius=tip_radius_mm)

    inner_feature, inner_body, inner_sketch = _create_cylindrical_surface(
        component,
        root_radius_mm,
        half_height_cm,
        inner_label,
    )
    outer_feature, outer_body, outer_sketch = _create_cylindrical_surface(
        component,
        tip_radius_mm,
        half_height_cm,
        outer_label,
    )

    # Os círculos continuam disponíveis na timeline. A visibilidade segue
    # a opção geral da janela.
    inner_sketch.isLightBulbOn = not hide_created_sketches
    outer_sketch.isLightBulbOn = not hide_created_sketches

    return inner_feature, inner_body, outer_feature, outer_body


@dataclass(frozen=True)
class _CellMetric:
    cell: object
    area_cm2: float
    average_radius_mm: float


def _body_area_and_average_radius(
    body: adsk.fusion.BRepBody,
) -> tuple[float, float]:
    """Retorna área e raio médio ponderado pelas áreas das faces."""
    total_area = 0.0
    weighted_radius = 0.0

    for index in range(body.faces.count):
        face = body.faces.item(index)
        if not face:
            continue

        area = max(float(face.area), 1e-15)
        point = face.pointOnFace
        if not point:
            point = face.centroid
        if not point:
            continue

        radius_mm = 10.0 * math.hypot(point.x, point.y)
        total_area += area
        weighted_radius += area * radius_mm

    if total_area > 0.0:
        return total_area, weighted_radius / total_area

    bounding_box = body.boundingBox
    if not bounding_box:
        raise RuntimeError("Não foi possível medir uma célula B-Rep.")

    center_x = 0.5 * (
        bounding_box.minPoint.x + bounding_box.maxPoint.x
    )
    center_y = 0.5 * (
        bounding_box.minPoint.y + bounding_box.maxPoint.y
    )
    return 0.0, 10.0 * math.hypot(center_x, center_y)


def _trim_cell_metrics(
    trim_input: adsk.fusion.TrimFeatureInput,
) -> list[_CellMetric]:
    cells = trim_input.bRepCells
    if not cells or cells.count < 1:
        raise RuntimeError(
            "O Fusion não encontrou células válidas para a operação Trim."
        )

    metrics: list[_CellMetric] = []
    for index in range(cells.count):
        cell = cells.item(index)
        if not cell:
            continue
        area_cm2, average_radius_mm = _body_area_and_average_radius(
            cell.cellBody
        )
        metrics.append(
            _CellMetric(
                cell=cell,
                area_cm2=area_cm2,
                average_radius_mm=average_radius_mm,
            )
        )

    if not metrics:
        raise RuntimeError(
            "Não foi possível medir as células disponíveis para Trim."
        )
    return metrics


def _feature_surface_bodies(
    feature: adsk.fusion.Feature,
    description: str,
) -> list[adsk.fusion.BRepBody]:
    bodies = feature.bodies
    if not bodies or bodies.count < 1:
        raise RuntimeError(f"{description} não retornou corpos.")

    result: list[adsk.fusion.BRepBody] = []
    for index in range(bodies.count):
        body = bodies.item(index)
        if body:
            result.append(body)

    if not result:
        raise RuntimeError(f"{description} não retornou corpos válidos.")
    return result


def _add_trim_feature(
    component: adsk.fusion.Component,
    trim_tool: object,
    select_cells,
    feature_name: str,
) -> adsk.fusion.TrimFeature:
    """Cria Trim e cancela corretamente a transação em caso de falha."""
    trims = component.features.trimFeatures
    trim_input = trims.createInput(trim_tool)
    if not trim_input:
        raise RuntimeError(
            f"Não foi possível preparar a operação {feature_name}."
        )

    add_was_called = False
    try:
        metrics = _trim_cell_metrics(trim_input)
        selected_count = int(select_cells(metrics))

        if selected_count < 1:
            raise RuntimeError(
                f"A operação {feature_name} não selecionou nenhuma célula."
            )
        if selected_count >= len(metrics):
            raise RuntimeError(
                f"A operação {feature_name} tentaria remover todas as células."
            )

        add_was_called = True
        feature = trims.add(trim_input)
        if not feature:
            raise RuntimeError(
                f"O Fusion não conseguiu concluir {feature_name}."
            )
        feature.name = feature_name
        return feature
    except Exception:
        # createInput inicia uma transação parcial. Se add não foi chamado,
        # cancel é obrigatório para não deixar a timeline em estado inconsistente.
        if not add_was_called:
            try:
                trim_input.cancel()
            except Exception:
                pass
        raise


def _trim_cylinders_to_caps(
    component: adsk.fusion.Component,
    blade_body: adsk.fusion.BRepBody,
    root_radius_mm: float,
    tip_radius_mm: float,
) -> tuple[
    adsk.fusion.TrimFeature,
    adsk.fusion.BRepBody,
    adsk.fusion.BRepBody,
]:
    """Recorta ambos os cilindros e preserva o menor patch em cada raio."""

    def select_cells(metrics: list[_CellMetric]) -> int:
        groups: dict[str, list[_CellMetric]] = {
            "root": [],
            "tip": [],
        }

        for metric in metrics:
            root_error = abs(metric.average_radius_mm - root_radius_mm)
            tip_error = abs(metric.average_radius_mm - tip_radius_mm)
            groups["root" if root_error <= tip_error else "tip"].append(metric)

        selected_count = 0
        for label, group in groups.items():
            if len(group) < 2:
                expected = root_radius_mm if label == "root" else tip_radius_mm
                raise RuntimeError(
                    "O Trim não dividiu o cilindro em pelo menos duas células "
                    f"no raio {expected:g} mm."
                )

            # O patch que fecha a pá é muito menor que o restante do cilindro.
            keep_metric = min(group, key=lambda item: item.area_cm2)
            for metric in group:
                if metric is keep_metric:
                    continue
                metric.cell.isSelected = True
                selected_count += 1

        return selected_count

    trim_feature = _add_trim_feature(
        component,
        blade_body,
        select_cells,
        "Trim dos cilindros pela pá",
    )

    result_bodies = _feature_surface_bodies(
        trim_feature,
        "O Trim dos cilindros",
    )
    if len(result_bodies) < 2:
        raise RuntimeError(
            "O Trim dos cilindros não retornou os dois patches esperados."
        )

    measured: list[tuple[float, float, adsk.fusion.BRepBody]] = []
    for body in result_bodies:
        area_cm2, average_radius_mm = _body_area_and_average_radius(body)
        measured.append((average_radius_mm, area_cm2, body))

    inner_candidates = sorted(
        measured,
        key=lambda item: (
            abs(item[0] - root_radius_mm),
            item[1],
        ),
    )
    outer_candidates = sorted(
        measured,
        key=lambda item: (
            abs(item[0] - tip_radius_mm),
            item[1],
        ),
    )

    inner_body = inner_candidates[0][2]
    outer_body = outer_candidates[0][2]

    if inner_body is outer_body:
        raise RuntimeError(
            "Não foi possível distinguir os patches cilíndricos interno e externo."
        )

    inner_body.name = _t("feature.inner_cap", radius=root_radius_mm)
    outer_body.name = _t("feature.outer_cap", radius=tip_radius_mm)

    return trim_feature, inner_body, outer_body


def _trim_blade_by_radius(
    component: adsk.fusion.Component,
    blade_body: adsk.fusion.BRepBody,
    trim_tool: adsk.fusion.BRepBody,
    target_radius_mm: float,
    remove_outside: bool,
    feature_name: str,
) -> tuple[adsk.fusion.TrimFeature, adsk.fusion.BRepBody]:
    """Remove a extensão radial interna ou externa da superfície da pá."""

    def select_cells(metrics: list[_CellMetric]) -> int:
        tolerance_mm = 1e-4

        if remove_outside:
            unwanted = [
                metric
                for metric in metrics
                if metric.average_radius_mm > target_radius_mm + tolerance_mm
            ]
            if not unwanted:
                extreme = max(
                    metrics,
                    key=lambda item: item.average_radius_mm,
                )
                if extreme.average_radius_mm > target_radius_mm:
                    unwanted = [extreme]
        else:
            unwanted = [
                metric
                for metric in metrics
                if metric.average_radius_mm < target_radius_mm - tolerance_mm
            ]
            if not unwanted:
                extreme = min(
                    metrics,
                    key=lambda item: item.average_radius_mm,
                )
                if extreme.average_radius_mm < target_radius_mm:
                    unwanted = [extreme]

        for metric in unwanted:
            metric.cell.isSelected = True
        return len(unwanted)

    trim_feature = _add_trim_feature(
        component,
        trim_tool,
        select_cells,
        feature_name,
    )

    result_bodies = _feature_surface_bodies(trim_feature, feature_name)

    # A peça útil é a maior superfície remanescente. Eventuais fragmentos
    # residuais têm área muito menor.
    ranked = sorted(
        result_bodies,
        key=lambda body: _body_area_and_average_radius(body)[0],
        reverse=True,
    )
    result_body = ranked[0]
    result_body.name = _t("feature.trimmed_blade")
    return trim_feature, result_body


def _stitch_blade_to_solid(
    component: adsk.fusion.Component,
    blade_body: adsk.fusion.BRepBody,
    inner_cap: adsk.fusion.BRepBody,
    outer_cap: adsk.fusion.BRepBody,
    tolerance_mm: float,
    root_radius_mm: float,
    tip_radius_mm: float,
) -> tuple[
    adsk.fusion.StitchFeature,
    adsk.fusion.BRepBody,
    bool,
]:
    if tolerance_mm <= 0.0:
        raise ValueError("A tolerância de costura deve ser positiva.")

    surfaces = adsk.core.ObjectCollection.create()
    surfaces.add(blade_body)
    surfaces.add(inner_cap)
    surfaces.add(outer_cap)

    tolerance = adsk.core.ValueInput.createByReal(tolerance_mm / 10.0)
    stitches = component.features.stitchFeatures
    stitch_input = stitches.createInput(
        surfaces,
        tolerance,
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    if not stitch_input:
        raise RuntimeError("Não foi possível preparar a costura.")

    stitch_feature = stitches.add(stitch_input)
    if not stitch_feature:
        raise RuntimeError("O Fusion não conseguiu criar a costura.")

    stitch_feature.name = _t("feature.stitch", tolerance=tolerance_mm)
    result_bodies = _feature_surface_bodies(
        stitch_feature,
        "A costura",
    )

    solid_bodies = [body for body in result_bodies if body.isSolid]
    result_body = (
        solid_bodies[0]
        if solid_bodies
        else max(
            result_bodies,
            key=lambda body: _body_area_and_average_radius(body)[0],
        )
    )

    is_solid = bool(result_body.isSolid)
    result_body.name = (
        _t("feature.solid_blade", root=root_radius_mm, tip=tip_radius_mm)
        if is_solid
        else _t("feature.open_blade")
    )
    return stitch_feature, result_body, is_solid


def _finalize_blade_solid(
    component: adsk.fusion.Component,
    extended_blade_body: adsk.fusion.BRepBody,
    root_radius_mm: float,
    tip_radius_mm: float,
    stitch_tolerance_mm: float,
) -> tuple[
    adsk.fusion.TrimFeature,
    adsk.fusion.TrimFeature,
    adsk.fusion.TrimFeature,
    adsk.fusion.StitchFeature,
    adsk.fusion.BRepBody,
    bool,
]:
    """Executa a mesma ordem validada manualmente pelo usuário."""
    cylinder_trim, inner_cap, outer_cap = _trim_cylinders_to_caps(
        component,
        extended_blade_body,
        root_radius_mm,
        tip_radius_mm,
    )

    outer_trim, blade_after_outer = _trim_blade_by_radius(
        component,
        extended_blade_body,
        outer_cap,
        tip_radius_mm,
        True,
        "Trim da extensão externa da pá",
    )

    inner_trim, final_blade_surface = _trim_blade_by_radius(
        component,
        blade_after_outer,
        inner_cap,
        root_radius_mm,
        False,
        "Trim da extensão interna da pá",
    )

    stitch_feature, final_body, is_solid = _stitch_blade_to_solid(
        component,
        final_blade_surface,
        inner_cap,
        outer_cap,
        stitch_tolerance_mm,
        root_radius_mm,
        tip_radius_mm,
    )

    return (
        cylinder_trim,
        outer_trim,
        inner_trim,
        stitch_feature,
        final_body,
        is_solid,
    )




# =============================================================================
# FINAL PROPELLER ASSEMBLY
#
# This block starts only after a single watertight blade solid exists. Optional
# stages are ordered to reproduce the top-level SCAD operations:
# base cut -> Prop_Z_Offset -> blade pattern -> hub -> hoop -> spinners.
# =============================================================================


def _brep_bodies_to_list(
    bodies: adsk.fusion.BRepBodies,
) -> list[adsk.fusion.BRepBody]:
    result: list[adsk.fusion.BRepBody] = []
    if not bodies:
        return result
    for index in range(bodies.count):
        body = bodies.item(index)
        if body:
            result.append(body)
    return result


def _unique_valid_solid_bodies(
    bodies: list[adsk.fusion.BRepBody],
) -> list[adsk.fusion.BRepBody]:
    unique: list[adsk.fusion.BRepBody] = []
    seen: set[str] = set()

    for body in bodies:
        if not body or not body.isValid or not body.isSolid:
            continue
        try:
            token = body.entityToken
        except Exception:
            token = ""
        key = token or f"python:{id(body)}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(body)

    return unique


def _body_volume_or_zero(body: adsk.fusion.BRepBody) -> float:
    try:
        return float(body.volume)
    except Exception:
        return 0.0


def _cut_blade_below_hub_base(
    component: adsk.fusion.Component,
    blade_body: adsk.fusion.BRepBody,
    tolerance_mm: float = 1e-5,
) -> tuple[
    adsk.fusion.BRepBody,
    adsk.fusion.SplitBodyFeature | None,
    bool,
]:
    """Remove tudo que estiver abaixo do plano global Z=0.

    O corte é feito antes de Prop_Z_Offset, reproduzindo a ordem do SCAD.
    """
    tolerance_cm = tolerance_mm / 10.0
    bounding_box = blade_body.boundingBox
    if not bounding_box:
        raise RuntimeError("Não foi possível medir a pá antes do corte inferior.")

    if bounding_box.minPoint.z >= -tolerance_cm:
        blade_body.name = _t("feature.blade_base_clear")
        return blade_body, None, False

    if bounding_box.maxPoint.z <= tolerance_cm:
        raise RuntimeError(
            "A pá inteira está abaixo ou sobre o plano Z=0; o corte inferior "
            "removeria todo o corpo."
        )

    split_features = component.features.splitBodyFeatures
    split_input = split_features.createInput(
        blade_body,
        component.xYConstructionPlane,
        True,
    )
    if not split_input:
        raise RuntimeError("Não foi possível preparar o corte no plano Z=0.")

    split_feature = split_features.add(split_input)
    if not split_feature:
        raise RuntimeError("O Fusion não conseguiu dividir a pá no plano Z=0.")
    split_feature.name = _t("feature.base_split")

    result_bodies = _brep_bodies_to_list(split_feature.bodies)
    if len(result_bodies) < 2:
        raise RuntimeError(
            "A divisão no plano Z=0 não produziu as duas regiões esperadas."
        )

    upper_candidates: list[adsk.fusion.BRepBody] = []
    lower_bodies: list[adsk.fusion.BRepBody] = []

    for body in result_bodies:
        box = body.boundingBox
        if not box:
            continue
        center_z = 0.5 * (box.minPoint.z + box.maxPoint.z)
        if box.maxPoint.z <= tolerance_cm or center_z < -tolerance_cm:
            lower_bodies.append(body)
        else:
            upper_candidates.append(body)

    if not upper_candidates:
        raise RuntimeError(
            "Não foi possível identificar a parte superior da pá após o corte."
        )

    upper_body = max(upper_candidates, key=_body_volume_or_zero)
    for body in upper_candidates:
        if body is not upper_body:
            lower_bodies.append(body)

    if not lower_bodies:
        upper_body.name = "Pá única — corte inferior sem corpo removível"
        return upper_body, split_feature, False

    remove_features = component.features.removeFeatures
    for body in lower_bodies:
        if body and body.isValid:
            remove_feature = remove_features.add(body)
            if not remove_feature:
                raise RuntimeError(
                    "Não foi possível remover uma das regiões abaixo de Z=0."
                )
            remove_feature.name = _t("feature.remove_below")

    upper_body.name = _t("feature.blade_base_trimmed")
    return upper_body, split_feature, True


def _move_body_along_z(
    component: adsk.fusion.Component,
    body: adsk.fusion.BRepBody,
    offset_mm: float,
) -> tuple[adsk.fusion.BRepBody, adsk.fusion.MoveFeature | None]:
    if math.isclose(offset_mm, 0.0, abs_tol=1e-12):
        return body, None

    entities = adsk.core.ObjectCollection.create()
    entities.add(body)

    move_features = component.features.moveFeatures
    move_input = move_features.createInput2(entities)
    if not move_input:
        raise RuntimeError("Não foi possível preparar Prop_Z_Offset.")

    zero = adsk.core.ValueInput.createByReal(0.0)
    z_distance = adsk.core.ValueInput.createByReal(offset_mm / 10.0)
    if not move_input.defineAsTranslateXYZ(zero, zero, z_distance, True):
        raise RuntimeError("Não foi possível definir Prop_Z_Offset.")

    move_feature = move_features.add(move_input)
    if not move_feature:
        raise RuntimeError("O Fusion não conseguiu aplicar Prop_Z_Offset.")
    move_feature.name = _t("feature.z_offset", offset=offset_mm)

    result_bodies = _feature_surface_bodies(
        move_feature,
        "O deslocamento axial",
    )
    result_body = next(
        (candidate for candidate in result_bodies if candidate.isSolid),
        result_bodies[0],
    )
    result_body.name = _t("feature.single_blade_moved")
    return result_body, move_feature


def _create_circular_blade_pattern(
    component: adsk.fusion.Component,
    blade_body: adsk.fusion.BRepBody,
    number_of_blades: int,
) -> tuple[
    adsk.fusion.CircularPatternFeature | None,
    list[adsk.fusion.BRepBody],
]:
    if number_of_blades < 1:
        raise ValueError("Number_of_Blades deve ser pelo menos 1.")
    if number_of_blades == 1:
        blade_body.name = "Pá 01"
        return None, [blade_body]

    entities = adsk.core.ObjectCollection.create()
    entities.add(blade_body)

    circular_patterns = component.features.circularPatternFeatures
    pattern_input = circular_patterns.createInput(
        entities,
        component.zConstructionAxis,
    )
    if not pattern_input:
        raise RuntimeError("Não foi possível preparar o padrão circular.")

    pattern_input.quantity = adsk.core.ValueInput.createByReal(
        float(number_of_blades)
    )
    pattern_input.totalAngle = adsk.core.ValueInput.createByString("360 deg")
    pattern_input.isSymmetric = False

    pattern_feature = circular_patterns.add(pattern_input)
    if not pattern_feature:
        raise RuntimeError("O Fusion não conseguiu criar o padrão circular.")
    pattern_feature.name = _t("feature.pattern", count=number_of_blades)

    blade_bodies = _unique_valid_solid_bodies(
        [blade_body] + _brep_bodies_to_list(pattern_feature.bodies)
    )
    if len(blade_bodies) < number_of_blades:
        raise RuntimeError(
            "O padrão circular retornou menos corpos do que o esperado: "
            f"esperado={number_of_blades}, encontrado={len(blade_bodies)}."
        )

    # Caso a API reporte corpos adicionais, preserva os N maiores sólidos.
    if len(blade_bodies) > number_of_blades:
        blade_bodies = sorted(
            blade_bodies,
            key=_body_volume_or_zero,
            reverse=True,
        )[:number_of_blades]

    for index, body in enumerate(blade_bodies, start=1):
        body.name = _t("feature.blade_number", index=index, count=number_of_blades)

    return pattern_feature, blade_bodies


def _find_hub_profile(
    sketch: adsk.fusion.Sketch,
    has_hole: bool,
) -> adsk.fusion.Profile:
    profiles = sketch.profiles
    if not profiles or profiles.count < 1:
        raise RuntimeError("O esboço do hub não formou um perfil fechado.")

    candidates: list[adsk.fusion.Profile] = []
    for index in range(profiles.count):
        profile = profiles.item(index)
        if not profile:
            continue
        loop_count = profile.profileLoops.count
        if has_hole and loop_count >= 2:
            candidates.append(profile)
        elif not has_hole and loop_count == 1:
            candidates.append(profile)

    if not candidates:
        raise RuntimeError(
            "Não foi possível localizar o perfil anular do hub."
            if has_hole
            else "Não foi possível localizar o perfil circular do hub."
        )

    # Para círculos concêntricos, o perfil correto é o de maior área entre os
    # candidatos com a quantidade esperada de loops.
    def profile_area(profile: adsk.fusion.Profile) -> float:
        try:
            return float(profile.areaProperties().area)
        except Exception:
            return 0.0

    return max(candidates, key=profile_area)


def _create_hub_solid(
    component: adsk.fusion.Component,
    hub_diameter_mm: float,
    hole_diameter_mm: float,
    hub_length_mm: float,
    hide_created_sketches: bool,
) -> tuple[
    adsk.fusion.ExtrudeFeature,
    adsk.fusion.BRepBody,
    adsk.fusion.Sketch,
]:
    if hub_diameter_mm <= 0.0:
        raise ValueError("Hub_Diameter deve ser positivo.")
    if hub_length_mm <= 0.0:
        raise ValueError("Hub_Length deve ser positivo.")
    if hole_diameter_mm < 0.0:
        raise ValueError("Hole_Diameter não pode ser negativo.")
    if hole_diameter_mm >= hub_diameter_mm:
        raise ValueError("Hole_Diameter deve ser menor que Hub_Diameter.")

    sketch = component.sketches.add(component.xYConstructionPlane)
    if not sketch:
        raise RuntimeError("Não foi possível criar o esboço do hub.")
    sketch.name = _t("feature.hub_sketch")

    center = adsk.core.Point3D.create(0.0, 0.0, 0.0)
    outer_circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(
        center,
        0.5 * hub_diameter_mm / 10.0,
    )
    if not outer_circle:
        raise RuntimeError("Não foi possível criar o círculo externo do hub.")

    has_hole = hole_diameter_mm > 0.0
    if has_hole:
        inner_circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(
            center,
            0.5 * hole_diameter_mm / 10.0,
        )
        if not inner_circle:
            raise RuntimeError("Não foi possível criar o furo central do hub.")

    profile = _find_hub_profile(sketch, has_hole)
    distance = adsk.core.ValueInput.createByReal(hub_length_mm / 10.0)
    extrude_feature = component.features.extrudeFeatures.addSimple(
        profile,
        distance,
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    if not extrude_feature:
        raise RuntimeError("O Fusion não conseguiu extrudar o hub.")
    extrude_feature.name = _t(
        "feature.hub", diameter=hub_diameter_mm, length=hub_length_mm
    )

    hub_body = _feature_first_body(extrude_feature, "a extrusão do hub")
    hub_body.name = "Hub"
    sketch.isLightBulbOn = not hide_created_sketches
    return extrude_feature, hub_body, sketch



def _create_hoop_solid(
    component: adsk.fusion.Component,
    propeller_diameter_mm: float,
    hoop_thickness_mm: float,
    hoop_height_mm: float,
    hoop_offset_mm: float,
    hide_created_sketches: bool,
) -> tuple[
    adsk.fusion.ExtrudeFeature,
    adsk.fusion.BRepBody,
    adsk.fusion.Sketch,
    adsk.fusion.ConstructionPlane | None,
]:
    """Cria o Hoop do SCAD como um anel cilíndrico paramétrico.

    O raio interno é exatamente Propeller_Diameter / 2.
    O raio externo acrescenta Hoop_Thickness radialmente.
    A extrusão começa em Hoop_Offset e avança Hoop_Height no sentido +Z.
    """
    if propeller_diameter_mm <= 0.0:
        raise ValueError("Propeller_Diameter deve ser positivo.")
    if hoop_thickness_mm <= 0.0:
        raise ValueError("Hoop_Thickness deve ser positivo.")
    if hoop_height_mm <= 0.0:
        raise ValueError("Hoop_Height deve ser positivo.")

    support_plane = component.xYConstructionPlane
    offset_plane = None

    if not math.isclose(hoop_offset_mm, 0.0, abs_tol=1e-12):
        planes = component.constructionPlanes
        plane_input = planes.createInput()
        offset = adsk.core.ValueInput.createByReal(hoop_offset_mm / 10.0)

        if not plane_input.setByOffset(
            component.xYConstructionPlane,
            offset,
        ):
            raise RuntimeError(
                "Não foi possível definir o plano deslocado do Hoop."
            )

        offset_plane = planes.add(plane_input)
        if not offset_plane:
            raise RuntimeError(
                "O Fusion não conseguiu criar o plano deslocado do Hoop."
            )

        offset_plane.name = _t(
            "feature.hoop_plane",
            offset=hoop_offset_mm,
        )
        offset_plane.isLightBulbOn = False
        support_plane = offset_plane

    sketch = component.sketches.add(support_plane)
    if not sketch:
        raise RuntimeError("Não foi possível criar o esboço do Hoop.")
    sketch.name = _t("feature.hoop_sketch")

    inner_radius_mm = 0.5 * propeller_diameter_mm
    outer_radius_mm = inner_radius_mm + hoop_thickness_mm
    center = adsk.core.Point3D.create(0.0, 0.0, 0.0)

    inner_circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(
        center,
        inner_radius_mm / 10.0,
    )
    outer_circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(
        center,
        outer_radius_mm / 10.0,
    )

    if not inner_circle or not outer_circle:
        raise RuntimeError(
            "Não foi possível criar as circunferências do Hoop."
        )

    profile = _find_hub_profile(sketch, True)
    distance = adsk.core.ValueInput.createByReal(hoop_height_mm / 10.0)
    extrude_feature = component.features.extrudeFeatures.addSimple(
        profile,
        distance,
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    if not extrude_feature:
        raise RuntimeError("O Fusion não conseguiu extrudar o Hoop.")

    extrude_feature.name = _t(
        "feature.hoop",
        inner=2.0 * inner_radius_mm,
        outer=2.0 * outer_radius_mm,
        height=hoop_height_mm,
        offset=hoop_offset_mm,
    )

    hoop_body = _feature_first_body(
        extrude_feature,
        "a extrusão do Hoop",
    )
    hoop_body.name = extrude_feature.name
    sketch.isLightBulbOn = not hide_created_sketches

    return extrude_feature, hoop_body, sketch, offset_plane


def _spinner_point(
    radius_mm: float,
    axial_mm: float,
) -> adsk.core.Point3D:
    """Mapeia raio/Z globais para as coordenadas locais do plano XZ."""
    return adsk.core.Point3D.create(
        radius_mm / 10.0,
        -axial_mm / 10.0,
        0.0,
    )


def _sketch_endpoint_near(
    curve: object,
    target: adsk.core.Point3D,
) -> adsk.fusion.SketchPoint:
    candidates = (curve.startSketchPoint, curve.endSketchPoint)

    def squared_distance(point: adsk.fusion.SketchPoint) -> float:
        geometry = point.geometry
        return (
            (geometry.x - target.x) ** 2
            + (geometry.y - target.y) ** 2
            + (geometry.z - target.z) ** 2
        )

    return min(candidates, key=squared_distance)


def _revolve_spinner_profile(
    component: adsk.fusion.Component,
    sketch: adsk.fusion.Sketch,
    feature_name: str,
    body_name: str,
) -> tuple[adsk.fusion.RevolveFeature, adsk.fusion.BRepBody]:
    profile = _find_hub_profile(sketch, False)
    revolves = component.features.revolveFeatures
    revolve_input = revolves.createInput(
        profile,
        component.zConstructionAxis,
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    if not revolve_input:
        raise RuntimeError("Não foi possível preparar a revolução do spinner.")

    if not revolve_input.setAngleExtent(
        False,
        adsk.core.ValueInput.createByString("360 deg"),
    ):
        raise RuntimeError("Não foi possível definir a revolução completa.")

    revolve_feature = revolves.add(revolve_input)
    if not revolve_feature:
        raise RuntimeError("O Fusion não conseguiu criar o spinner por revolução.")

    revolve_feature.name = feature_name
    body = _feature_first_body(revolve_feature, feature_name)
    body.name = body_name
    return revolve_feature, body


def _create_axial_hole_tool(
    component: adsk.fusion.Component,
    diameter_mm: float,
    start_z_mm: float,
    height_mm: float,
    hide_created_sketches: bool,
    label: str,
) -> tuple[
    adsk.fusion.ExtrudeFeature,
    adsk.fusion.BRepBody,
    adsk.fusion.Sketch,
    adsk.fusion.ConstructionPlane | None,
]:
    if diameter_mm <= 0.0 or height_mm <= 0.0:
        raise ValueError("O cilindro de corte deve ter dimensões positivas.")

    support_plane = component.xYConstructionPlane
    offset_plane = None
    if not math.isclose(start_z_mm, 0.0, abs_tol=1e-12):
        planes = component.constructionPlanes
        plane_input = planes.createInput()
        if not plane_input.setByOffset(
            component.xYConstructionPlane,
            adsk.core.ValueInput.createByReal(start_z_mm / 10.0),
        ):
            raise RuntimeError("Não foi possível definir o plano do furo do spinner.")
        offset_plane = planes.add(plane_input)
        if not offset_plane:
            raise RuntimeError("Não foi possível criar o plano do furo do spinner.")
        offset_plane.name = _t("feature.spinner_hole_plane", z=start_z_mm)
        offset_plane.isLightBulbOn = False
        support_plane = offset_plane

    sketch = component.sketches.add(support_plane)
    if not sketch:
        raise RuntimeError("Não foi possível criar o esboço do furo do spinner.")
    sketch.name = _t("feature.spinner_hole_sketch", label=label)

    circle = sketch.sketchCurves.sketchCircles.addByCenterRadius(
        adsk.core.Point3D.create(0.0, 0.0, 0.0),
        0.5 * diameter_mm / 10.0,
    )
    if not circle:
        raise RuntimeError("Não foi possível criar o círculo do furo do spinner.")

    profile = _find_hub_profile(sketch, False)
    extrude = component.features.extrudeFeatures.addSimple(
        profile,
        adsk.core.ValueInput.createByReal(height_mm / 10.0),
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    if not extrude:
        raise RuntimeError("Não foi possível criar o cilindro de corte do spinner.")
    extrude.name = _t(
        "feature.spinner_hole_tool",
        diameter=diameter_mm,
        height=height_mm,
    )
    body = _feature_first_body(extrude, extrude.name)
    body.name = extrude.name
    sketch.isLightBulbOn = not hide_created_sketches
    return extrude, body, sketch, offset_plane


def _cut_spinner_hole(
    component: adsk.fusion.Component,
    spinner_body: adsk.fusion.BRepBody,
    hole_diameter_mm: float,
    hub_length_mm: float,
    hide_created_sketches: bool,
    label: str,
) -> tuple[adsk.fusion.BRepBody, adsk.fusion.CombineFeature | None]:
    """Reproduz o cilindro do SCAD: Z=-0,5 até Hub_Length+1,0."""
    if hole_diameter_mm <= 0.0:
        return spinner_body, None

    hole_start_mm = -0.5
    hole_height_mm = hub_length_mm + 1.5
    _, tool_body, _, _ = _create_axial_hole_tool(
        component,
        hole_diameter_mm,
        hole_start_mm,
        hole_height_mm,
        hide_created_sketches,
        label,
    )

    tools = adsk.core.ObjectCollection.create()
    tools.add(tool_body)
    combines = component.features.combineFeatures
    combine_input = combines.createInput(spinner_body, tools)
    if not combine_input:
        raise RuntimeError("Não foi possível preparar o furo do spinner.")
    combine_input.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
    combine_input.isKeepToolBodies = False
    combine_input.isNewComponent = False

    combine_feature = combines.add(combine_input)
    if not combine_feature:
        raise RuntimeError("O Fusion não conseguiu cortar o furo do spinner.")
    combine_feature.name = _t("feature.spinner_hole", label=label)

    bodies = _unique_valid_solid_bodies(
        _brep_bodies_to_list(combine_feature.bodies)
    )
    if not bodies:
        raise RuntimeError("O corte do furo não retornou um spinner sólido.")
    result = max(bodies, key=_body_volume_or_zero)
    return result, combine_feature


def _create_parabolic_spinner_solid(
    component: adsk.fusion.Component,
    diameter_mm: float,
    length_mm: float,
    hole_diameter_mm: float,
    hub_length_mm: float,
    hide_created_sketches: bool,
) -> tuple[adsk.fusion.RevolveFeature, adsk.fusion.BRepBody, adsk.fusion.Sketch]:
    if diameter_mm <= 0.0 or length_mm <= 0.0:
        raise ValueError("As dimensões do spinner parabólico devem ser positivas.")

    sketch = component.sketches.add(component.xZConstructionPlane)
    if not sketch:
        raise RuntimeError("Não foi possível criar o esboço do spinner parabólico.")
    sketch.name = _t("feature.parabolic_spinner_sketch")

    radius_mm = 0.5 * diameter_mm
    fit_points = adsk.core.ObjectCollection.create()
    # O SCAD usa x=[0:0.05:1.001]. Mantemos os mesmos 21 pontos básicos,
    # mas o Fusion os interpola por uma curva suave.
    for index in range(21):
        x = index / 20.0
        fit_points.add(
            _spinner_point(
                radius_mm * x,
                length_mm * (1.0 - x * x),
            )
        )

    spline = sketch.sketchCurves.sketchFittedSplines.add(fit_points)
    if not spline:
        raise RuntimeError("Não foi possível criar a parábola do spinner.")

    origin = _spinner_point(0.0, 0.0)
    lines = sketch.sketchCurves.sketchLines
    if not lines.addByTwoPoints(spline.endSketchPoint, origin):
        raise RuntimeError("Não foi possível fechar a base do spinner parabólico.")
    if not lines.addByTwoPoints(origin, spline.startSketchPoint):
        raise RuntimeError("Não foi possível fechar o eixo do spinner parabólico.")

    feature_name = _t(
        "feature.parabolic_spinner",
        diameter=diameter_mm,
        length=length_mm,
    )
    revolve, body = _revolve_spinner_profile(
        component,
        sketch,
        feature_name,
        _t("feature.parabolic_spinner_body"),
    )
    body, _ = _cut_spinner_hole(
        component,
        body,
        hole_diameter_mm,
        hub_length_mm,
        hide_created_sketches,
        _t("feature.parabolic_spinner_body"),
    )
    body.name = _t("feature.parabolic_spinner_body")
    sketch.isLightBulbOn = not hide_created_sketches
    return revolve, body, sketch


def _create_ogive_spinner_solid(
    component: adsk.fusion.Component,
    diameter_mm: float,
    length_mm: float,
    nose_radius_fraction: float,
    hole_diameter_mm: float,
    hub_length_mm: float,
    hide_created_sketches: bool,
) -> tuple[adsk.fusion.RevolveFeature, adsk.fusion.BRepBody, adsk.fusion.Sketch]:
    if diameter_mm <= 0.0 or length_mm <= 0.0:
        raise ValueError("As dimensões do spinner ogival devem ser positivas.")
    if not 0.0 < nose_radius_fraction < 0.25:
        raise ValueError("Nose_Radius deve estar entre 0 e 0,25.")

    nose_radius_mm = nose_radius_fraction * diameter_mm
    reduced_radius_mm = 0.5 * diameter_mm - nose_radius_mm
    reduced_height_mm = length_mm - nose_radius_mm
    if reduced_radius_mm <= 0.0 or reduced_height_mm <= 0.0:
        raise ValueError("As dimensões do spinner ogival são degeneradas.")

    center_offset_mm = (
        reduced_height_mm * reduced_height_mm
        - reduced_radius_mm * reduced_radius_mm
    ) / (2.0 * reduced_radius_mm)
    if center_offset_mm <= 0.0:
        raise ValueError(
            "Ogive_Spinner_Length deve ser maior que metade do diâmetro."
        )

    main_radius_mm = (
        center_offset_mm + reduced_radius_mm + nose_radius_mm
    )
    start_angle = math.atan2(reduced_height_mm, center_offset_mm)

    top = _spinner_point(0.0, length_mm)
    tangent = _spinner_point(
        nose_radius_mm * math.cos(start_angle),
        reduced_height_mm + nose_radius_mm * math.sin(start_angle),
    )
    nose_mid_angle = 0.5 * (0.5 * math.pi + start_angle)
    nose_mid = _spinner_point(
        nose_radius_mm * math.cos(nose_mid_angle),
        reduced_height_mm + nose_radius_mm * math.sin(nose_mid_angle),
    )
    main_mid_angle = 0.5 * start_angle
    main_mid = _spinner_point(
        main_radius_mm * math.cos(main_mid_angle) - center_offset_mm,
        main_radius_mm * math.sin(main_mid_angle),
    )
    base = _spinner_point(0.5 * diameter_mm, 0.0)
    origin = _spinner_point(0.0, 0.0)

    sketch = component.sketches.add(component.xZConstructionPlane)
    if not sketch:
        raise RuntimeError("Não foi possível criar o esboço do spinner ogival.")
    sketch.name = _t("feature.ogive_spinner_sketch")

    arcs = sketch.sketchCurves.sketchArcs
    nose_arc = arcs.addByThreePoints(top, nose_mid, tangent)
    if not nose_arc:
        raise RuntimeError("Não foi possível criar o arco da ponta ogival.")
    tangent_point = _sketch_endpoint_near(nose_arc, tangent)
    top_point = _sketch_endpoint_near(nose_arc, top)

    main_arc = arcs.addByThreePoints(tangent_point, main_mid, base)
    if not main_arc:
        raise RuntimeError("Não foi possível criar o arco principal da ogiva.")
    base_point = _sketch_endpoint_near(main_arc, base)

    lines = sketch.sketchCurves.sketchLines
    if not lines.addByTwoPoints(base_point, origin):
        raise RuntimeError("Não foi possível fechar a base do spinner ogival.")
    if not lines.addByTwoPoints(origin, top_point):
        raise RuntimeError("Não foi possível fechar o eixo do spinner ogival.")

    feature_name = _t(
        "feature.ogive_spinner",
        diameter=diameter_mm,
        length=length_mm,
        nose=nose_radius_fraction,
    )
    revolve, body = _revolve_spinner_profile(
        component,
        sketch,
        feature_name,
        _t("feature.ogive_spinner_body"),
    )
    body, _ = _cut_spinner_hole(
        component,
        body,
        hole_diameter_mm,
        hub_length_mm,
        hide_created_sketches,
        _t("feature.ogive_spinner_body"),
    )
    body.name = _t("feature.ogive_spinner_body")
    sketch.isLightBulbOn = not hide_created_sketches
    return revolve, body, sketch


def _join_spinner_and_propeller_bodies(
    component: adsk.fusion.Component,
    spinner_body: adsk.fusion.BRepBody,
    propeller_bodies: list[adsk.fusion.BRepBody],
    number_of_blades: int,
    feature_name: str,
) -> tuple[adsk.fusion.CombineFeature, adsk.fusion.BRepBody]:
    valid_bodies = [
        body
        for body in _unique_valid_solid_bodies(propeller_bodies)
        if body is not spinner_body
    ]
    if not valid_bodies:
        raise RuntimeError("Nenhum corpo válido foi encontrado para unir ao spinner.")

    tools = adsk.core.ObjectCollection.create()
    for body in valid_bodies:
        tools.add(body)

    combines = component.features.combineFeatures
    combine_input = combines.createInput(spinner_body, tools)
    if not combine_input:
        raise RuntimeError("Não foi possível preparar a união do spinner.")
    combine_input.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
    combine_input.isKeepToolBodies = False
    combine_input.isNewComponent = False

    combine = combines.add(combine_input)
    if not combine:
        raise RuntimeError(
            "O Fusion não conseguiu unir o spinner à hélice. "
            "Verifique se as geometrias se interceptam."
        )
    combine.name = feature_name

    bodies = _unique_valid_solid_bodies(_brep_bodies_to_list(combine.bodies))
    if not bodies:
        raise RuntimeError("A união do spinner não retornou um sólido.")
    result = max(bodies, key=_body_volume_or_zero)
    result.name = _t("feature.final_propeller_spinner", count=number_of_blades)
    return combine, result

def _join_hub_and_blades(
    component: adsk.fusion.Component,
    hub_body: adsk.fusion.BRepBody,
    blade_bodies: list[adsk.fusion.BRepBody],
    number_of_blades: int,
) -> tuple[adsk.fusion.CombineFeature, adsk.fusion.BRepBody]:
    valid_blades = _unique_valid_solid_bodies(blade_bodies)
    if not valid_blades:
        raise RuntimeError("Nenhuma pá sólida válida foi encontrada para união.")

    tools = adsk.core.ObjectCollection.create()
    for body in valid_blades:
        tools.add(body)

    combines = component.features.combineFeatures
    combine_input = combines.createInput(hub_body, tools)
    if not combine_input:
        raise RuntimeError("Não foi possível preparar a união do hub com as pás.")

    combine_input.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
    combine_input.isKeepToolBodies = False
    combine_input.isNewComponent = False

    combine_feature = combines.add(combine_input)
    if not combine_feature:
        raise RuntimeError("O Fusion não conseguiu unir o hub às pás.")
    combine_feature.name = _t("feature.join", count=number_of_blades)

    result_bodies = _unique_valid_solid_bodies(
        _brep_bodies_to_list(combine_feature.bodies)
    )
    if not result_bodies:
        raise RuntimeError("A união final não retornou um corpo sólido.")

    result_body = max(result_bodies, key=_body_volume_or_zero)
    result_body.name = _t("feature.final_propeller", count=number_of_blades)
    return combine_feature, result_body



def _resolved_airfoil_ring_chord_mm(
    requested_chord_mm: float,
    propeller_diameter_mm: float,
    max_chord_fraction: float,
) -> float:
    """Resolve the upstream demo's automatic ring-chord expression."""
    if requested_chord_mm > 0.0:
        return requested_chord_mm
    automatic = min(
        20.0,
        0.5 * propeller_diameter_mm * max_chord_fraction,
    )
    if automatic <= 0.0:
        raise ValueError(
            "Não foi possível calcular automaticamente "
            "Airfoil_Ring_Chord."
        )
    return automatic


def _create_airfoil_ring_solid(
    component: adsk.fusion.Component,
    naca_code: str,
    chord_mm: float,
    reference_diameter_mm: float,
    axial_offset_mm: float,
    trailing_edge_thickness_mm: float,
    profile_points: int,
    hide_created_sketches: bool,
) -> tuple[
    adsk.fusion.RevolveFeature,
    adsk.fusion.BRepBody,
    adsk.fusion.Sketch,
]:
    """Create the upstream NACA-section ring as a native Fusion revolve.

    The input diameter locates the NACA chord/reference line, exactly as the
    upstream ``translate([Propeller_Diameter/2, 0])`` construction. The actual
    body extends both inside and outside that diameter according to airfoil
    thickness.
    """
    reference_radius_mm = 0.5 * reference_diameter_mm
    points = airfoil_ring_profile_points(
        naca_code=naca_code,
        chord_mm=chord_mm,
        reference_radius_mm=reference_radius_mm,
        axial_offset_mm=axial_offset_mm,
        trailing_edge_thickness_mm=trailing_edge_thickness_mm,
        points_per_surface=profile_points,
    )

    if min(radius for radius, _ in points) <= 0.0:
        raise ValueError(
            "O perfil do anel cruza o eixo de revolução. "
            "Aumente Airfoil_Ring_Diameter ou reduza a espessura."
        )

    sketch = component.sketches.add(component.xZConstructionPlane)
    if not sketch:
        raise RuntimeError(
            "Não foi possível criar o esboço do anel aerodinâmico."
        )
    sketch.name = _t("feature.airfoil_ring_sketch")

    fit_points = adsk.core.ObjectCollection.create()
    for radial_mm, axial_mm in points:
        fit_points.add(
            _spinner_point(radial_mm, axial_mm)
        )

    spline = sketch.sketchCurves.sketchFittedSplines.add(
        fit_points
    )
    if not spline:
        raise RuntimeError(
            "Não foi possível criar a spline do anel aerodinâmico."
        )

    closing_line = sketch.sketchCurves.sketchLines.addByTwoPoints(
        spline.endSketchPoint,
        spline.startSketchPoint,
    )
    if not closing_line:
        raise RuntimeError(
            "Não foi possível fechar o bordo de fuga "
            "do anel aerodinâmico."
        )

    feature_name = _t(
        "feature.airfoil_ring",
        naca=naca_code,
        diameter=reference_diameter_mm,
        chord=chord_mm,
        offset=axial_offset_mm,
    )
    revolve, body = _revolve_spinner_profile(
        component,
        sketch,
        feature_name,
        _t("feature.airfoil_ring_body"),
    )
    body.name = _t("feature.airfoil_ring_body")
    sketch.isLightBulbOn = not hide_created_sketches
    return revolve, body, sketch

def _join_hoop_and_propeller_bodies(
    component: adsk.fusion.Component,
    hoop_body: adsk.fusion.BRepBody,
    propeller_bodies: list[adsk.fusion.BRepBody],
    number_of_blades: int,
) -> tuple[
    adsk.fusion.CombineFeature,
    adsk.fusion.BRepBody,
]:
    valid_bodies = _unique_valid_solid_bodies(propeller_bodies)
    valid_bodies = [
        body for body in valid_bodies
        if body is not hoop_body
    ]
    if not valid_bodies:
        raise RuntimeError(
            "Nenhum corpo de hélice válido foi encontrado para unir ao Hoop."
        )

    tools = adsk.core.ObjectCollection.create()
    for body in valid_bodies:
        tools.add(body)

    combines = component.features.combineFeatures
    combine_input = combines.createInput(hoop_body, tools)
    if not combine_input:
        raise RuntimeError(
            "Não foi possível preparar a união do Hoop com a hélice."
        )

    combine_input.operation = (
        adsk.fusion.FeatureOperations.JoinFeatureOperation
    )
    combine_input.isKeepToolBodies = False
    combine_input.isNewComponent = False

    combine_feature = combines.add(combine_input)
    if not combine_feature:
        raise RuntimeError(
            "O Fusion não conseguiu unir o Hoop à hélice. "
            "Verifique se o aro realmente toca as pontas das pás."
        )

    combine_feature.name = _t(
        "feature.hoop_join",
        count=number_of_blades,
    )

    result_bodies = _unique_valid_solid_bodies(
        _brep_bodies_to_list(combine_feature.bodies)
    )
    if not result_bodies:
        raise RuntimeError(
            "A união do Hoop não retornou um corpo sólido."
        )

    result_body = max(result_bodies, key=_body_volume_or_zero)
    result_body.name = _t(
        "feature.final_propeller_hoop",
        count=number_of_blades,
    )
    return combine_feature, result_body


@dataclass(frozen=True)
class _AssemblyOutcome:
    final_body: adsk.fusion.BRepBody
    underside_cut_completed: bool
    underside_cut_applied: bool
    z_offset_applied: bool
    blade_pattern_created: bool
    blade_bodies: tuple[adsk.fusion.BRepBody, ...]
    hub_created: bool
    hub_joined: bool
    final_propeller_created: bool
    final_propeller_name: str
    hoop_created: bool
    hoop_joined: bool
    hoop_body_name: str
    hoop_error: str
    airfoil_ring_created: bool
    airfoil_ring_joined: bool
    airfoil_ring_body_name: str
    airfoil_ring_error: str
    parabolic_spinner_created: bool
    parabolic_spinner_joined: bool
    parabolic_spinner_body_name: str
    parabolic_spinner_error: str
    ogive_spinner_created: bool
    ogive_spinner_joined: bool
    ogive_spinner_body_name: str
    ogive_spinner_error: str


def _assemble_propeller(
    component: adsk.fusion.Component,
    single_blade_body: adsk.fusion.BRepBody,
    number_of_blades: int,
    propeller_diameter_mm: float,
    hub_diameter_mm: float,
    hub_length_mm: float,
    hole_diameter_mm: float,
    prop_z_offset_mm: float,
    cut_below_hub_base: bool,
    create_blade_pattern: bool,
    create_hub_and_join: bool,
    create_hoop: bool,
    hoop_thickness_mm: float,
    hoop_height_mm: float,
    hoop_offset_mm: float,
    create_airfoil_ring: bool,
    airfoil_ring_naca: str,
    airfoil_ring_chord_mm: float,
    airfoil_ring_diameter_mm: float,
    airfoil_ring_axial_offset_mm: float,
    airfoil_ring_te_thickness_mm: float,
    airfoil_ring_profile_points: int,
    max_chord_fraction: float,
    create_parabolic_spinner: bool,
    spinner_diameter_mm: float,
    spinner_length_mm: float,
    create_ogive_spinner: bool,
    ogive_spinner_diameter_mm: float,
    ogive_spinner_length_mm: float,
    nose_radius_fraction: float,
    hide_created_sketches: bool,
) -> _AssemblyOutcome:
    blade_body = single_blade_body
    underside_cut_completed = False
    underside_cut_applied = False

    if cut_below_hub_base:
        blade_body, _, underside_cut_applied = _cut_blade_below_hub_base(
            component,
            blade_body,
        )
        underside_cut_completed = True

    blade_body, move_feature = _move_body_along_z(
        component,
        blade_body,
        prop_z_offset_mm,
    )
    z_offset_applied = move_feature is not None

    if create_blade_pattern:
        pattern_feature, blade_bodies = _create_circular_blade_pattern(
            component,
            blade_body,
            number_of_blades,
        )
        blade_pattern_created = pattern_feature is not None
    else:
        blade_bodies = [blade_body]
        blade_pattern_created = False

    hub_created = False
    hub_joined = False
    final_propeller_created = False
    final_body = blade_body
    final_name = blade_body.name
    assembly_is_single_body = False

    if create_hub_and_join:
        _, hub_body, _ = _create_hub_solid(
            component,
            hub_diameter_mm,
            hole_diameter_mm,
            hub_length_mm,
            hide_created_sketches,
        )
        hub_created = True
        _, final_body = _join_hub_and_blades(
            component,
            hub_body,
            blade_bodies,
            len(blade_bodies),
        )
        hub_joined = True
        final_propeller_created = True
        final_name = final_body.name
        assembly_is_single_body = True

    airfoil_ring_created = False
    airfoil_ring_joined = False
    airfoil_ring_body_name = ""
    airfoil_ring_error = ""

    if create_airfoil_ring:
        try:
            resolved_ring_chord_mm = (
                _resolved_airfoil_ring_chord_mm(
                    airfoil_ring_chord_mm,
                    propeller_diameter_mm,
                    max_chord_fraction,
                )
            )
            _, ring_body, _ = _create_airfoil_ring_solid(
                component,
                airfoil_ring_naca,
                resolved_ring_chord_mm,
                airfoil_ring_diameter_mm,
                airfoil_ring_axial_offset_mm,
                airfoil_ring_te_thickness_mm,
                airfoil_ring_profile_points,
                hide_created_sketches,
            )
            airfoil_ring_created = True
            airfoil_ring_body_name = ring_body.name
            join_candidates = (
                [final_body]
                if assembly_is_single_body
                else list(blade_bodies)
            )
            try:
                _, final_body = _join_hoop_and_propeller_bodies(
                    component,
                    ring_body,
                    join_candidates,
                    len(blade_bodies),
                )
                airfoil_ring_joined = True
                assembly_is_single_body = True
                final_propeller_created = True
                final_name = final_body.name
                final_body.name = _t(
                    "feature.final_propeller_airfoil_ring",
                    count=len(blade_bodies),
                )
                final_name = final_body.name
                airfoil_ring_body_name = final_body.name
            except Exception as error:
                airfoil_ring_error = (
                    f"{type(error).__name__}: {error}"
                )
        except Exception as error:
            airfoil_ring_error = (
                f"{type(error).__name__}: {error}"
            )

    parabolic_spinner_created = False
    parabolic_spinner_joined = False
    parabolic_spinner_body_name = ""
    parabolic_spinner_error = ""

    if create_parabolic_spinner:
        try:
            _, spinner_body, _ = _create_parabolic_spinner_solid(
                component,
                spinner_diameter_mm,
                spinner_length_mm,
                hole_diameter_mm,
                hub_length_mm,
                hide_created_sketches,
            )
            parabolic_spinner_created = True
            parabolic_spinner_body_name = spinner_body.name
            join_candidates = [final_body] if assembly_is_single_body else list(blade_bodies)
            try:
                _, final_body = _join_spinner_and_propeller_bodies(
                    component,
                    spinner_body,
                    join_candidates,
                    len(blade_bodies),
                    _t("feature.parabolic_spinner_join"),
                )
                parabolic_spinner_joined = True
                assembly_is_single_body = True
                final_propeller_created = True
                final_name = final_body.name
                parabolic_spinner_body_name = final_body.name
            except Exception as error:
                parabolic_spinner_error = f"{type(error).__name__}: {error}"
        except Exception as error:
            parabolic_spinner_error = f"{type(error).__name__}: {error}"

    ogive_spinner_created = False
    ogive_spinner_joined = False
    ogive_spinner_body_name = ""
    ogive_spinner_error = ""

    if create_ogive_spinner:
        try:
            _, spinner_body, _ = _create_ogive_spinner_solid(
                component,
                ogive_spinner_diameter_mm,
                ogive_spinner_length_mm,
                nose_radius_fraction,
                hole_diameter_mm,
                hub_length_mm,
                hide_created_sketches,
            )
            ogive_spinner_created = True
            ogive_spinner_body_name = spinner_body.name
            join_candidates = [final_body] if assembly_is_single_body else list(blade_bodies)
            try:
                _, final_body = _join_spinner_and_propeller_bodies(
                    component,
                    spinner_body,
                    join_candidates,
                    len(blade_bodies),
                    _t("feature.ogive_spinner_join"),
                )
                ogive_spinner_joined = True
                assembly_is_single_body = True
                final_propeller_created = True
                final_name = final_body.name
                ogive_spinner_body_name = final_body.name
            except Exception as error:
                ogive_spinner_error = f"{type(error).__name__}: {error}"
        except Exception as error:
            ogive_spinner_error = f"{type(error).__name__}: {error}"

    hoop_created = False
    hoop_joined = False
    hoop_body_name = ""
    hoop_error = ""

    if create_hoop:
        try:
            _, hoop_body, _, _ = _create_hoop_solid(
                component,
                propeller_diameter_mm,
                hoop_thickness_mm,
                hoop_height_mm,
                hoop_offset_mm,
                hide_created_sketches,
            )
            hoop_created = True
            hoop_body_name = hoop_body.name
            join_candidates = [final_body] if assembly_is_single_body else list(blade_bodies)
            try:
                _, final_body = _join_hoop_and_propeller_bodies(
                    component,
                    hoop_body,
                    join_candidates,
                    len(blade_bodies),
                )
                hoop_joined = True
                assembly_is_single_body = True
                final_propeller_created = True
                final_name = final_body.name
                hoop_body_name = final_body.name
            except Exception as error:
                hoop_error = f"{type(error).__name__}: {error}"
        except Exception as error:
            hoop_error = f"{type(error).__name__}: {error}"

    return _AssemblyOutcome(
        final_body=final_body,
        underside_cut_completed=underside_cut_completed,
        underside_cut_applied=underside_cut_applied,
        z_offset_applied=z_offset_applied,
        blade_pattern_created=blade_pattern_created,
        blade_bodies=tuple(blade_bodies),
        hub_created=hub_created,
        hub_joined=hub_joined,
        final_propeller_created=final_propeller_created,
        final_propeller_name=final_name,
        hoop_created=hoop_created,
        hoop_joined=hoop_joined,
        hoop_body_name=hoop_body_name,
        hoop_error=hoop_error,
        airfoil_ring_created=airfoil_ring_created,
        airfoil_ring_joined=airfoil_ring_joined,
        airfoil_ring_body_name=airfoil_ring_body_name,
        airfoil_ring_error=airfoil_ring_error,
        parabolic_spinner_created=parabolic_spinner_created,
        parabolic_spinner_joined=parabolic_spinner_joined,
        parabolic_spinner_body_name=parabolic_spinner_body_name,
        parabolic_spinner_error=parabolic_spinner_error,
        ogive_spinner_created=ogive_spinner_created,
        ogive_spinner_joined=ogive_spinner_joined,
        ogive_spinner_body_name=ogive_spinner_body_name,
        ogive_spinner_error=ogive_spinner_error,
    )


def _create_flat_section_plane(
    component: adsk.fusion.Component,
    radius_mm: float,
    sweep_deg: float,
    index: int,
) -> adsk.fusion.ConstructionPlane:
    """Cria o plano tangente da seção na posição azimutal de Sweep_Angle.

    Com sweep zero, preserva exatamente a construção antiga: plano XZ
    deslocado em +Y. Para sweep diferente de zero, primeiro gira um plano
    auxiliar em torno de Z e depois o desloca radialmente. A rotação usada no
    plano é o negativo do ângulo azimutal porque a normal +Y do plano XZ deve
    terminar em (sin(theta), cos(theta), 0), enquanto o eixo X local termina
    na direção tangencial positiva (cos(theta), -sin(theta), 0).
    """
    construction_planes = component.constructionPlanes
    base_plane = component.xZConstructionPlane

    reference_plane = base_plane
    if not math.isclose(sweep_deg, 0.0, abs_tol=1e-12):
        angle_input = construction_planes.createInput()
        fusion_plane_angle = adsk.core.ValueInput.createByString(
            f"{-sweep_deg:.15g} deg"
        )
        if not angle_input.setByAngle(
            component.zConstructionAxis,
            fusion_plane_angle,
            base_plane,
        ):
            raise RuntimeError(
                f"Não foi possível definir o plano angular em R={radius_mm:g} mm."
            )

        reference_plane = construction_planes.add(angle_input)
        if not reference_plane:
            raise RuntimeError(
                f"Não foi possível criar o plano angular em R={radius_mm:g} mm."
            )
        reference_plane.name = _t(
            "feature.sweep_reference_plane",
            index=index,
            radius=radius_mm,
            sweep=sweep_deg,
        )
        reference_plane.isLightBulbOn = False

    offset_input = construction_planes.createInput()
    offset = adsk.core.ValueInput.createByReal(radius_mm / 10.0)
    if not offset_input.setByOffset(reference_plane, offset):
        raise RuntimeError(
            f"Não foi possível definir o plano tangente em R={radius_mm:g} mm."
        )

    section_plane = construction_planes.add(offset_input)
    if not section_plane:
        raise RuntimeError(
            f"Não foi possível criar o plano tangente em R={radius_mm:g} mm."
        )
    section_plane.name = _t(
        "feature.section_plane",
        index=index,
        radius=radius_mm,
        sweep=sweep_deg,
    )
    return section_plane

def _generate_flat_sections(
    component: adsk.fusion.Component,
    config: BladeConfig,
    radii: list[float],
    apply_angle: bool,
    profile_points: int,
    hide_created_sketches: bool,
) -> int:
    sketches = component.sketches

    created = 0
    for index, radius_mm in enumerate(radii, start=1):
        section = section_geometry(
            config,
            radius_mm,
            apply_geometric_angle=apply_angle,
            profile_points_override=profile_points,
        )
        sweep_deg = sweep_origin_angle_deg(config, radius_mm)
        plane = _create_flat_section_plane(
            component,
            radius_mm,
            sweep_deg,
            index,
        )

        sketch = sketches.add(plane)
        if not sketch:
            raise RuntimeError(f"Não foi possível criar o esboço em R={radius_mm:g} mm.")
        sketch.name = _t(
            "feature.flat_section",
            index=index,
            radius=radius_mm,
            chord=section.chord_mm,
            angle=section.applied_angle_deg,
            sweep=sweep_deg,
            points=section.profile_points_per_surface,
        )

        sketch.isComputeDeferred = True
        try:
            _add_closed_spline_2d(sketch, section.points_mm, radius_mm)
        finally:
            sketch.isComputeDeferred = False

        sketch.isLightBulbOn = not hide_created_sketches
        created += 1

    return created


def _generate_wrapped_sections(
    component: adsk.fusion.Component,
    config: BladeConfig,
    radii: list[float],
    apply_angle: bool,
    profile_points: int,
    create_surface_loft: bool,
    extend_surface_ends: bool,
    extension_distance_mm: float,
    create_limit_cylinders: bool,
    cylinder_axial_margin_mm: float,
    finalize_solid: bool,
    stitch_tolerance_mm: float,
    hide_created_sketches: bool,
    number_of_blades: int,
    hub_length_mm: float,
    hole_diameter_mm: float,
    prop_z_offset_mm: float,
    cut_below_hub_base: bool,
    create_blade_pattern: bool,
    create_hub_and_join: bool,
    create_hoop: bool,
    hoop_thickness_mm: float,
    hoop_height_mm: float,
    hoop_offset_mm: float,
    create_airfoil_ring: bool,
    airfoil_ring_naca: str,
    airfoil_ring_chord_mm: float,
    airfoil_ring_diameter_mm: float,
    airfoil_ring_axial_offset_mm: float,
    airfoil_ring_te_thickness_mm: float,
    airfoil_ring_profile_points: int,
    create_parabolic_spinner: bool,
    spinner_diameter_mm: float,
    spinner_length_mm: float,
    create_ogive_spinner: bool,
    ogive_spinner_diameter_mm: float,
    ogive_spinner_length_mm: float,
    nose_radius_fraction: float,
) -> GenerationResult:
    sketches = component.sketches
    base_plane = component.xYConstructionPlane
    section_paths: list[tuple[float, adsk.fusion.Path]] = []

    created = 0
    for index, radius_mm in enumerate(radii, start=1):
        section = wrapped_section_geometry(
            config,
            radius_mm,
            apply_geometric_angle=apply_angle,
            profile_points_override=profile_points,
        )

        sketch = sketches.add(base_plane)
        if not sketch:
            raise RuntimeError(
                f"Não foi possível criar o esboço 3D em R={radius_mm:g} mm."
            )
        sketch.name = _t(
            "feature.wrapped_section",
            index=index,
            radius=radius_mm,
            chord=section.chord_mm,
            angle=section.applied_angle_deg,
            sweep=section.sweep_origin_deg,
            points=section.profile_points_per_surface,
        )

        sketch.isComputeDeferred = True
        try:
            spline, closing_line = _add_closed_spline_3d(
                sketch,
                section.points_xyz_mm,
                radius_mm,
            )
        finally:
            sketch.isComputeDeferred = False

        section_path = _create_closed_section_path(
            component,
            spline,
            closing_line,
            radius_mm,
        )
        section_paths.append((radius_mm, section_path))
        sketch.isLightBulbOn = not hide_created_sketches
        created += 1

    if not create_surface_loft:
        return GenerationResult(
            section_count=created,
            section_mode=MODE_WRAPPED,
            surface_loft_requested=False,
            extension_requested=extend_surface_ends,
            extension_error=(
                "A extensão requer que o loft de superfície seja criado."
                if extend_surface_ends else ""
            ),
            cylinders_requested=create_limit_cylinders,
            cylinders_error=(
                "Os cilindros requerem que o loft seja criado."
                if create_limit_cylinders else ""
            ),
            finalization_requested=finalize_solid,
            finalization_error=(
                "A finalização sólida requer loft, extensões e cilindros."
                if finalize_solid else ""
            ),
        )

    try:
        loft_feature = _create_surface_loft(component, section_paths)
    except Exception as error:
        return GenerationResult(
            section_count=created,
            section_mode=MODE_WRAPPED,
            surface_loft_requested=True,
            surface_loft_created=False,
            surface_loft_error=f"{type(error).__name__}: {error}",
            extension_requested=extend_surface_ends,
            cylinders_requested=create_limit_cylinders,
            finalization_requested=finalize_solid,
        )

    root_radius_mm = min(radii)
    tip_radius_mm = max(radii)
    current_body = _feature_first_body(loft_feature, "o loft de superfície")

    root_extension_created = False
    tip_extension_created = False
    extension_error = ""

    if extend_surface_ends:
        try:
            _, _, current_body = _extend_both_surface_ends(
                component,
                loft_feature,
                root_radius_mm,
                tip_radius_mm,
                extension_distance_mm,
            )
            root_extension_created = True
            tip_extension_created = True
        except Exception as error:
            extension_error = f"{type(error).__name__}: {error}"

    inner_cylinder_created = False
    outer_cylinder_created = False
    inner_cylinder_name = ""
    outer_cylinder_name = ""
    cylinders_error = ""
    inner_cylinder_body = None
    outer_cylinder_body = None

    if create_limit_cylinders:
        try:
            (
                inner_feature,
                inner_cylinder_body,
                outer_feature,
                outer_cylinder_body,
            ) = _create_limit_cylinders(
                component,
                current_body,
                root_radius_mm,
                tip_radius_mm,
                cylinder_axial_margin_mm,
                hide_created_sketches,
            )
            inner_cylinder_created = True
            outer_cylinder_created = True
            inner_cylinder_name = inner_feature.name
            outer_cylinder_name = outer_feature.name
        except Exception as error:
            cylinders_error = f"{type(error).__name__}: {error}"

    cylinder_caps_created = False
    blade_trimmed = False
    stitch_created = False
    solid_created = False
    solid_body_name = ""
    finalization_error = ""
    single_blade_body = None

    if finalize_solid:
        prerequisites_ok = (
            root_extension_created
            and tip_extension_created
            and inner_cylinder_created
            and outer_cylinder_created
            and inner_cylinder_body is not None
            and outer_cylinder_body is not None
        )

        if not prerequisites_ok:
            finalization_error = (
                "A finalização requer que as duas extensões e os dois "
                "cilindros tenham sido criados com sucesso."
            )
        else:
            try:
                (
                    _,
                    _,
                    _,
                    _,
                    final_body,
                    solid_created,
                ) = _finalize_blade_solid(
                    component,
                    current_body,
                    root_radius_mm,
                    tip_radius_mm,
                    stitch_tolerance_mm,
                )
                cylinder_caps_created = True
                blade_trimmed = True
                stitch_created = True
                solid_body_name = final_body.name
                if solid_created:
                    single_blade_body = final_body

                if not solid_created:
                    finalization_error = (
                        "A costura foi criada, mas o resultado ainda é uma "
                        "superfície aberta. Verifique as bordas livres."
                    )
            except Exception as error:
                finalization_error = f"{type(error).__name__}: {error}"

    assembly_requested = (
        cut_below_hub_base
        or not math.isclose(prop_z_offset_mm, 0.0, abs_tol=1e-12)
        or create_blade_pattern
        or create_hub_and_join
        or create_hoop
        or create_airfoil_ring
        or create_parabolic_spinner
        or create_ogive_spinner
    )
    underside_cut_completed = False
    underside_cut_applied = False
    z_offset_applied = False
    blade_pattern_created = False
    blade_body_count = 1 if single_blade_body is not None else 0
    hub_created = False
    hub_joined = False
    final_propeller_created = False
    final_propeller_name = ""
    hoop_created = False
    hoop_joined = False
    hoop_body_name = ""
    hoop_error = ""
    airfoil_ring_created = False
    airfoil_ring_joined = False
    airfoil_ring_body_name = ""
    airfoil_ring_error = ""
    parabolic_spinner_created = False
    parabolic_spinner_joined = False
    parabolic_spinner_body_name = ""
    parabolic_spinner_error = ""
    ogive_spinner_created = False
    ogive_spinner_joined = False
    ogive_spinner_body_name = ""
    ogive_spinner_error = ""
    assembly_error = ""

    if assembly_requested:
        if single_blade_body is None:
            assembly_error = (
                "A montagem final requer que a costura tenha produzido "
                "uma pá sólida."
            )
        else:
            try:
                assembly = _assemble_propeller(
                    component,
                    single_blade_body,
                    number_of_blades,
                    config.propeller_diameter_mm,
                    config.hub_diameter_mm,
                    hub_length_mm,
                    hole_diameter_mm,
                    prop_z_offset_mm,
                    cut_below_hub_base,
                    create_blade_pattern,
                    create_hub_and_join,
                    create_hoop,
                    hoop_thickness_mm,
                    hoop_height_mm,
                    hoop_offset_mm,
                    create_airfoil_ring,
                    airfoil_ring_naca,
                    airfoil_ring_chord_mm,
                    airfoil_ring_diameter_mm,
                    airfoil_ring_axial_offset_mm,
                    airfoil_ring_te_thickness_mm,
                    airfoil_ring_profile_points,
                    config.max_chord_fraction,
                    create_parabolic_spinner,
                    spinner_diameter_mm,
                    spinner_length_mm,
                    create_ogive_spinner,
                    ogive_spinner_diameter_mm,
                    ogive_spinner_length_mm,
                    nose_radius_fraction,
                    hide_created_sketches,
                )
                underside_cut_completed = assembly.underside_cut_completed
                underside_cut_applied = assembly.underside_cut_applied
                z_offset_applied = assembly.z_offset_applied
                blade_pattern_created = assembly.blade_pattern_created
                blade_body_count = len(assembly.blade_bodies)
                hub_created = assembly.hub_created
                hub_joined = assembly.hub_joined
                final_propeller_created = assembly.final_propeller_created
                final_propeller_name = assembly.final_propeller_name
                hoop_created = assembly.hoop_created
                hoop_joined = assembly.hoop_joined
                hoop_body_name = assembly.hoop_body_name
                hoop_error = assembly.hoop_error
                airfoil_ring_created = assembly.airfoil_ring_created
                airfoil_ring_joined = assembly.airfoil_ring_joined
                airfoil_ring_body_name = assembly.airfoil_ring_body_name
                airfoil_ring_error = assembly.airfoil_ring_error
                parabolic_spinner_created = assembly.parabolic_spinner_created
                parabolic_spinner_joined = assembly.parabolic_spinner_joined
                parabolic_spinner_body_name = assembly.parabolic_spinner_body_name
                parabolic_spinner_error = assembly.parabolic_spinner_error
                ogive_spinner_created = assembly.ogive_spinner_created
                ogive_spinner_joined = assembly.ogive_spinner_joined
                ogive_spinner_body_name = assembly.ogive_spinner_body_name
                ogive_spinner_error = assembly.ogive_spinner_error
            except Exception as error:
                assembly_error = f"{type(error).__name__}: {error}"

    return GenerationResult(
        section_count=created,
        section_mode=MODE_WRAPPED,
        surface_loft_requested=True,
        surface_loft_created=True,
        surface_loft_name=loft_feature.name,
        extension_requested=extend_surface_ends,
        root_extension_created=root_extension_created,
        tip_extension_created=tip_extension_created,
        extension_error=extension_error,
        cylinders_requested=create_limit_cylinders,
        inner_cylinder_created=inner_cylinder_created,
        outer_cylinder_created=outer_cylinder_created,
        inner_cylinder_name=inner_cylinder_name,
        outer_cylinder_name=outer_cylinder_name,
        cylinders_error=cylinders_error,
        finalization_requested=finalize_solid,
        cylinder_caps_created=cylinder_caps_created,
        blade_trimmed=blade_trimmed,
        stitch_created=stitch_created,
        solid_created=solid_created,
        solid_body_name=solid_body_name,
        finalization_error=finalization_error,
        assembly_requested=assembly_requested,
        underside_cut_completed=underside_cut_completed,
        underside_cut_applied=underside_cut_applied,
        z_offset_applied=z_offset_applied,
        blade_pattern_created=blade_pattern_created,
        blade_body_count=blade_body_count,
        hub_created=hub_created,
        hub_joined=hub_joined,
        final_propeller_created=final_propeller_created,
        final_propeller_name=final_propeller_name,
        hoop_requested=create_hoop,
        hoop_created=hoop_created,
        hoop_joined=hoop_joined,
        hoop_body_name=hoop_body_name,
        hoop_error=hoop_error,
        airfoil_ring_requested=create_airfoil_ring,
        airfoil_ring_created=airfoil_ring_created,
        airfoil_ring_joined=airfoil_ring_joined,
        airfoil_ring_body_name=airfoil_ring_body_name,
        airfoil_ring_error=airfoil_ring_error,
        parabolic_spinner_requested=create_parabolic_spinner,
        parabolic_spinner_created=parabolic_spinner_created,
        parabolic_spinner_joined=parabolic_spinner_joined,
        parabolic_spinner_body_name=parabolic_spinner_body_name,
        parabolic_spinner_error=parabolic_spinner_error,
        ogive_spinner_requested=create_ogive_spinner,
        ogive_spinner_created=ogive_spinner_created,
        ogive_spinner_joined=ogive_spinner_joined,
        ogive_spinner_body_name=ogive_spinner_body_name,
        ogive_spinner_error=ogive_spinner_error,
        assembly_error=assembly_error,
    )


def _generate_sections(
    radii: list[float],
    apply_angle: bool,
    section_mode: str,
    profile_points: int,
    create_surface_loft: bool,
    extend_surface_ends: bool,
    extension_distance_mm: float,
    create_limit_cylinders: bool,
    cylinder_axial_margin_mm: float,
    finalize_solid: bool,
    stitch_tolerance_mm: float,
    config_overrides: dict,
    hide_created_sketches: bool,
    number_of_blades: int,
    hub_length_mm: float,
    hole_diameter_mm: float,
    prop_z_offset_mm: float,
    cut_below_hub_base: bool,
    create_blade_pattern: bool,
    create_hub_and_join: bool,
    create_hoop: bool,
    hoop_thickness_mm: float,
    hoop_height_mm: float,
    hoop_offset_mm: float,
    create_airfoil_ring: bool,
    airfoil_ring_naca: str,
    airfoil_ring_chord_mm: float,
    airfoil_ring_diameter_mm: float,
    airfoil_ring_axial_offset_mm: float,
    airfoil_ring_te_thickness_mm: float,
    airfoil_ring_profile_points: int,
    create_parabolic_spinner: bool,
    spinner_diameter_mm: float,
    spinner_length_mm: float,
    create_ogive_spinner: bool,
    ogive_spinner_diameter_mm: float,
    ogive_spinner_length_mm: float,
    nose_radius_fraction: float,
) -> GenerationResult:
    design = adsk.fusion.Design.cast(APP.activeProduct)
    if design is None or not design.isValid:
        raise RuntimeError(_t("error.design_required"))

    component = design.activeComponent
    if component is None or not component.isValid:
        raise RuntimeError(_t("error.active_component_required"))

    component_name = str(
        component.name or _t("result.unnamed_component")
    )

    raw_config = _load_raw_config()
    raw_config.update(config_overrides)
    config = BladeConfig.from_mapping(raw_config)
    radii = validate_radii(config, radii)

    if section_mode == MODE_FLAT:
        count = _generate_flat_sections(
            component,
            config,
            radii,
            apply_angle,
            profile_points,
            hide_created_sketches,
        )
        return GenerationResult(
            section_count=count,
            section_mode=MODE_FLAT,
            component_name=component_name,
        )

    if section_mode == MODE_WRAPPED:
        wrapped_result = _generate_wrapped_sections(
            component,
            config,
            radii,
            apply_angle,
            profile_points,
            create_surface_loft,
            extend_surface_ends,
            extension_distance_mm,
            create_limit_cylinders,
            cylinder_axial_margin_mm,
            finalize_solid,
            stitch_tolerance_mm,
            hide_created_sketches,
            number_of_blades,
            hub_length_mm,
            hole_diameter_mm,
            prop_z_offset_mm,
            cut_below_hub_base,
            create_blade_pattern,
            create_hub_and_join,
            create_hoop,
            hoop_thickness_mm,
            hoop_height_mm,
            hoop_offset_mm,
            create_airfoil_ring,
            airfoil_ring_naca,
            airfoil_ring_chord_mm,
            airfoil_ring_diameter_mm,
            airfoil_ring_axial_offset_mm,
            airfoil_ring_te_thickness_mm,
            airfoil_ring_profile_points,
            create_parabolic_spinner,
            spinner_diameter_mm,
            spinner_length_mm,
            create_ogive_spinner,
            ogive_spinner_diameter_mm,
            ogive_spinner_length_mm,
            nose_radius_fraction,
        )
        return replace(
            wrapped_result,
            component_name=component_name,
        )

    raise ValueError(f"Modo de seção desconhecido: {section_mode!r}.")


# =============================================================================
# TIMELINE GROUPING
#
# Features created in Command.execute belong to the command transaction. The
# timeline can still report its pre-transaction count inside execute, so group
# creation is deferred to UserInterface.commandTerminated.
# =============================================================================

TIMELINE_GROUP_PREFIX = "Elliptical NACA Propeller"


def _capture_timeline_group_request() -> dict:
    """
    Capture the design and first future timeline index before generation.

    The returned request always records why grouping is unavailable, avoiding
    the silent behavior of the previous implementation.
    """
    design = adsk.fusion.Design.cast(APP.activeProduct)
    if design is None or not design.isValid:
        return {
            "design": None,
            "start_index": None,
            "skip_key": "result.timeline_group_skipped_no_design",
        }

    if (
        design.designType
        != adsk.fusion.DesignTypes.ParametricDesignType
    ):
        return {
            "design": design,
            "start_index": None,
            "skip_key": "result.timeline_group_skipped_direct",
        }

    timeline = design.timeline
    if timeline is None or not timeline.isValid:
        return {
            "design": design,
            "start_index": None,
            "skip_key": "result.timeline_group_skipped_no_timeline",
        }

    if int(timeline.markerPosition) != int(timeline.count):
        return {
            "design": design,
            "start_index": None,
            "skip_key": "result.timeline_group_skipped_marker",
        }

    return {
        "design": design,
        "start_index": int(timeline.count),
        "skip_key": "",
    }


def _next_timeline_group_name(
    timeline: adsk.fusion.Timeline,
    incomplete: bool,
) -> str:
    """Return the next sequential name used by this add-in."""
    highest_number = 0
    name_pattern = re.compile(
        rf"^{re.escape(TIMELINE_GROUP_PREFIX)}\s+(\d+)"
    )

    groups = timeline.timelineGroups
    for index in range(groups.count):
        group = groups.item(index)
        if group is None or not group.isValid:
            continue

        match = name_pattern.match(str(group.name or ""))
        if match:
            highest_number = max(
                highest_number,
                int(match.group(1)),
            )

    name = f"{TIMELINE_GROUP_PREFIX} {highest_number + 1:02d}"
    if incomplete:
        name += " (incomplete)"
    return name


def _create_timeline_group_for_run(
    request: dict,
    incomplete: bool = False,
) -> tuple[str, str, str]:
    """
    Create a group after command termination.

    Returns:
        (group_name, error_detail, skipped_message)
    """
    skip_key = str(request.get("skip_key", ""))
    if skip_key:
        return "", "", _t(skip_key)

    try:
        design = request.get("design")
        if design is None or not design.isValid:
            return "", _t("result.timeline_group_invalid_design"), ""

        if (
            design.designType
            != adsk.fusion.DesignTypes.ParametricDesignType
        ):
            return "", "", _t("result.timeline_group_skipped_direct")

        timeline = design.timeline
        if timeline is None or not timeline.isValid:
            return "", _t("result.timeline_group_missing_timeline"), ""

        start_index = int(request["start_index"])
        current_count = int(timeline.count)
        end_index = current_count - 1
        generated_item_count = end_index - start_index + 1

        if generated_item_count <= 0:
            return (
                "",
                _t(
                    "result.timeline_group_no_items",
                    start=start_index,
                    count=current_count,
                ),
                "",
            )

        if generated_item_count == 1:
            return (
                "",
                "",
                _t(
                    "result.timeline_group_single_item",
                    index=start_index,
                ),
            )

        # A TimelineGroup cannot contain another group. This should not occur
        # because only new end-of-timeline items are captured, but report it
        # explicitly rather than returning silently.
        for index in range(start_index, end_index + 1):
            timeline_object = timeline.item(index)
            if timeline_object and timeline_object.isGroup:
                return "", _t("result.timeline_group_nested"), ""

        group_name = _next_timeline_group_name(
            timeline,
            incomplete,
        )
        group = timeline.timelineGroups.add(
            start_index,
            end_index,
        )
        if group is None or not group.isValid:
            return "", _t("result.timeline_group_null"), ""

        group.name = group_name
        group.isCollapsed = True
        return group.name, "", ""
    except Exception:
        return "", traceback.format_exc(), ""


def _queue_post_termination_result(
    request: dict,
    message: str,
    incomplete: bool,
) -> None:
    """Store one result for the global commandTerminated event."""
    global _pending_timeline_run
    _pending_timeline_run = {
        "request": request,
        "message": message,
        "incomplete": bool(incomplete),
    }


# =============================================================================
# FUSION COMMAND EVENTS AND ADD-IN LIFECYCLE
#
# Fusion retains event handlers only while Python references remain alive.
# Every handler instance is therefore appended to the module-level _handlers
# list. Removing that retention causes apparently random command failures.
# =============================================================================


class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args: adsk.core.CommandEventArgs):
        global _pending_timeline_run

        timeline_group_request = None
        _pending_timeline_run = None

        try:
            inputs = args.command.commandInputs

            radii_text = _string_input_value(inputs, "radii")
            radius_distribution_mode = _selected_dropdown_name(
                inputs,
                "radiusDistributionMode",
            )
            section_spacing_mm = _value_input_mm(inputs, "sectionSpacing")
            section_slices = int(
                _required_command_input(inputs, "sectionSlices").value
            )

            apply_angle = bool(
                _required_command_input(inputs, "applyAngle").value
            )
            profile_points = int(
                _required_command_input(inputs, "profilePoints").value
            )
            section_mode = _selected_dropdown_name(inputs, "sectionMode")

            create_surface_loft = bool(
                _required_command_input(inputs, "createSurfaceLoft").value
            )
            extend_surface_ends = bool(
                _required_command_input(inputs, "extendSurfaceEnds").value
            )
            create_limit_cylinders = bool(
                _required_command_input(inputs, "createLimitCylinders").value
            )
            finalize_solid = bool(
                _required_command_input(inputs, "finalizeSolid").value
            )
            hide_created_sketches = bool(
                _required_command_input(inputs, "hideCreatedSketches").value
            )

            extension_distance_mm = _value_input_mm(inputs, "extensionDistance")
            cylinder_axial_margin_mm = _value_input_mm(inputs, "cylinderAxialMargin")
            stitch_tolerance_mm = _value_input_mm(inputs, "stitchTolerance")

            config_overrides = _collect_blade_config_overrides(inputs, profile_points)
            assembly_parameters = _collect_final_assembly_parameters(inputs)

            radii_config_values = _load_raw_config()
            radii_config_values.update(config_overrides)
            radii_config = BladeConfig.from_mapping(radii_config_values)
            resolved_radii = _resolve_section_radii(
                radii_config,
                radius_distribution_mode,
                radii_text,
                section_spacing_mm,
                section_slices,
            )

            # All dialog values and the radial distribution are valid at this
            # point. Persist them before geometry creation so a later Fusion
            # feature failure does not discard the user's last settings.
            _save_current_config(inputs)

            timeline_group_request = _capture_timeline_group_request()

            result = _generate_sections(
                resolved_radii,
                apply_angle,
                section_mode,
                profile_points,
                create_surface_loft,
                extend_surface_ends,
                extension_distance_mm,
                create_limit_cylinders,
                cylinder_axial_margin_mm,
                finalize_solid,
                stitch_tolerance_mm,
                config_overrides,
                hide_created_sketches,
                assembly_parameters["number_of_blades"],
                assembly_parameters["hub_length_mm"],
                assembly_parameters["hole_diameter_mm"],
                assembly_parameters["prop_z_offset_mm"],
                assembly_parameters["cut_below_hub_base"],
                assembly_parameters["create_blade_pattern"],
                assembly_parameters["create_hub_and_join"],
                assembly_parameters["create_hoop"],
                assembly_parameters["hoop_thickness_mm"],
                assembly_parameters["hoop_height_mm"],
                assembly_parameters["hoop_offset_mm"],
                assembly_parameters["create_airfoil_ring"],
                assembly_parameters["airfoil_ring_naca"],
                assembly_parameters["airfoil_ring_chord_mm"],
                assembly_parameters["airfoil_ring_diameter_mm"],
                assembly_parameters["airfoil_ring_axial_offset_mm"],
                assembly_parameters["airfoil_ring_te_thickness_mm"],
                assembly_parameters["airfoil_ring_profile_points"],
                assembly_parameters["create_parabolic_spinner"],
                assembly_parameters["spinner_diameter_mm"],
                assembly_parameters["spinner_length_mm"],
                assembly_parameters["create_ogive_spinner"],
                assembly_parameters["ogive_spinner_diameter_mm"],
                assembly_parameters["ogive_spinner_length_mm"],
                assembly_parameters["nose_radius_fraction"],
            )

            if section_mode == MODE_FLAT:
                detail = _t("result.flat")
            else:
                lines = [_t("result.wrapped")]

                if result.surface_loft_created:
                    lines.append(_t("result.loft_success", name=result.surface_loft_name))
                elif result.surface_loft_requested:
                    lines.append(_t("result.loft_fail", detail=result.surface_loft_error))
                else:
                    lines.append(_t("result.loft_disabled"))

                if result.extension_requested:
                    if result.root_extension_created and result.tip_extension_created:
                        lines.append(_t("result.extend_success", distance=extension_distance_mm))
                    else:
                        lines.append(_t(
                            "result.extend_fail",
                            detail=result.extension_error or _t("common.detail_unavailable"),
                        ))

                if result.cylinders_requested:
                    if result.inner_cylinder_created and result.outer_cylinder_created:
                        lines.append(_t(
                            "result.cylinders_success",
                            inner=result.inner_cylinder_name,
                            outer=result.outer_cylinder_name,
                        ))
                    else:
                        lines.append(_t(
                            "result.cylinders_fail",
                            detail=result.cylinders_error or _t("common.detail_unavailable"),
                        ))

                if result.finalization_requested:
                    if result.solid_created:
                        lines.append(_t("result.finalize_success", name=result.solid_body_name))
                    elif result.stitch_created:
                        lines.append(_t("result.finalize_open", detail=result.finalization_error))
                    else:
                        lines.append(_t("result.finalize_fail", detail=result.finalization_error))

                if result.assembly_requested:
                    if result.assembly_error:
                        lines.append(_t("result.assembly_fail", detail=result.assembly_error))
                    else:
                        assembly_lines = []
                        if result.underside_cut_completed:
                            assembly_lines.append(
                                _t("result.base_cut")
                                if result.underside_cut_applied
                                else _t("result.base_already_clear")
                            )
                        if result.z_offset_applied:
                            assembly_lines.append(_t("result.offset_applied"))
                        assembly_lines.append(_t("result.blade_bodies", count=result.blade_body_count))
                        if result.blade_pattern_created:
                            assembly_lines.append(_t("result.pattern_created"))
                        if result.hub_created:
                            assembly_lines.append(_t("result.hub_created"))
                        if result.hub_joined:
                            assembly_lines.append(_t("result.joined"))

                        if result.airfoil_ring_requested:
                            if result.airfoil_ring_created:
                                assembly_lines.append(
                                    _t(
                                        "result.airfoil_ring_created",
                                        name=result.airfoil_ring_body_name,
                                    )
                                )
                                if result.airfoil_ring_joined:
                                    assembly_lines.append(
                                        _t(
                                            "result.airfoil_ring_joined"
                                        )
                                    )
                                elif result.airfoil_ring_error:
                                    assembly_lines.append(
                                        _t(
                                            "result.airfoil_ring_separate",
                                            detail=(
                                                result.airfoil_ring_error
                                            ),
                                        )
                                    )
                            else:
                                assembly_lines.append(
                                    _t(
                                        "result.airfoil_ring_fail",
                                        detail=(
                                            result.airfoil_ring_error
                                            or _t(
                                                "common.detail_unavailable"
                                            )
                                        ),
                                    )
                                )

                        if result.parabolic_spinner_requested:
                            if result.parabolic_spinner_created:
                                assembly_lines.append(
                                    _t(
                                        "result.parabolic_spinner_created",
                                        name=result.parabolic_spinner_body_name,
                                    )
                                )
                                if result.parabolic_spinner_joined:
                                    assembly_lines.append(
                                        _t("result.parabolic_spinner_joined")
                                    )
                                elif result.parabolic_spinner_error:
                                    assembly_lines.append(
                                        _t(
                                            "result.spinner_separate",
                                            detail=result.parabolic_spinner_error,
                                        )
                                    )
                            else:
                                assembly_lines.append(
                                    _t(
                                        "result.parabolic_spinner_fail",
                                        detail=(
                                            result.parabolic_spinner_error
                                            or _t("common.detail_unavailable")
                                        ),
                                    )
                                )

                        if result.ogive_spinner_requested:
                            if result.ogive_spinner_created:
                                assembly_lines.append(
                                    _t(
                                        "result.ogive_spinner_created",
                                        name=result.ogive_spinner_body_name,
                                    )
                                )
                                if result.ogive_spinner_joined:
                                    assembly_lines.append(
                                        _t("result.ogive_spinner_joined")
                                    )
                                elif result.ogive_spinner_error:
                                    assembly_lines.append(
                                        _t(
                                            "result.spinner_separate",
                                            detail=result.ogive_spinner_error,
                                        )
                                    )
                            else:
                                assembly_lines.append(
                                    _t(
                                        "result.ogive_spinner_fail",
                                        detail=(
                                            result.ogive_spinner_error
                                            or _t("common.detail_unavailable")
                                        ),
                                    )
                                )

                        if result.hoop_requested:
                            if result.hoop_created:
                                assembly_lines.append(
                                    _t(
                                        "result.hoop_created",
                                        name=result.hoop_body_name,
                                    )
                                )
                                if result.hoop_joined:
                                    assembly_lines.append(
                                        _t("result.hoop_joined")
                                    )
                                elif result.hoop_error:
                                    assembly_lines.append(
                                        _t(
                                            "result.hoop_separate",
                                            detail=result.hoop_error,
                                        )
                                    )
                            else:
                                assembly_lines.append(
                                    _t(
                                        "result.hoop_fail",
                                        detail=(
                                            result.hoop_error
                                            or _t("common.detail_unavailable")
                                        ),
                                    )
                                )

                        if result.final_propeller_created:
                            assembly_lines.append(
                                _t(
                                    "result.final",
                                    name=result.final_propeller_name,
                                )
                            )
                        lines.append("\n".join(assembly_lines))

                detail = "\n\n".join(lines)

            visibility_note = _t("result.hidden") if hide_created_sketches else _t("result.visible")
            transition_radius_mm = (
                radii_config.root_radius_mm
                + radii_config.blade_length_mm * radii_config.transition_point
            )
            distribution_note = _t(
                "result.distribution",
                mode=radius_distribution_mode,
                root=resolved_radii[0],
                transition=transition_radius_mm,
                tip=resolved_radii[-1],
            )

            result_message = (
                _t(
                    "result.header",
                    count=result.section_count,
                    component=result.component_name,
                )
                + "\n\n" + distribution_note
                + "\n\n" + detail
                + "\n\n" + visibility_note
            )
            _queue_post_termination_result(
                timeline_group_request,
                result_message,
                incomplete=False,
            )
        except Exception:
            error_message = _t(
                "error.generate",
                detail=traceback.format_exc(),
            )

            # If geometry creation had already begun, delay the error message
            # too. The transaction will then be committed before any partial
            # features are inspected and grouped.
            if timeline_group_request is not None:
                _queue_post_termination_result(
                    timeline_group_request,
                    error_message,
                    incomplete=True,
                )
            else:
                UI.messageBox(error_message)


class CommandTerminatedHandler(
    adsk.core.ApplicationCommandEventHandler
):
    def notify(self, args: adsk.core.ApplicationCommandEventArgs):
        global _pending_timeline_run

        try:
            if args.commandId != CMD_ID:
                return

            pending = _pending_timeline_run
            _pending_timeline_run = None
            if not pending:
                return

            group_name, group_error, skipped_message = (
                _create_timeline_group_for_run(
                    pending["request"],
                    incomplete=pending["incomplete"],
                )
            )

            if group_name:
                if pending["incomplete"]:
                    timeline_note = _t(
                        "error.timeline_partial_group",
                        name=group_name,
                    )
                else:
                    timeline_note = _t(
                        "result.timeline_group",
                        name=group_name,
                    )
            elif skipped_message:
                timeline_note = skipped_message
            else:
                timeline_note = _t(
                    "result.timeline_group_fail",
                    detail=group_error,
                )

            UI.messageBox(
                pending["message"]
                + "\n\n"
                + timeline_note
            )
        except Exception:
            _pending_timeline_run = None
            UI.messageBox(
                _t(
                    "error.timeline_post_commit",
                    detail=traceback.format_exc(),
                )
            )


class CommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args: adsk.core.InputChangedEventArgs):
        try:
            changed_input = args.input
            if not changed_input:
                return

            command_inputs = args.firingEvent.sender.commandInputs

            if changed_input.id == "restoreDefaults":
                try:
                    factory_config = _load_factory_config()
                    _apply_config_to_dialog(
                        command_inputs,
                        factory_config,
                    )
                    _delete_user_configuration()
                    UI.messageBox(_t("restore.success"))
                except Exception:
                    UI.messageBox(
                        _t(
                            "restore.error",
                            detail=traceback.format_exc(),
                        )
                    )
            elif changed_input.id == "radiusDistributionMode":
                _update_radius_distribution_inputs(command_inputs)
            elif changed_input.id in (
                "createTipRing",
                "tipRingType",
            ):
                _update_tip_ring_inputs(command_inputs)
            elif changed_input.id in (
                "createSpinner",
                "spinnerType",
            ):
                _update_spinner_inputs(command_inputs)
        except Exception:
            UI.messageBox(
                _t("error.update_radius", detail=traceback.format_exc())
            )


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args: adsk.core.CommandCreatedEventArgs):
        global _pending_timeline_run

        try:
            _pending_timeline_run = None
            raw_config = _load_raw_config()

            default_radii = raw_config.get(
                "Section_Radii",
                [4.15, 5.15, 6.15, 7.15, 8.15, 14.335, 38.1],
            )
            default_radii_text = "; ".join(
                f"{float(value):g}" for value in default_radii
            )

            radius_distribution_default = _normalize_radius_distribution_mode(
                raw_config.get("Section_Distribution_Mode", "spacing")
            )
            section_spacing_default_mm = float(
                raw_config.get("Section_Spacing_mm", 1.0)
            )
            default_blade_length_mm = 0.5 * (
                float(raw_config["Propeller_Diameter"])
                - float(raw_config["Hub_Diameter"])
            )
            section_slices_default = int(
                raw_config.get(
                    "Section_Slices",
                    max(
                        1,
                        round(
                            default_blade_length_mm
                            / max(section_spacing_default_mm, 1e-9)
                        ),
                    ),
                )
            )
            section_slices_default = max(1, min(998, section_slices_default))

            apply_angle_default = bool(
                raw_config.get("Apply_Geometric_Angle", True)
            )
            create_loft_default = bool(
                raw_config.get("Create_Surface_Loft", True)
            )
            extend_ends_default = bool(
                raw_config.get("Extend_Surface_Ends", True)
            )
            extension_distance_default_mm = float(
                raw_config.get("Surface_Extension_mm", 0.1)
            )
            create_cylinders_default = bool(
                raw_config.get("Create_Limit_Cylinders", True)
            )
            cylinder_margin_default_mm = float(
                raw_config.get("Cylinder_Axial_Margin_mm", 1.0)
            )
            finalize_solid_default = bool(
                raw_config.get("Finalize_Solid", True)
            )
            stitch_tolerance_default_mm = float(
                raw_config.get("Stitch_Tolerance_mm", 0.01)
            )
            hide_sketches_default = bool(
                raw_config.get("Hide_Created_Sketches", True)
            )
            number_of_blades_default = int(
                raw_config.get("Number_of_Blades", 2)
            )
            hub_length_default_mm = float(
                raw_config.get("Hub_Length", 5.0)
            )
            hole_diameter_default_mm = float(
                raw_config.get("Hole_Diameter", 3.0)
            )
            prop_z_offset_default_mm = float(
                raw_config.get("Prop_Z_Offset", 0.0)
            )
            cut_below_default = bool(
                raw_config.get("Cut_Below_Hub_Base", True)
            )
            create_pattern_default = bool(
                raw_config.get("Create_Blade_Pattern", True)
            )
            create_hub_default = bool(
                raw_config.get("Create_Hub_And_Join", True)
            )
            create_hoop_default = bool(
                raw_config.get("Hoop", False)
            )
            hoop_thickness_default_mm = float(
                raw_config.get("Hoop_Thickness", 1.2)
            )
            hoop_height_default_mm = float(
                raw_config.get("Hoop_Height", 6.0)
            )
            hoop_offset_default_mm = float(
                raw_config.get("Hoop_Offset", 0.0)
            )
            create_airfoil_ring_default = bool(
                raw_config.get("Airfoil_Ring", False)
            )
            airfoil_ring_naca_default = str(
                raw_config.get("Airfoil_Ring_NACA", "0015")
            ).zfill(4)
            airfoil_ring_chord_default_mm = float(
                raw_config.get("Airfoil_Ring_Chord", 0.0)
            )
            airfoil_ring_diameter_default_mm = float(
                raw_config.get(
                    "Airfoil_Ring_Diameter",
                    raw_config.get("Propeller_Diameter", 76.2),
                )
            )
            airfoil_ring_axial_offset_default_mm = float(
                raw_config.get("Airfoil_Ring_Axial_Offset", 0.0)
            )
            airfoil_ring_te_thickness_default_mm = float(
                raw_config.get("Airfoil_Ring_TE_Thickness", 0.4)
            )
            airfoil_ring_profile_points_default = int(
                raw_config.get("Airfoil_Ring_Profile_Points", 20)
            )
            airfoil_ring_profile_points_default = max(
                2,
                min(200, airfoil_ring_profile_points_default),
            )

            parabolic_spinner_default = bool(
                raw_config.get("Parabolic_Spinner_Yes", False)
            )
            spinner_diameter_default_mm = float(
                raw_config.get("Spinner_Diameter", 20.0)
            )
            spinner_length_default_mm = float(
                raw_config.get("Spinner_Length", 20.0)
            )
            ogive_spinner_default = bool(
                raw_config.get("Ogive_Spinner_Yes", False)
            )
            ogive_spinner_diameter_default_mm = float(
                raw_config.get("Ogive_Spinner_Diameter", 20.0)
            )
            ogive_spinner_length_default_mm = float(
                raw_config.get("Ogive_Spinner_Length", 20.0)
            )
            nose_radius_default = float(
                raw_config.get("Nose_Radius", 0.24)
            )

            create_tip_ring_default = bool(
                create_hoop_default or create_airfoil_ring_default
            )
            tip_ring_type_default = (
                TIP_RING_TYPE_AERODYNAMIC
                if (
                    create_airfoil_ring_default
                    and not create_hoop_default
                )
                else TIP_RING_TYPE_RECTANGULAR
            )

            create_spinner_default = bool(
                parabolic_spinner_default or ogive_spinner_default
            )
            spinner_type_default = (
                SPINNER_TYPE_OGIVE
                if (
                    ogive_spinner_default
                    and not parabolic_spinner_default
                )
                else SPINNER_TYPE_PARABOLIC
            )

            profile_points_default = int(
                raw_config.get("Profile_Points", 41)
            )
            if profile_points_default == 0:
                profile_points_default = 41
            profile_points_default = min(
                401,
                max(2, profile_points_default),
            )

            raw_mode = str(
                raw_config.get("Section_Mode", "wrapped_3d")
            ).strip().lower()
            wrapped_default = raw_mode not in {
                "flat",
                "flat_2d",
                "2d",
                "planar",
            }

            command = args.command
            command.isRepeatable = True
            command.okButtonText = _t("ui.generate")
            command.setDialogInitialSize(
                DIALOG_INITIAL_WIDTH,
                DIALOG_INITIAL_HEIGHT,
            )
            command.setDialogMinimumSize(
                DIALOG_MINIMUM_WIDTH,
                DIALOG_MINIMUM_HEIGHT,
            )

            inputs = command.commandInputs

            # Generate automatically remembers every validated value.
            # This button restores the immutable configuration distributed
            # with the add-in without generating or modifying geometry.
            restore_button = inputs.addBoolValueInput(
                "restoreDefaults",
                _t("ui.restore_defaults"),
                False,
                "",
                False,
            )
            restore_button.isFullWidth = True
            restore_button.tooltip = _t(
                "ui.restore_defaults_tooltip"
            )
            restore_button.tooltipDescription = _t(
                "ui.restore_defaults_tooltip_description"
            )

            # ---------------------------------------------------------------
            # Group: global propeller geometry
            # ---------------------------------------------------------------
            geometry_group = inputs.addGroupCommandInput(
                "geometryGroup",
                _t("ui.group.geometry"),
            )
            geometry_group.isExpanded = True
            geometry_inputs = geometry_group.children

            geometry_inputs.addIntegerSpinnerCommandInput(
                "numberOfBlades",
                _t("ui.number_of_blades"),
                1,
                12,
                1,
                max(1, min(12, number_of_blades_default)),
            )
            geometry_inputs.addValueInput(
                "propellerDiameter",
                _t("ui.propeller_diameter"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{float(raw_config['Propeller_Diameter']):g} mm"
                ),
            )
            geometry_inputs.addValueInput(
                "bladePitch",
                _t("ui.blade_pitch"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{float(raw_config['Blade_Pitch']):g} mm"
                ),
            )

            direction_input = geometry_inputs.addDropDownCommandInput(
                "propDirection",
                _t("ui.prop_direction"),
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            direction_default = int(raw_config["Prop_Direction"])
            direction_input.listItems.add("-1", direction_default == -1)
            direction_input.listItems.add("+1", direction_default == 1)

            geometry_inputs.addValueInput(
                "propZOffset",
                _t("ui.prop_z_offset"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{prop_z_offset_default_mm:g} mm"
                ),
            )
            geometry_inputs.addStringValueInput(
                "maxChordFraction",
                _t("ui.max_chord_fraction"),
                f"{float(raw_config['Max_Chord_Fraction']):g}",
            )
            geometry_inputs.addValueInput(
                "rootLength",
                _t("ui.root_length"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{float(raw_config['Root_Length']):g} mm"
                ),
            )
            geometry_inputs.addStringValueInput(
                "elenFraction",
                _t("ui.elen_fraction"),
                f"{float(raw_config['Elen_Fraction']):g}",
            )
            geometry_inputs.addStringValueInput(
                "sweepAngle",
                _t("ui.sweep_angle"),
                f"{float(raw_config['Sweep_Angle']):g}",
            )

            # ---------------------------------------------------------------
            # Group: airfoil definitions and transitions
            # ---------------------------------------------------------------
            profiles_group = inputs.addGroupCommandInput(
                "profilesGroup",
                _t("ui.group.profiles"),
            )
            profiles_group.isExpanded = True
            profiles_inputs = profiles_group.children

            profiles_inputs.addStringValueInput(
                "rootNaca",
                _t("ui.root_naca"),
                str(raw_config["Root_NACA_Airfoil"]).zfill(4),
            )
            profiles_inputs.addStringValueInput(
                "midNaca",
                _t("ui.mid_naca"),
                str(raw_config["Mid_NACA_Airfoil"]).zfill(4),
            )
            profiles_inputs.addStringValueInput(
                "tipNaca",
                _t("ui.tip_naca"),
                str(raw_config["Tip_NACA_Airfoil"]).zfill(4),
            )
            profiles_inputs.addStringValueInput(
                "transitionPoint",
                _t("ui.transition_point"),
                f"{float(raw_config['Transition_Point']):g}",
            )
            profiles_inputs.addValueInput(
                "trailingEdgeThickness",
                _t("ui.trailing_edge_thickness"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{float(raw_config['Trailing_Edge_Thickness']):g} mm"
                ),
            )
            profiles_inputs.addValueInput(
                "fairingSize",
                _t("ui.fairing_size"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{float(raw_config['Fairing_Size']):g} mm"
                ),
            )

            # ---------------------------------------------------------------
            # Group: hub
            # ---------------------------------------------------------------
            hub_group = inputs.addGroupCommandInput(
                "hubGroup",
                _t("ui.group.assembly"),
            )
            hub_group.isExpanded = True
            hub_inputs = hub_group.children

            hub_inputs.addBoolValueInput(
                "createHubAndJoin",
                _t("ui.create_hub"),
                True,
                "",
                create_hub_default,
            )
            hub_inputs.addValueInput(
                "hubDiameter",
                _t("ui.hub_diameter"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{float(raw_config['Hub_Diameter']):g} mm"
                ),
            )
            hub_inputs.addValueInput(
                "hubLength",
                _t("ui.hub_length"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{hub_length_default_mm:g} mm"
                ),
            )
            hub_inputs.addValueInput(
                "holeDiameter",
                _t("ui.hole_diameter"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{hole_diameter_default_mm:g} mm"
                ),
            )

            # ---------------------------------------------------------------
            # Group: radial and airfoil resolution
            # ---------------------------------------------------------------
            sections_group = inputs.addGroupCommandInput(
                "sectionsGroup",
                _t("ui.group.sections"),
            )
            sections_group.isExpanded = False
            sections_inputs = sections_group.children

            sections_inputs.addIntegerSpinnerCommandInput(
                "profilePoints",
                _t("ui.profile_points"),
                2,
                401,
                1,
                profile_points_default,
            )

            radius_distribution_input = sections_inputs.addDropDownCommandInput(
                "radiusDistributionMode",
                _t("ui.radius_distribution"),
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            radius_distribution_input.listItems.add(
                RADIUS_MODE_MANUAL,
                radius_distribution_default == RADIUS_MODE_MANUAL,
            )
            radius_distribution_input.listItems.add(
                RADIUS_MODE_SPACING,
                radius_distribution_default == RADIUS_MODE_SPACING,
            )
            radius_distribution_input.listItems.add(
                RADIUS_MODE_SLICES,
                radius_distribution_default == RADIUS_MODE_SLICES,
            )

            radii_input = sections_inputs.addStringValueInput(
                "radii",
                _t("ui.manual_radii"),
                default_radii_text,
            )
            radii_input.isFullWidth = False

            spacing_input = sections_inputs.addValueInput(
                "sectionSpacing",
                _t("ui.section_spacing"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{section_spacing_default_mm:g} mm"
                ),
            )
            spacing_input.minimumValue = 0.001

            sections_inputs.addIntegerSpinnerCommandInput(
                "sectionSlices",
                _t("ui.section_slices"),
                1,
                998,
                1,
                section_slices_default,
            )

            radius_info = sections_inputs.addTextBoxCommandInput(
                "radiusDistributionInfo",
                "",
                _t("ui.radius_info"),
                3,
                True,
            )
            radius_info.isFullWidth = True

            # ---------------------------------------------------------------
            # Group: mutually exclusive tip-ring types
            # ---------------------------------------------------------------
            tip_ring_group = inputs.addGroupCommandInput(
                "tipRingGroup",
                _t("ui.group.tip_ring"),
            )
            tip_ring_group.isExpanded = create_tip_ring_default
            tip_ring_inputs = tip_ring_group.children

            create_tip_ring_input = tip_ring_inputs.addBoolValueInput(
                "createTipRing",
                _t("ui.create_tip_ring"),
                True,
                "",
                create_tip_ring_default,
            )
            create_tip_ring_input.tooltipDescription = _t(
                "ui.tip_ring_description"
            )

            tip_ring_type_input = tip_ring_inputs.addDropDownCommandInput(
                "tipRingType",
                _t("ui.tip_ring_type"),
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            tip_ring_type_input.listItems.add(
                TIP_RING_TYPE_RECTANGULAR,
                tip_ring_type_default == TIP_RING_TYPE_RECTANGULAR,
            )
            tip_ring_type_input.listItems.add(
                TIP_RING_TYPE_AERODYNAMIC,
                tip_ring_type_default == TIP_RING_TYPE_AERODYNAMIC,
            )

            hoop_thickness_input = tip_ring_inputs.addValueInput(
                "hoopThickness",
                _t("ui.hoop_thickness"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{hoop_thickness_default_mm:g} mm"
                ),
            )
            hoop_thickness_input.minimumValue = 0.001

            hoop_height_input = tip_ring_inputs.addValueInput(
                "hoopHeight",
                _t("ui.hoop_height"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{hoop_height_default_mm:g} mm"
                ),
            )
            hoop_height_input.minimumValue = 0.001

            tip_ring_inputs.addValueInput(
                "hoopOffset",
                _t("ui.hoop_offset"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{hoop_offset_default_mm:g} mm"
                ),
            )

            tip_ring_inputs.addStringValueInput(
                "airfoilRingNaca",
                _t("ui.airfoil_ring_naca"),
                airfoil_ring_naca_default,
            )
            tip_ring_inputs.addValueInput(
                "airfoilRingChord",
                _t("ui.airfoil_ring_chord"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{airfoil_ring_chord_default_mm:g} mm"
                ),
            )
            tip_ring_inputs.addValueInput(
                "airfoilRingDiameter",
                _t("ui.airfoil_ring_diameter"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{airfoil_ring_diameter_default_mm:g} mm"
                ),
            )
            tip_ring_inputs.addValueInput(
                "airfoilRingAxialOffset",
                _t("ui.airfoil_ring_axial_offset"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{airfoil_ring_axial_offset_default_mm:g} mm"
                ),
            )
            tip_ring_inputs.addValueInput(
                "airfoilRingTeThickness",
                _t("ui.airfoil_ring_te_thickness"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{airfoil_ring_te_thickness_default_mm:g} mm"
                ),
            )
            tip_ring_inputs.addIntegerSpinnerCommandInput(
                "airfoilRingProfilePoints",
                _t("ui.airfoil_ring_profile_points"),
                2,
                200,
                1,
                airfoil_ring_profile_points_default,
            )

            # ---------------------------------------------------------------
            # Group: mutually exclusive spinner types
            # ---------------------------------------------------------------
            spinner_group = inputs.addGroupCommandInput(
                "spinnerGroup",
                _t("ui.group.spinners"),
            )
            spinner_group.isExpanded = create_spinner_default
            spinner_inputs = spinner_group.children

            create_spinner_input = spinner_inputs.addBoolValueInput(
                "createSpinner",
                _t("ui.create_spinner"),
                True,
                "",
                create_spinner_default,
            )
            create_spinner_input.tooltipDescription = _t(
                "ui.spinner_description"
            )

            spinner_type_input = spinner_inputs.addDropDownCommandInput(
                "spinnerType",
                _t("ui.spinner_type"),
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            spinner_type_input.listItems.add(
                SPINNER_TYPE_PARABOLIC,
                spinner_type_default == SPINNER_TYPE_PARABOLIC,
            )
            spinner_type_input.listItems.add(
                SPINNER_TYPE_OGIVE,
                spinner_type_default == SPINNER_TYPE_OGIVE,
            )

            parabolic_diameter_input = spinner_inputs.addValueInput(
                "spinnerDiameter",
                _t("ui.spinner_diameter"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{spinner_diameter_default_mm:g} mm"
                ),
            )
            parabolic_diameter_input.minimumValue = 0.001

            parabolic_length_input = spinner_inputs.addValueInput(
                "spinnerLength",
                _t("ui.spinner_length"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{spinner_length_default_mm:g} mm"
                ),
            )
            parabolic_length_input.minimumValue = 0.001

            ogive_diameter_input = spinner_inputs.addValueInput(
                "ogiveSpinnerDiameter",
                _t("ui.ogive_spinner_diameter"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{ogive_spinner_diameter_default_mm:g} mm"
                ),
            )
            ogive_diameter_input.minimumValue = 0.001

            ogive_length_input = spinner_inputs.addValueInput(
                "ogiveSpinnerLength",
                _t("ui.ogive_spinner_length"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{ogive_spinner_length_default_mm:g} mm"
                ),
            )
            ogive_length_input.minimumValue = 0.001

            spinner_inputs.addStringValueInput(
                "noseRadius",
                _t("ui.nose_radius"),
                f"{nose_radius_default:g}",
            )

            # ---------------------------------------------------------------
            # Group: display-only behavior
            # ---------------------------------------------------------------
            display_group = inputs.addGroupCommandInput(
                "displayGroup",
                _t("ui.group.display"),
            )
            display_group.isExpanded = False
            display_inputs = display_group.children

            display_inputs.addBoolValueInput(
                "hideCreatedSketches",
                _t("ui.hide_sketches"),
                True,
                "",
                hide_sketches_default,
            )

            # ---------------------------------------------------------------
            # Group: diagnostic and construction controls
            # ---------------------------------------------------------------
            operations_group = inputs.addGroupCommandInput(
                "operationsGroup",
                _t("ui.group.operations"),
            )
            operations_group.isExpanded = False
            operations_inputs = operations_group.children

            mode_input = operations_inputs.addDropDownCommandInput(
                "sectionMode",
                _t("ui.section_type"),
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            mode_input.listItems.add(MODE_FLAT, not wrapped_default)
            mode_input.listItems.add(MODE_WRAPPED, wrapped_default)

            operations_inputs.addBoolValueInput(
                "applyAngle",
                _t("ui.apply_pitch_angle"),
                True,
                "",
                apply_angle_default,
            )
            operations_inputs.addStringValueInput(
                "centerline",
                _t("ui.centerline"),
                f"{float(raw_config['Centerline']):g}",
            )
            operations_inputs.addBoolValueInput(
                "createSurfaceLoft",
                _t("ui.create_loft"),
                True,
                "",
                create_loft_default,
            )
            operations_inputs.addBoolValueInput(
                "extendSurfaceEnds",
                _t("ui.extend_ends"),
                True,
                "",
                extend_ends_default,
            )

            extension_input = operations_inputs.addValueInput(
                "extensionDistance",
                _t("ui.extension_distance"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{extension_distance_default_mm:g} mm"
                ),
            )
            extension_input.minimumValue = 0.001

            operations_inputs.addBoolValueInput(
                "createLimitCylinders",
                _t("ui.create_cylinders"),
                True,
                "",
                create_cylinders_default,
            )

            margin_input = operations_inputs.addValueInput(
                "cylinderAxialMargin",
                _t("ui.cylinder_margin"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{cylinder_margin_default_mm:g} mm"
                ),
            )
            margin_input.minimumValue = 0.0

            operations_inputs.addBoolValueInput(
                "finalizeSolid",
                _t("ui.finalize_solid"),
                True,
                "",
                finalize_solid_default,
            )

            stitch_input = operations_inputs.addValueInput(
                "stitchTolerance",
                _t("ui.stitch_tolerance"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{stitch_tolerance_default_mm:g} mm"
                ),
            )
            stitch_input.minimumValue = 0.0001

            operations_inputs.addBoolValueInput(
                "cutBelowHubBase",
                _t("ui.cut_below"),
                True,
                "",
                cut_below_default,
            )
            operations_inputs.addBoolValueInput(
                "createBladePattern",
                _t("ui.create_pattern"),
                True,
                "",
                create_pattern_default,
            )

            _update_radius_distribution_inputs(inputs)
            _update_tip_ring_inputs(inputs)
            _update_spinner_inputs(inputs)

            input_changed_handler = CommandInputChangedHandler()
            command.inputChanged.add(input_changed_handler)
            _handlers.append(input_changed_handler)

            execute_handler = CommandExecuteHandler()
            command.execute.add(execute_handler)
            _handlers.append(execute_handler)
        except Exception:
            UI.messageBox(
                _t("error.open_command", detail=traceback.format_exc())
            )


def run(context):
    global _control
    global _pending_timeline_run

    try:
        _pending_timeline_run = None

        terminated_handler = CommandTerminatedHandler()
        UI.commandTerminated.add(terminated_handler)
        _handlers.append(terminated_handler)

        command_definitions = UI.commandDefinitions
        command_definition = command_definitions.itemById(CMD_ID)
        if not command_definition:
            command_definition = command_definitions.addButtonDefinition(
                CMD_ID,
                CMD_NAME,
                CMD_DESCRIPTION,
                "",
            )
        else:
            command_definition.name = CMD_NAME

        created_handler = CommandCreatedHandler()
        command_definition.commandCreated.add(created_handler)
        _handlers.append(created_handler)

        workspace = UI.workspaces.itemById(WORKSPACE_ID)
        panel = None
        if workspace:
            for panel_id in PANEL_IDS:
                panel = workspace.toolbarPanels.itemById(panel_id)
                if panel:
                    break

        if panel:
            existing_control = panel.controls.itemById(CMD_ID)
            _control = existing_control or panel.controls.addCommand(command_definition)
            if _control:
                _control.isPromoted = True
                _control.isPromotedByDefault = True
        else:
            UI.messageBox(_t("error.panel", id=CMD_ID))
    except Exception:
        UI.messageBox(_t("error.start", detail=traceback.format_exc()))


def stop(context):
    global _control
    global _pending_timeline_run

    try:
        _pending_timeline_run = None
        workspace = UI.workspaces.itemById(WORKSPACE_ID)
        if workspace:
            for panel_id in PANEL_IDS:
                panel = workspace.toolbarPanels.itemById(panel_id)
                if panel:
                    control = panel.controls.itemById(CMD_ID)
                    if control:
                        control.deleteMe()

        command_definition = UI.commandDefinitions.itemById(CMD_ID)
        if command_definition:
            command_definition.deleteMe()

        _control = None
        _handlers.clear()
    except Exception:
        UI.messageBox(_t("error.stop", detail=traceback.format_exc()))
