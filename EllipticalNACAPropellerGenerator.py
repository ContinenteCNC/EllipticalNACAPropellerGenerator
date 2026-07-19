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
* Sweep_Angle keeps the experimentally validated Fusion/OpenSCAD mapping in
  sweep_origin_angle_deg(). Prop_Direction already mirrors the effective sweep,
  so callers must not negate Sweep_Angle when changing propeller direction.
* Propeller_Orientation is a rigid final-assembly transform. It must not alter
  Prop_Direction, Sweep_Angle, pitch, or any blade-generation equation.
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

from dataclasses import dataclass, fields, replace
from datetime import datetime, timezone

import adsk.core
import adsk.fusion
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import traceback
import textwrap
import uuid
import unicodedata

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
SAMPLES_DIRECTORY_NAME = "configurations"
USER_SAMPLES_DIRECTORY_NAME = "configurations"
LEGACY_USER_SAMPLES_DIRECTORY_NAME = "samples"
MANUAL_LOG_DIRECTORY_NAME = "manual_generation_logs"

DEFAULT_CONFIG_PATH = os.path.join(
    BASE_DIRECTORY,
    DEFAULT_CONFIG_FILENAME,
)
SAMPLES_DIRECTORY = os.path.join(
    BASE_DIRECTORY,
    SAMPLES_DIRECTORY_NAME,
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
USER_SAMPLES_DIRECTORY = os.path.join(
    USER_CONFIG_DIRECTORY,
    USER_SAMPLES_DIRECTORY_NAME,
)
LEGACY_USER_SAMPLES_DIRECTORY = os.path.join(
    USER_CONFIG_DIRECTORY,
    LEGACY_USER_SAMPLES_DIRECTORY_NAME,
)
MANUAL_LOG_DIRECTORY = os.path.join(
    USER_CONFIG_DIRECTORY,
    MANUAL_LOG_DIRECTORY_NAME,
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
PROJECT_VERSION = "1.1.1"
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

# Fusion auto-sizes ProgressDialog to its longest message line. Keep every
# manual-progress line short so a late diagnostic string cannot expand the
# dialog to nearly the full screen width.
MANUAL_PROGRESS_LINE_WIDTH = 54
MANUAL_PROGRESS_MAX_DETAIL_LINES = 3

_handlers: list[object] = []
_control = None


@dataclass(frozen=True)
class SampleConfiguration:
    """One JSON configuration discovered under a configurations directory."""

    menu_label: str
    display_name: str
    description: str
    relative_path: str
    parameters: dict


_sample_catalog: dict[str, SampleConfiguration] = {}
_sample_discovery_errors: list[str] = []
_dialog_config_base: dict | None = None

# One Fusion command can be active at a time. A successful execute handler
# stores its result here so timeline grouping and the final message occur only
# after the native Generate/OK action terminates the command and commits its
# transaction. This avoids grouping or visibility changes being rolled back.
_pending_timeline_run = None
_active_manual_progress = None


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


def _set_dialog_config_base(config: dict | None) -> None:
    """Set the JSON base preserved while the current dialog is open."""
    global _dialog_config_base
    _dialog_config_base = dict(config) if isinstance(config, dict) else None


def _current_dialog_config_base() -> dict:
    """Return the active dialog base without exposing mutable global state."""
    if isinstance(_dialog_config_base, dict):
        return dict(_dialog_config_base)
    return _load_raw_config()


def _localized_sample_metadata(
    data: dict,
    key: str,
    fallback: str,
) -> str:
    """Read optional localized sample metadata with English fallback."""
    translations = data.get(f"{key}_i18n")
    if isinstance(translations, dict):
        candidates = (
            ACTIVE_LOCALE,
            ACTIVE_LOCALE.split("-", 1)[0],
            "en",
        )
        for candidate in candidates:
            value = translations.get(candidate)
            if isinstance(value, str) and value.strip():
                return value.strip()

    value = data.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _migrate_legacy_user_samples_directory() -> list[str]:
    """Copy legacy per-user ``samples`` JSON files into ``configurations``.

    Version 1.1 renamed the user-facing library and its filesystem directory.
    Existing files are copied once, without overwriting files already present
    in the new location. The old directory is left untouched as a safe backup.
    """
    errors: list[str] = []
    if not os.path.isdir(LEGACY_USER_SAMPLES_DIRECTORY):
        return errors

    try:
        os.makedirs(USER_SAMPLES_DIRECTORY, exist_ok=True)
    except Exception:
        return [traceback.format_exc()]

    for directory, subdirectories, filenames in os.walk(
        LEGACY_USER_SAMPLES_DIRECTORY
    ):
        subdirectories.sort(key=str.casefold)
        for filename in sorted(filenames, key=str.casefold):
            if not filename.lower().endswith(".json"):
                continue
            source_path = os.path.join(directory, filename)
            relative_path = os.path.relpath(
                source_path,
                LEGACY_USER_SAMPLES_DIRECTORY,
            )
            target_path = os.path.join(
                USER_SAMPLES_DIRECTORY,
                relative_path,
            )
            if os.path.exists(target_path):
                continue
            try:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(source_path, "rb") as source_file:
                    payload = source_file.read()
                temporary_path = f"{target_path}.{uuid.uuid4().hex}.tmp"
                with open(temporary_path, "wb") as target_file:
                    target_file.write(payload)
                    target_file.flush()
                    os.fsync(target_file.fileno())
                os.replace(temporary_path, target_path)
            except Exception:
                errors.append(
                    f"{source_path}: {traceback.format_exc()}"
                )
    return errors


def _sample_search_roots() -> tuple[tuple[str, str], ...]:
    """Return every filesystem root searched for configuration JSON files."""
    return (
        ("builtin", SAMPLES_DIRECTORY),
        ("user", USER_SAMPLES_DIRECTORY),
    )


def _discover_sample_configurations() -> tuple[dict, list[str]]:
    """Discover built-in and user-created JSON configurations."""
    catalog: dict[str, SampleConfiguration] = {}
    errors: list[str] = _migrate_legacy_user_samples_directory()
    candidates: list[tuple[str, str, str]] = []

    for source_name, root_directory in _sample_search_roots():
        if not os.path.isdir(root_directory):
            continue
        for directory, subdirectories, filenames in os.walk(root_directory):
            subdirectories.sort(key=str.casefold)
            for filename in sorted(filenames, key=str.casefold):
                if not filename.lower().endswith(".json"):
                    continue
                absolute_path = os.path.join(directory, filename)
                relative_path = os.path.relpath(
                    absolute_path,
                    root_directory,
                ).replace(os.sep, "/")
                candidates.append(
                    (source_name, relative_path, absolute_path)
                )

    parsed: list[tuple[str, str, str, str, dict]] = []
    metadata_keys = {
        "Sample_Name",
        "Sample_Name_i18n",
        "Sample_Description",
        "Sample_Description_i18n",
        "Schema_Version",
        "Source",
        "Source_Module",
        "Source_Reference",
        "Adaptation_Notes",
        "Created_At_UTC",
        "Project_Version",
    }

    for source_name, relative_path, absolute_path in candidates:
        qualified_path = f"{source_name}:{relative_path}"
        try:
            data = _read_config_object(absolute_path, qualified_path)
            if "Parameters" in data:
                raw_parameters = data["Parameters"]
                if not isinstance(raw_parameters, dict):
                    raise ValueError(
                        "Parameters deve conter um objeto JSON."
                    )
                parameters = dict(raw_parameters)
            else:
                parameters = {
                    key: value
                    for key, value in data.items()
                    if key not in metadata_keys
                }

            # Samples never select the add-in language. The current user
            # language is preserved independently when a sample is loaded.
            parameters.pop("Interface_Language", None)

            filename_stem = Path(relative_path).stem.replace("_", " ")
            display_name = _localized_sample_metadata(
                data,
                "Sample_Name",
                filename_stem,
            )
            description = _localized_sample_metadata(
                data,
                "Sample_Description",
                _t("sample.no_description"),
            )
            parsed.append(
                (
                    display_name,
                    description,
                    qualified_path,
                    source_name,
                    parameters,
                )
            )
        except Exception as error:
            errors.append(
                f"{qualified_path}: {type(error).__name__}: {error}"
            )

    parsed.sort(
        key=lambda item: (
            0 if item[3] == "user" else 1,
            item[0].casefold(),
            item[2].casefold(),
        )
    )
    used_labels: set[str] = set()
    for display_name, description, relative_path, source_name, parameters in parsed:
        menu_label = display_name
        if menu_label in used_labels:
            source_label = (
                _t("sample.source_user")
                if source_name == "user"
                else _t("sample.source_builtin")
            )
            menu_label = f"{display_name} — {source_label}"
        suffix = 2
        base_label = menu_label
        while menu_label in used_labels:
            menu_label = f"{base_label} ({suffix})"
            suffix += 1
        used_labels.add(menu_label)
        catalog[menu_label] = SampleConfiguration(
            menu_label=menu_label,
            display_name=display_name,
            description=description,
            relative_path=relative_path,
            parameters=parameters,
        )

    return catalog, errors


def _selected_sample(
    inputs: adsk.core.CommandInputs,
) -> SampleConfiguration | None:
    try:
        selected_name = _selected_dropdown_name(
            inputs,
            "sampleConfiguration",
        )
    except Exception:
        return None
    return _sample_catalog.get(selected_name)


def _sample_discovery_note() -> str:
    if not _sample_discovery_errors:
        return ""
    return _t(
        "sample.invalid_count",
        count=len(_sample_discovery_errors),
    )


def _sample_tooltip_description() -> str:
    base = _t(
        "ui.samples_scan_tooltip_description",
        path=(SAMPLES_DIRECTORY + "\n" + USER_SAMPLES_DIRECTORY),
    )
    if not _sample_discovery_errors:
        return base
    details = "\n".join(_sample_discovery_errors[:5])
    if len(_sample_discovery_errors) > 5:
        details += "\n…"
    return base + "\n\n" + _t(
        "sample.invalid_details",
        details=details,
    )


def _update_sample_description(
    inputs: adsk.core.CommandInputs,
    loaded: bool = False,
) -> None:
    text_box = adsk.core.TextBoxCommandInput.cast(
        _required_command_input(inputs, "sampleDescription")
    )
    if text_box is None:
        raise RuntimeError(
            "sampleDescription não é um TextBoxCommandInput."
        )

    sample = _selected_sample(inputs)
    if sample is None:
        text = _t(
            "sample.none_found",
            path=(SAMPLES_DIRECTORY + "\n" + USER_SAMPLES_DIRECTORY),
        )
    else:
        text = _t(
            "sample.description",
            description=sample.description,
            file=sample.relative_path,
        )
        if loaded:
            text += "\n\n" + _t("sample.loaded_status")

    discovery_note = _sample_discovery_note()
    if discovery_note:
        text += "\n\n" + discovery_note
    text_box.formattedText = text


def _load_selected_sample(
    inputs: adsk.core.CommandInputs,
) -> SampleConfiguration:
    sample = _selected_sample(inputs)
    if sample is None:
        raise ValueError(_t("sample.none_selected"))

    config = _load_factory_config()
    config.update(sample.parameters)
    config["Interface_Language"] = _current_dialog_config_base().get(
        "Interface_Language",
        "auto",
    )

    _apply_config_to_dialog(inputs, config)
    _set_dialog_config_base(config)
    _update_sample_description(inputs, loaded=True)
    return sample



def _sample_filename_stem(display_name: str) -> str:
    """Return a portable filename stem for a user-created sample."""
    normalized = unicodedata.normalize("NFKD", display_name)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_").lower()
    return stem or f"sample_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"


def _refresh_sample_dropdown(
    inputs: adsk.core.CommandInputs,
    select_label: str = "",
) -> None:
    """Rescan both sample roots and refresh the open dialog in-place."""
    global _sample_catalog
    global _sample_discovery_errors

    _sample_catalog, _sample_discovery_errors = (
        _discover_sample_configurations()
    )
    drop_down = adsk.core.DropDownCommandInput.cast(
        _required_command_input(inputs, "sampleConfiguration")
    )
    if drop_down is None:
        raise RuntimeError(
            "sampleConfiguration não é um DropDownCommandInput."
        )

    drop_down.listItems.clear()
    if _sample_catalog:
        labels = list(_sample_catalog)
        selected = select_label if select_label in _sample_catalog else labels[0]
        for label in labels:
            drop_down.listItems.add(label, label == selected)
        drop_down.isEnabled = True
    else:
        drop_down.listItems.add(_t("sample.menu_empty"), True)
        drop_down.isEnabled = False

    load_button = adsk.core.BoolValueCommandInput.cast(
        _required_command_input(inputs, "loadSample")
    )
    if load_button:
        load_button.isEnabled = bool(_sample_catalog)

    drop_down.tooltipDescription = _sample_tooltip_description()
    _update_sample_description(inputs)


def _save_current_as_user_sample(
    inputs: adsk.core.CommandInputs,
) -> tuple[str, str]:
    """Save all current GUI parameters as a persistent user sample."""
    display_name = _string_input_value(inputs, "newSampleName")
    if not display_name:
        raise ValueError(_t("sample.name_required"))

    config = _collect_current_config(inputs)
    parameters = dict(config)
    parameters.pop("Interface_Language", None)

    os.makedirs(USER_SAMPLES_DIRECTORY, exist_ok=True)
    stem = _sample_filename_stem(display_name)
    path = os.path.join(USER_SAMPLES_DIRECTORY, stem + ".json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(
            USER_SAMPLES_DIRECTORY,
            f"{stem}_{suffix}.json",
        )
        suffix += 1

    payload = {
        "Schema_Version": 1,
        "Sample_Name": display_name,
        "Sample_Description": _t("sample.user_description"),
        "Source": "user_gui",
        "Created_At_UTC": _utc_now_text(),
        "Project_Version": PROJECT_VERSION,
        "Parameters": parameters,
    }
    _write_json_atomically(path, payload)

    _refresh_sample_dropdown(inputs)
    # Find the saved entry by the exact absolute user path represented in the
    # catalog. This remains reliable even when display names are duplicated.
    qualified_path = "user:" + os.path.basename(path)
    selected_label = next(
        (
            label
            for label, sample in _sample_catalog.items()
            if sample.relative_path == qualified_path
        ),
        "",
    )
    if selected_label:
        _select_dropdown_item(
            inputs,
            "sampleConfiguration",
            selected_label,
        )
        _update_sample_description(inputs)
    name_input = adsk.core.StringValueCommandInput.cast(
        _required_command_input(inputs, "newSampleName")
    )
    if name_input:
        name_input.value = ""
    return display_name, path


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
    propeller_orientation = _propeller_orientation_from_display(
        _selected_dropdown_name(inputs, "propellerOrientation")
    )

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
        "propeller_orientation": propeller_orientation,
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



LOFT_CONSTRUCTION_CLOSED = "closed_profile"
LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE = "split_trailing_edge"

PROPELLER_ORIENTATION_STANDARD = "standard"
PROPELLER_ORIENTATION_FLIPPED_180 = "flipped_180"


# =============================================================================
# PERSISTED PRESETS AND DIALOG STATE
#
# Generate serializes every validated visible parameter to the per-user JSON
# before geometry construction. Factory defaults remain immutable and are also
# distributed as the built-in original 3 x 1.25-inch configuration.
# Interface_Language is preserved because localization is selected before the
# dialog exists.
# =============================================================================


def _normalize_propeller_orientation(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {
        "flipped_180",
        "flipped",
        "flip_180",
        "boat",
        "boat_propeller",
        "inverted_180",
    }:
        return PROPELLER_ORIENTATION_FLIPPED_180
    return PROPELLER_ORIENTATION_STANDARD


def _propeller_orientation_to_storage(value: str) -> str:
    normalized = _normalize_propeller_orientation(value)
    if normalized == PROPELLER_ORIENTATION_FLIPPED_180:
        return "flipped_180"
    return "standard"


def _propeller_orientation_display(value: str) -> str:
    normalized = _normalize_propeller_orientation(value)
    if normalized == PROPELLER_ORIENTATION_FLIPPED_180:
        return PROPELLER_ORIENTATION_FLIPPED_180_DISPLAY
    return PROPELLER_ORIENTATION_STANDARD_DISPLAY


def _propeller_orientation_from_display(value: object) -> str:
    text_value = str(value or "").strip()
    if text_value == PROPELLER_ORIENTATION_FLIPPED_180_DISPLAY:
        return PROPELLER_ORIENTATION_FLIPPED_180
    if text_value == PROPELLER_ORIENTATION_STANDARD_DISPLAY:
        return PROPELLER_ORIENTATION_STANDARD
    return _normalize_propeller_orientation(text_value)


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


def _normalize_loft_section_order(value: object) -> str:
    normalized = str(value).strip().lower().replace("-", "_")
    if normalized in {"automatic", "auto", "robust"}:
        return LOFT_ORDER_AUTOMATIC
    if normalized in {"tip_to_root", "tip", "reverse"}:
        return LOFT_ORDER_TIP_TO_ROOT
    return LOFT_ORDER_ROOT_TO_TIP


def _loft_section_order_to_storage(value: str) -> str:
    if value == LOFT_ORDER_AUTOMATIC:
        return "automatic"
    if value == LOFT_ORDER_TIP_TO_ROOT:
        return "tip_to_root"
    if value == LOFT_ORDER_ROOT_TO_TIP:
        return "root_to_tip"
    raise ValueError(f"Ordem de loft desconhecida: {value!r}.")


def _normalize_loft_construction_mode(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {
        "split_trailing_edge",
        "split_te",
        "separate_trailing_edge",
        "open_profile_and_te",
    }:
        return LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE
    return LOFT_CONSTRUCTION_CLOSED


def _loft_construction_mode_to_storage(value: str) -> str:
    if value == LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE:
        return "split_trailing_edge"
    if value == LOFT_CONSTRUCTION_CLOSED:
        return "closed_profile"
    raise ValueError(f"Modo de construção do loft desconhecido: {value!r}.")


def _loft_construction_mode_display(value: str) -> str:
    if value == LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE:
        return LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE_DISPLAY
    if value == LOFT_CONSTRUCTION_CLOSED:
        return LOFT_CONSTRUCTION_CLOSED_DISPLAY
    raise ValueError(f"Modo de construção do loft desconhecido: {value!r}.")


def _loft_construction_mode_from_display(value: object) -> str:
    text = str(value or "").strip()
    if text == LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE_DISPLAY:
        return LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE
    if text == LOFT_CONSTRUCTION_CLOSED_DISPLAY:
        return LOFT_CONSTRUCTION_CLOSED
    return _normalize_loft_construction_mode(text)


def _normalize_loft_guides(value: object) -> str:
    normalized = str(value).strip().lower().replace("-", "_")
    if normalized in {
        "distributed",
        "distributed_profile",
        "profile",
        "profile_points",
    }:
        return LOFT_GUIDES_DISTRIBUTED
    if normalized in {
        "dual_trailing_edge",
        "trailing_edge",
        "dual_te",
    }:
        return LOFT_GUIDES_DUAL_TRAILING_EDGE
    return LOFT_GUIDES_NONE


def _loft_guides_to_storage(value: str) -> str:
    if value == LOFT_GUIDES_DISTRIBUTED:
        return "distributed"
    if value == LOFT_GUIDES_DUAL_TRAILING_EDGE:
        return "dual_trailing_edge"
    if value == LOFT_GUIDES_NONE:
        return "none"
    raise ValueError(f"Guias de loft desconhecidas: {value!r}.")


def _normalize_distributed_rail_count(value: object) -> int:
    """Normalize legacy/even values to the supported odd sequence 3, 5, 7..."""
    count = int(value)
    count = max(3, min(803, count))
    if count % 2 == 0:
        count -= 1
    return count


def _normalize_loft_rail_placement(
    value: object,
    legacy_use_te_vertices: object = False,
) -> str:
    """Normalize rail placement with legacy-checkbox compatibility."""
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {
        "uniform",
        "uniform_chord",
        "chord",
        "even_chord",
        "recommended",
    }:
        return LOFT_RAIL_PLACEMENT_UNIFORM_CHORD
    if normalized in {
        "first_points",
        "first_profile_points",
        "after_vertices",
        "internal",
    }:
        return LOFT_RAIL_PLACEMENT_FIRST_POINTS
    if normalized in {
        "vertices",
        "trailing_edge_vertices",
        "te_vertices",
        "exact_vertices",
    }:
        return LOFT_RAIL_PLACEMENT_VERTICES

    legacy_text = str(legacy_use_te_vertices).strip().lower()
    legacy_enabled = (
        legacy_use_te_vertices is True
        or legacy_text in {"1", "true", "yes", "on"}
    )
    return (
        LOFT_RAIL_PLACEMENT_VERTICES
        if legacy_enabled
        else LOFT_RAIL_PLACEMENT_FIRST_POINTS
    )


def _loft_rail_placement_to_storage(value: str) -> str:
    if value == LOFT_RAIL_PLACEMENT_UNIFORM_CHORD:
        return "uniform_chord"
    if value == LOFT_RAIL_PLACEMENT_FIRST_POINTS:
        return "first_points"
    if value == LOFT_RAIL_PLACEMENT_VERTICES:
        return "trailing_edge_vertices"
    raise ValueError(
        f"Posicionamento de rails desconhecido: {value!r}."
    )


def _normalize_finalization_method(value: object) -> str:
    normalized = str(value).strip().lower().replace("-", "_")
    if normalized in {
        "legacy",
        "extend_trim_stitch",
        "trim_stitch",
    }:
        return FINALIZATION_LEGACY
    return FINALIZATION_BOUNDARY_FILL


def _finalization_method_to_storage(value: str) -> str:
    if value == FINALIZATION_BOUNDARY_FILL:
        return "boundary_fill"
    if value == FINALIZATION_LEGACY:
        return "legacy"
    raise ValueError(f"Método de finalização desconhecido: {value!r}.")


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

    config = _current_dialog_config_base()
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
            "Loft_Construction_Mode": _loft_construction_mode_to_storage(
                _loft_construction_mode_from_display(
                    _selected_dropdown_name(inputs, "loftConstructionMode")
                )
            ),
            "Loft_Section_Order": _loft_section_order_to_storage(
                _selected_dropdown_name(inputs, "loftSectionOrder")
            ),
            "Loft_Guide_Rails": _loft_guides_to_storage(
                _selected_dropdown_name(inputs, "loftGuideRails")
            ),
            "Loft_Distributed_Rail_Count": (
                _normalize_distributed_rail_count(
                    _required_command_input(
                        inputs,
                        "loftDistributedRailCount",
                    ).value
                )
            ),
            "Loft_Distributed_Rail_Placement": (
                _loft_rail_placement_to_storage(
                    _selected_dropdown_name(
                        inputs,
                        "loftRailPlacement",
                    )
                )
            ),
            # Retain the former boolean for downgrade compatibility.
            "Loft_Distributed_Rails_Use_TE_Vertices": (
                _selected_dropdown_name(
                    inputs,
                    "loftRailPlacement",
                )
                == LOFT_RAIL_PLACEMENT_VERTICES
            ),
            "Loft_Merge_Tangent_Edges": bool(
                _required_command_input(
                    inputs,
                    "loftMergeTangentEdges",
                ).value
            ),
            "Loft_Quality_Check": bool(
                _required_command_input(
                    inputs,
                    "loftQualityCheck",
                ).value
            ),
            "Loft_Quality_Max_Deviation_Percent": _parse_float_text(
                _string_input_value(
                    inputs,
                    "loftQualityMaxDeviationPercent",
                ),
                "Loft_Quality_Max_Deviation_Percent",
            ),
            "Loft_Quality_Max_Wave_Angle_Deg": _parse_float_text(
                _string_input_value(
                    inputs,
                    "loftQualityMaxWaveAngleDeg",
                ),
                "Loft_Quality_Max_Wave_Angle_Deg",
            ),
            "Loft_Quality_Post_Fairing_Margin_Multiplier": _parse_float_text(
                _string_input_value(
                    inputs,
                    "loftQualityPostFairingMarginMultiplier",
                ),
                "Loft_Quality_Post_Fairing_Margin_Multiplier",
            ),
            "Blade_Finalization_Method": _finalization_method_to_storage(
                _selected_dropdown_name(inputs, "finalizationMethod")
            ),
            "Boundary_Fill_Diameter_Overlap_mm": _value_input_mm(
                inputs,
                "boundaryOverlapDiameter",
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
            "Propeller_Orientation": _propeller_orientation_to_storage(
                assembly["propeller_orientation"]
            ),
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


def _write_json_atomically(path: str, payload: dict) -> None:
    """Durably replace one JSON file without leaving a partial target."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temporary_path = f"{path}.tmp.{uuid.uuid4().hex}"

    try:
        with open(temporary_path, "x", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except Exception:
            pass
        raise


def _write_user_config_atomically(config: dict) -> None:
    """Persist the complete last-run configuration outside the add-in."""
    _write_json_atomically(USER_CONFIG_PATH, config)


def _save_current_config(
    inputs: adsk.core.CommandInputs,
) -> dict:
    """Persist and return the complete configuration represented by the GUI."""
    config = _collect_current_config(inputs)
    _write_user_config_atomically(config)
    _set_dialog_config_base(config)
    return config


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



def _update_loft_inputs(
    inputs: adsk.core.CommandInputs,
) -> None:
    """Enable loft, robust-search, quality, and distributed-rail controls."""
    create_loft = bool(
        _required_command_input(inputs, "createSurfaceLoft").value
    )
    _required_command_input(
        inputs,
        "loftSectionOrder",
    ).isEnabled = create_loft

    order = _selected_dropdown_name(inputs, "loftSectionOrder")
    guide_mode = _selected_dropdown_name(inputs, "loftGuideRails")
    automatic = create_loft and order == LOFT_ORDER_AUTOMATIC
    _required_command_input(
        inputs,
        "loftConstructionMode",
    ).isEnabled = create_loft and not automatic
    _required_command_input(
        inputs,
        "loftGuideRails",
    ).isEnabled = create_loft and not automatic
    _required_command_input(
        inputs,
        "loftMergeTangentEdges",
    ).isEnabled = create_loft

    distributed_enabled = create_loft and (
        automatic or guide_mode == LOFT_GUIDES_DISTRIBUTED
    )
    for input_id in (
        "loftDistributedRailCount",
        "loftRailPlacement",
    ):
        _required_command_input(
            inputs,
            input_id,
        ).isEnabled = distributed_enabled

    quality_check_input = _required_command_input(
        inputs,
        "loftQualityCheck",
    )
    quality_check_input.isEnabled = automatic
    quality_enabled = automatic and bool(quality_check_input.value)
    for input_id in (
        "loftQualityMaxDeviationPercent",
        "loftQualityMaxWaveAngleDeg",
        "loftQualityPostFairingMarginMultiplier",
    ):
        _required_command_input(
            inputs,
            input_id,
        ).isEnabled = quality_enabled



def _update_finalization_inputs(
    inputs: adsk.core.CommandInputs,
) -> None:
    """Enable controls that apply to the selected solid-finalization method."""
    create_loft = bool(
        _required_command_input(inputs, "createSurfaceLoft").value
    )
    finalize = bool(
        _required_command_input(inputs, "finalizeSolid").value
    )
    method = _selected_dropdown_name(inputs, "finalizationMethod")
    boundary_fill = method == FINALIZATION_BOUNDARY_FILL

    _required_command_input(
        inputs, "finalizationMethod"
    ).isEnabled = create_loft
    _required_command_input(
        inputs, "boundaryOverlapDiameter"
    ).isEnabled = create_loft and finalize and boundary_fill

    extend_input = _required_command_input(inputs, "extendSurfaceEnds")
    extend_input.isEnabled = create_loft and not boundary_fill
    _required_command_input(
        inputs, "extensionDistance"
    ).isEnabled = (
        create_loft
        and not boundary_fill
        and bool(extend_input.value)
    )

    cylinder_input = _required_command_input(inputs, "createLimitCylinders")
    if create_loft and finalize and boundary_fill:
        # Boundary Fill requires both nominal cylinders. Keep the saved value
        # for legacy mode, but make the active requirement explicit.
        cylinder_input.value = True
        cylinder_input.isEnabled = False
    else:
        cylinder_input.isEnabled = create_loft

    _required_command_input(
        inputs, "cylinderAxialMargin"
    ).isEnabled = create_loft and bool(cylinder_input.value)
    construction_mode = _loft_construction_mode_from_display(
        _selected_dropdown_name(inputs, "loftConstructionMode")
    )
    split_construction = (
        create_loft
        and construction_mode == LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE
    )
    _required_command_input(
        inputs, "stitchTolerance"
    ).isEnabled = (
        split_construction
        or (create_loft and finalize and not boundary_fill)
    )


MODE_FLAT = _t("mode.flat")
MODE_WRAPPED = _t("mode.wrapped")

LOFT_ORDER_ROOT_TO_TIP = _t("loft_order.root_to_tip")
LOFT_ORDER_TIP_TO_ROOT = _t("loft_order.tip_to_root")
LOFT_ORDER_AUTOMATIC = _t("loft_order.automatic")

LOFT_CONSTRUCTION_CLOSED_DISPLAY = _t(
    "loft_construction.closed_profile"
)
LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE_DISPLAY = _t(
    "loft_construction.split_trailing_edge"
)

LOFT_GUIDES_NONE = _t("loft_guides.none")
LOFT_GUIDES_DISTRIBUTED = _t("loft_guides.distributed")
LOFT_GUIDES_DUAL_TRAILING_EDGE = _t(
    "loft_guides.dual_trailing_edge"
)

LOFT_RAIL_PLACEMENT_UNIFORM_CHORD = _t(
    "loft_rail_placement.uniform_chord"
)
LOFT_RAIL_PLACEMENT_FIRST_POINTS = _t(
    "loft_rail_placement.first_points"
)
LOFT_RAIL_PLACEMENT_VERTICES = _t(
    "loft_rail_placement.vertices"
)

FINALIZATION_BOUNDARY_FILL = _t("finalization.boundary_fill")
FINALIZATION_LEGACY = _t("finalization.legacy")

PROPELLER_ORIENTATION_STANDARD_DISPLAY = _t(
    "propeller_orientation.standard"
)
PROPELLER_ORIENTATION_FLIPPED_180_DISPLAY = _t(
    "propeller_orientation.flipped_180"
)


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
    _select_dropdown_item(
        inputs,
        "propellerOrientation",
        _propeller_orientation_display(
            config.get("Propeller_Orientation", "standard")
        ),
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
    _select_dropdown_item(
        inputs,
        "loftConstructionMode",
        _loft_construction_mode_display(
            _normalize_loft_construction_mode(
                config.get(
                    "Loft_Construction_Mode",
                    "split_trailing_edge",
                )
            )
        ),
    )
    _select_dropdown_item(
        inputs,
        "loftSectionOrder",
        _normalize_loft_section_order(
            config.get("Loft_Section_Order", "root_to_tip")
        ),
    )
    _select_dropdown_item(
        inputs,
        "loftGuideRails",
        _normalize_loft_guides(
            config.get("Loft_Guide_Rails", "none")
        ),
    )
    _set_integer_input(
        inputs,
        "loftDistributedRailCount",
        _normalize_distributed_rail_count(
            config.get("Loft_Distributed_Rail_Count", 9)
        ),
    )
    _select_dropdown_item(
        inputs,
        "loftRailPlacement",
        _normalize_loft_rail_placement(
            config.get("Loft_Distributed_Rail_Placement"),
            config.get(
                "Loft_Distributed_Rails_Use_TE_Vertices",
                False,
            ),
        ),
    )
    _set_bool_input(
        inputs,
        "loftMergeTangentEdges",
        config.get("Loft_Merge_Tangent_Edges", True),
    )
    _set_bool_input(
        inputs,
        "loftQualityCheck",
        config.get("Loft_Quality_Check", True),
    )
    _set_string_input(
        inputs,
        "loftQualityMaxDeviationPercent",
        f"{float(config.get('Loft_Quality_Max_Deviation_Percent', 0.1)):g}",
    )
    _set_string_input(
        inputs,
        "loftQualityMaxWaveAngleDeg",
        f"{float(config.get('Loft_Quality_Max_Wave_Angle_Deg', 0.2)):g}",
    )
    _set_string_input(
        inputs,
        "loftQualityPostFairingMarginMultiplier",
        f"{float(config.get('Loft_Quality_Post_Fairing_Margin_Multiplier', 2.0)):g}",
    )
    _select_dropdown_item(
        inputs,
        "finalizationMethod",
        _normalize_finalization_method(
            config.get("Blade_Finalization_Method", "boundary_fill")
        ),
    )
    _set_value_input_mm(
        inputs,
        "boundaryOverlapDiameter",
        config.get("Boundary_Fill_Diameter_Overlap_mm", 0.1),
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
        config.get("Stitch_Tolerance_mm", 0.1),
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
    _update_loft_inputs(inputs)
    _update_finalization_inputs(inputs)

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
    surface_loft_strategy: str = ""
    surface_loft_error: str = ""
    surface_loft_failed_stage: str = ""
    main_surface_loft_error: str = ""
    trailing_edge_loft_error: str = ""
    surface_trim_error: str = ""
    surface_stitch_error: str = ""

    robust_search_requested: bool = False
    robust_search_succeeded: bool = False
    robust_search_cancelled: bool = False
    robust_search_used_fallback: bool = False
    robust_search_fairing_tolerated: bool = False
    robust_attempt_count: int = 0
    robust_attempt_log: str = ""
    robust_log_json_path: str = ""
    robust_log_text_path: str = ""
    robust_log_write_error: str = ""

    loft_quality_checked: bool = False
    loft_quality_accepted: bool = False
    loft_quality_sample_count: int = 0
    loft_quality_rms_error_mm: float = 0.0
    loft_quality_max_error_mm: float = 0.0
    loft_quality_rms_percent_chord: float = 0.0
    loft_quality_max_percent_chord: float = 0.0
    loft_quality_limit_percent_chord: float = 0.0
    loft_quality_rms_wave_angle_deg: float = 0.0
    loft_quality_max_wave_angle_deg: float = 0.0
    loft_quality_limit_wave_angle_deg: float = 0.0
    loft_quality_worst_radius_mm: float = 0.0
    loft_quality_worst_contour_index: int = -1
    loft_quality_worst_wave_radius_mm: float = 0.0
    loft_quality_worst_wave_contour_index: int = -1
    loft_quality_fairing_end_radius_mm: float = 0.0
    loft_quality_post_fairing_margin_multiplier: float = 0.0
    loft_quality_post_fairing_margin_mm: float = 0.0
    loft_quality_root_tolerance_end_radius_mm: float = 0.0
    loft_quality_post_fairing_sample_count: int = 0
    loft_quality_post_fairing_max_percent_chord: float = 0.0
    loft_quality_post_fairing_max_wave_angle_deg: float = 0.0
    loft_quality_aerodynamic_sample_count: int = 0
    loft_quality_aerodynamic_max_percent_chord: float = 0.0
    loft_quality_aerodynamic_max_wave_angle_deg: float = 0.0
    loft_quality_fairing_sample_count: int = 0
    loft_quality_fairing_max_percent_chord: float = 0.0
    loft_quality_fairing_max_wave_angle_deg: float = 0.0

    root_wrap_min_deg: float = 0.0
    root_wrap_max_deg: float = 0.0
    boundary_overlap_diameter_mm: float = 0.0

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
    finalization_method: str = ""
    boundary_fill_created: bool = False
    boundary_fill_cell_count: int = 0
    boundary_fill_selected_volume_cm3: float = 0.0
    boundary_fill_second_volume_cm3: float = 0.0
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
    final_orientation_requested: bool = False
    final_orientation_applied: bool = False
    final_orientation_mode: str = "standard"
    final_orientation_angle_deg: float = 0.0
    final_orientation_body_count: int = 0
    final_orientation_error: str = ""

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
    closing_points_xyz_mm: tuple[tuple[float, float, float], ...],
    radius_mm: float,
) -> tuple[
    adsk.fusion.SketchFittedSpline,
    adsk.fusion.SketchFittedSpline,
]:
    """Create the wrapped NACA contour and wrapped TE closing curve."""
    profile_points = adsk.core.ObjectCollection.create()
    for x_mm, y_mm, z_mm in points_xyz_mm:
        profile_points.add(
            adsk.core.Point3D.create(
                x_mm / 10.0,
                y_mm / 10.0,
                z_mm / 10.0,
            )
        )

    spline = sketch.sketchCurves.sketchFittedSplines.add(
        profile_points
    )
    if not spline:
        raise RuntimeError(
            f"Falha ao criar a spline 3D da seção R={radius_mm:g} mm."
        )

    closing_points = adsk.core.ObjectCollection.create()
    for x_mm, y_mm, z_mm in closing_points_xyz_mm:
        closing_points.add(
            adsk.core.Point3D.create(
                x_mm / 10.0,
                y_mm / 10.0,
                z_mm / 10.0,
            )
        )

    closing_spline = sketch.sketchCurves.sketchFittedSplines.add(
        closing_points
    )
    if not closing_spline:
        raise RuntimeError(
            "Falha ao criar a spline 3D enrolada de fechamento do "
            f"bordo de fuga em R={radius_mm:g} mm."
        )

    return spline, closing_spline


def _create_closed_section_path(
    component: adsk.fusion.Component,
    spline: adsk.fusion.SketchFittedSpline,
    closing_curve: adsk.fusion.SketchFittedSpline,
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
    curves.add(closing_curve)

    path = component.features.createPath(
        curves,
        False,
    )
    if path is None or not path.isValid:
        raise RuntimeError(
            f"Não foi possível criar o Path fechado em R={radius_mm:g} mm."
        )
    return path


def _create_single_curve_section_path(
    component: adsk.fusion.Component,
    curve: adsk.fusion.SketchCurve,
    radius_mm: float,
    role: str,
) -> adsk.fusion.Path:
    """Create a fresh open Path from one reusable section curve."""
    if component is None or not component.isValid:
        raise RuntimeError(
            "O componente da seção não é mais válido."
        )
    if curve is None or not curve.isValid:
        raise RuntimeError(
            f"A curva {role} da seção R={radius_mm:g} mm não é válida."
        )

    curves = adsk.core.ObjectCollection.create()
    curves.add(curve)
    path = component.features.createPath(curves, False)
    if path is None or not path.isValid:
        raise RuntimeError(
            f"Não foi possível criar o Path {role} em R={radius_mm:g} mm."
        )
    return path


# =============================================================================
# SURFACE LOFT, EXACT RADIAL TRIMMING AND STITCHING
#
# The original SCAD directly creates a closed polygon mesh. Fusion lofts the
# section paths as an open surface; root and tip are extended slightly, trimmed
# against analytical cylindrical surfaces, capped and stitched into a solid.
# =============================================================================


def _create_dual_trailing_edge_rails(
    component: adsk.fusion.Component,
    trailing_edge_points: list[
        tuple[
            float,
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ],
    hide_created_sketches: bool,
) -> tuple[
    adsk.fusion.Sketch,
    tuple[adsk.fusion.SketchFittedSpline, ...],
]:
    """Create the experimental upper/lower trailing-edge guide rails."""
    if len(trailing_edge_points) < 2:
        raise ValueError(
            "São necessárias pelo menos duas seções para criar as guias."
        )

    ordered = sorted(trailing_edge_points, key=lambda item: item[0])
    rail_sketch = component.sketches.add(component.xYConstructionPlane)
    if rail_sketch is None or not rail_sketch.isValid:
        raise RuntimeError(
            "Não foi possível criar o esboço das guias do loft."
        )
    rail_sketch.name = _t("feature.loft_guide_rails")

    collections = (
        adsk.core.ObjectCollection.create(),
        adsk.core.ObjectCollection.create(),
    )
    for _, upper_mm, lower_mm in ordered:
        for collection, point_mm in zip(
            collections,
            (upper_mm, lower_mm),
        ):
            collection.add(
                adsk.core.Point3D.create(
                    point_mm[0] / 10.0,
                    point_mm[1] / 10.0,
                    point_mm[2] / 10.0,
                )
            )

    rails: list[adsk.fusion.SketchFittedSpline] = []
    rail_sketch.isComputeDeferred = True
    try:
        for points in collections:
            rail = rail_sketch.sketchCurves.sketchFittedSplines.add(
                points
            )
            if rail is None or not rail.isValid:
                raise RuntimeError(
                    "Não foi possível criar uma das guias do bordo de fuga."
                )
            rails.append(rail)
    finally:
        rail_sketch.isComputeDeferred = False

    rail_sketch.isLightBulbOn = not hide_created_sketches
    return rail_sketch, tuple(rails)


def _evenly_selected_indices(
    candidates: list[int],
    count: int,
) -> list[int]:
    """Select exactly ``count`` well-spaced entries from ordered candidates."""
    if count < 0 or count > len(candidates):
        raise ValueError("Quantidade inválida de índices distribuídos.")
    if count == 0:
        return []
    if count == len(candidates):
        return list(candidates)

    length = len(candidates)
    selected_positions = [
        math.floor(
            (index + 1) * (length + 1) / (count + 1)
        ) - 1
        for index in range(count)
    ]
    selected = [candidates[position] for position in selected_positions]
    if len(set(selected)) != count:
        raise RuntimeError(
            "Falha interna ao distribuir os índices das guias."
        )
    return selected


def _uniform_chord_sample_indices(
    profile_points_per_surface: int,
    count_per_surface: int,
) -> tuple[int, ...]:
    """Choose unique NACA sample indices nearest uniform x/c targets."""
    n = int(profile_points_per_surface)
    m = int(count_per_surface)
    if m < 0 or m > n - 1:
        raise ValueError(
            "Quantidade inválida de posições uniformes na corda."
        )
    if m == 0:
        return ()

    candidates = list(range(1, n))
    target_x = [
        (index + 1) / (m + 1)
        for index in range(m)
    ]
    candidate_x = [
        0.5 * (1.0 - math.cos(math.pi * sample_index / n))
        for sample_index in candidates
    ]

    candidate_count = len(candidates)
    infinity = math.inf
    costs = [
        [infinity] * (candidate_count + 1)
        for _ in range(m + 1)
    ]
    take = [
        [False] * (candidate_count + 1)
        for _ in range(m + 1)
    ]
    for column in range(candidate_count + 1):
        costs[0][column] = 0.0

    for target_index in range(1, m + 1):
        for column in range(1, candidate_count + 1):
            skip_cost = costs[target_index][column - 1]
            select_cost = infinity
            if costs[target_index - 1][column - 1] < infinity:
                delta = (
                    candidate_x[column - 1]
                    - target_x[target_index - 1]
                )
                select_cost = (
                    costs[target_index - 1][column - 1]
                    + delta * delta
                )
            if select_cost < skip_cost:
                costs[target_index][column] = select_cost
                take[target_index][column] = True
            else:
                costs[target_index][column] = skip_cost

    if not math.isfinite(costs[m][candidate_count]):
        raise RuntimeError(
            "Não foi possível distribuir as rails uniformemente na corda."
        )

    selected: list[int] = []
    target_index = m
    column = candidate_count
    while target_index > 0:
        if column <= 0:
            raise RuntimeError(
                "Falha ao reconstruir a distribuição uniforme de rails."
            )
        if take[target_index][column]:
            selected.append(candidates[column - 1])
            target_index -= 1
            column -= 1
        else:
            column -= 1

    selected.reverse()
    return tuple(selected)


def _maximum_distributed_rail_count(
    profile_points_per_surface: int,
    rail_placement: str,
) -> int:
    n = int(profile_points_per_surface)
    if n < 2:
        return 0
    placement = _normalize_loft_rail_placement(rail_placement)
    if placement == LOFT_RAIL_PLACEMENT_VERTICES:
        return 2 * n + 1
    return 2 * n - 1


def _distributed_rail_indices(
    profile_points_per_surface: int,
    requested_count: int,
    rail_placement: str,
) -> tuple[int, ...]:
    """Return an odd, symmetric set of matching NACA contour indices."""
    n = int(profile_points_per_surface)
    count = int(requested_count)
    placement = _normalize_loft_rail_placement(rail_placement)

    if n < 2:
        raise ValueError(
            "São necessários pelo menos dois pontos por superfície."
        )
    if count < 3 or count % 2 == 0:
        raise ValueError(
            "A quantidade de guias distribuídas deve ser ímpar e >= 3."
        )

    maximum = _maximum_distributed_rail_count(n, placement)
    if count > maximum:
        raise ValueError(
            f"Foram solicitadas {count} guias, mas o perfil atual permite "
            f"no máximo {maximum} no posicionamento selecionado."
        )

    if placement == LOFT_RAIL_PLACEMENT_UNIFORM_CHORD:
        per_surface = (count - 1) // 2
        sample_indices = _uniform_chord_sample_indices(
            n,
            per_surface,
        )
        upper_indices = [n - sample for sample in sample_indices]
        lower_indices = [n + sample for sample in sample_indices]
        result = tuple(sorted([*upper_indices, n, *lower_indices]))
    else:
        use_vertices = placement == LOFT_RAIL_PLACEMENT_VERTICES
        upper_anchor = 0 if use_vertices else 1
        lower_anchor = 2 * n if use_vertices else 2 * n - 1
        upper_candidates = list(range(upper_anchor + 1, n))
        lower_candidates = list(range(n + 1, lower_anchor))
        per_surface_extra = (count - 3) // 2
        upper_indices = _evenly_selected_indices(
            upper_candidates,
            per_surface_extra,
        )
        lower_indices = _evenly_selected_indices(
            lower_candidates,
            per_surface_extra,
        )
        result = tuple(
            sorted(
                [
                    upper_anchor,
                    *upper_indices,
                    n,
                    *lower_indices,
                    lower_anchor,
                ]
            )
        )

    if len(result) != count or len(set(result)) != count:
        raise RuntimeError(
            "Falha interna ao distribuir simetricamente as guias."
        )
    return result



def _create_distributed_profile_rails(
    component: adsk.fusion.Component,
    section_profile_points: list[
        tuple[
            float,
            tuple[tuple[float, float, float], ...],
        ]
    ],
    requested_count: int,
    rail_placement: str,
    hide_created_sketches: bool,
) -> tuple[
    adsk.fusion.Sketch,
    tuple[adsk.fusion.SketchFittedSpline, ...],
]:
    """Create rails through matching fitted points of every NACA contour."""
    if len(section_profile_points) < 2:
        raise ValueError(
            "São necessárias pelo menos duas seções para criar as guias."
        )

    ordered = sorted(section_profile_points, key=lambda item: item[0])
    point_count = len(ordered[0][1])
    if point_count < 5 or point_count % 2 == 0:
        raise RuntimeError(
            "A quantidade de pontos do perfil não corresponde a 2N+1."
        )
    for radius_mm, points_xyz in ordered:
        if len(points_xyz) != point_count:
            raise RuntimeError(
                "As seções não possuem a mesma quantidade de pontos; "
                f"a divergência foi encontrada em R={radius_mm:g} mm."
            )

    profile_points_per_surface = (point_count - 1) // 2
    rail_indices = _distributed_rail_indices(
        profile_points_per_surface,
        requested_count,
        rail_placement,
    )
    if not rail_indices:
        raise ValueError(
            "A quantidade de guias distribuídas deve ser pelo menos 1."
        )

    rail_sketch = component.sketches.add(component.xYConstructionPlane)
    if rail_sketch is None or not rail_sketch.isValid:
        raise RuntimeError(
            "Não foi possível criar o esboço das guias distribuídas."
        )
    rail_sketch.name = _t(
        "feature.loft_distributed_rails",
        count=len(rail_indices),
    )

    rails: list[adsk.fusion.SketchFittedSpline] = []
    rail_sketch.isComputeDeferred = True
    try:
        for point_index in rail_indices:
            fit_points = adsk.core.ObjectCollection.create()
            for _, points_xyz in ordered:
                point_mm = points_xyz[point_index]
                fit_points.add(
                    adsk.core.Point3D.create(
                        point_mm[0] / 10.0,
                        point_mm[1] / 10.0,
                        point_mm[2] / 10.0,
                    )
                )

            rail = rail_sketch.sketchCurves.sketchFittedSplines.add(
                fit_points
            )
            if rail is None or not rail.isValid:
                raise RuntimeError(
                    "Não foi possível criar a guia distribuída associada "
                    f"ao índice {point_index}."
                )
            rails.append(rail)
    finally:
        rail_sketch.isComputeDeferred = False

    rail_sketch.isLightBulbOn = not hide_created_sketches
    return rail_sketch, tuple(rails)


def _automatic_distributed_counts(
    requested_count: int,
) -> tuple[int, ...]:
    """Return every supported odd rail count up to the requested value."""
    requested = _normalize_distributed_rail_count(requested_count)
    return tuple(range(3, requested + 1, 2))


def _loft_attempt_sequence(
    requested_order: str,
    requested_guides: str,
    distributed_rail_count: int,
    merge_tangent_edges: bool,
) -> list[tuple[str, str, int, bool]]:
    """Build deterministic loft attempts without using TE rails automatically."""
    effective_guides = requested_guides
    effective_count = _normalize_distributed_rail_count(
        distributed_rail_count
    )

    if requested_order in (
        LOFT_ORDER_ROOT_TO_TIP,
        LOFT_ORDER_TIP_TO_ROOT,
    ):
        return [
            (
                requested_order,
                effective_guides,
                effective_count,
                merge_tangent_edges,
            )
        ]

    guide_variants: list[tuple[str, int]] = [
        (LOFT_GUIDES_NONE, 0)
    ]
    if effective_guides == LOFT_GUIDES_DISTRIBUTED:
        guide_variants.extend(
            (
                LOFT_GUIDES_DISTRIBUTED,
                count,
            )
            for count in _automatic_distributed_counts(
                effective_count
            )
        )
    elif effective_guides == LOFT_GUIDES_DUAL_TRAILING_EDGE:
        # Retained for explicit experimental use, but never substituted for
        # distributed rails because the user observed severe waviness.
        guide_variants.append(
            (LOFT_GUIDES_DUAL_TRAILING_EDGE, 0)
        )

    candidates: list[tuple[str, str, int, bool]] = []
    merge_variants = (
        merge_tangent_edges,
        not merge_tangent_edges,
    )
    for merge_edges in merge_variants:
        for order in (
            LOFT_ORDER_ROOT_TO_TIP,
            LOFT_ORDER_TIP_TO_ROOT,
        ):
            for guides, rail_count in guide_variants:
                candidate = (
                    order,
                    guides,
                    rail_count,
                    merge_edges,
                )
                if candidate not in candidates:
                    candidates.append(candidate)
    return candidates


def _loft_strategy_text(
    order: str,
    guides: str,
    distributed_rail_count: int,
    rail_placement: str,
    merge_tangent_edges: bool,
) -> str:
    guide_text = guides
    if guides == LOFT_GUIDES_DISTRIBUTED:
        guide_text = _t(
            "loft_guides.distributed_count",
            count=distributed_rail_count,
            placement=rail_placement,
        )

    return _t(
        "loft.strategy",
        order=order,
        guides=guide_text,
        tangent=(
            _t("loft_tangent.merge")
            if merge_tangent_edges
            else _t("loft_tangent.keep")
        ),
    )


def _create_surface_loft(
    component: adsk.fusion.Component,
    section_paths: list[tuple[float, adsk.fusion.Path]],
    trailing_edge_points: list[
        tuple[
            float,
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ],
    section_profile_points: list[
        tuple[
            float,
            tuple[tuple[float, float, float], ...],
        ]
    ],
    requested_order: str,
    requested_guides: str,
    distributed_rail_count: int,
    rail_placement: str,
    merge_tangent_edges: bool,
    hide_created_sketches: bool,
) -> tuple[adsk.fusion.LoftFeature, str]:
    """Create a surface loft using manual or progressively robust strategies."""
    if len(section_paths) < 2:
        raise ValueError(
            "São necessárias pelo menos duas seções para criar o loft."
        )

    loft_features = component.features.loftFeatures
    attempts = _loft_attempt_sequence(
        requested_order,
        requested_guides,
        distributed_rail_count,
        merge_tangent_edges,
    )

    rail_bundles: dict[
        tuple[str, int],
        tuple[
            adsk.fusion.Sketch,
            tuple[adsk.fusion.SketchFittedSpline, ...],
        ],
    ] = {}
    attempt_errors: list[str] = []

    def get_rail_bundle(
        guides: str,
        rail_count: int,
    ) -> tuple[
        adsk.fusion.Sketch,
        tuple[adsk.fusion.SketchFittedSpline, ...],
    ]:
        key = (guides, rail_count)
        existing = rail_bundles.get(key)
        if existing is not None:
            return existing

        if guides == LOFT_GUIDES_DISTRIBUTED:
            bundle = _create_distributed_profile_rails(
                component,
                section_profile_points,
                rail_count,
                rail_placement,
                hide_created_sketches,
            )
        elif guides == LOFT_GUIDES_DUAL_TRAILING_EDGE:
            bundle = _create_dual_trailing_edge_rails(
                component,
                trailing_edge_points,
                hide_created_sketches,
            )
        else:
            raise ValueError(
                f"Modo de guia inesperado: {guides!r}."
            )

        rail_bundles[key] = bundle
        return bundle

    for attempt_number, (
        order,
        guides,
        rail_count,
        merge_edges,
    ) in enumerate(attempts, start=1):
        strategy = _loft_strategy_text(
            order,
            guides,
            rail_count,
            rail_placement,
            merge_edges,
        )

        try:
            loft_input = loft_features.createInput(
                adsk.fusion.FeatureOperations.NewBodyFeatureOperation
            )
            if loft_input is None or not loft_input.isValid:
                raise RuntimeError(
                    "Não foi possível criar a entrada do loft."
                )

            loft_input.isSolid = False
            loft_input.isClosed = False
            loft_input.isTangentEdgesMerged = merge_edges
            loft_input.startLoftEdgeAlignment = (
                adsk.fusion.LoftEdgeAlignments.FreeEdgesLoftEdgeAlignment
            )
            loft_input.endLoftEdgeAlignment = (
                adsk.fusion.LoftEdgeAlignments.FreeEdgesLoftEdgeAlignment
            )

            reverse = order == LOFT_ORDER_TIP_TO_ROOT
            ordered_sections = sorted(
                section_paths,
                key=lambda item: item[0],
                reverse=reverse,
            )
            for radius_mm, path in ordered_sections:
                loft_section = loft_input.loftSections.add(path)
                if loft_section is None or not loft_section.isValid:
                    raise RuntimeError(
                        "Não foi possível adicionar ao loft a seção "
                        f"R={radius_mm:g} mm."
                    )

            used_rail_key = None
            if guides != LOFT_GUIDES_NONE:
                used_rail_key = (guides, rail_count)
                _, rails = get_rail_bundle(
                    guides,
                    rail_count,
                )
                for rail_number, rail in enumerate(rails, start=1):
                    definition = (
                        loft_input.centerLineOrRails.addRail(rail)
                    )
                    if definition is None or not definition.isValid:
                        raise RuntimeError(
                            "O Fusion recusou a guia "
                            f"{rail_number} de {len(rails)}."
                        )

            loft_feature = loft_features.add(loft_input)
            if loft_feature is None or not loft_feature.isValid:
                raise RuntimeError(
                    "O Fusion não conseguiu criar o loft de superfície."
                )

            # Remove rail sketches created by failed attempts. Preserve only
            # the bundle that actually constrains the successful loft.
            for key, (rail_sketch, _) in list(rail_bundles.items()):
                if key == used_rail_key:
                    continue
                if rail_sketch is not None and rail_sketch.isValid:
                    rail_sketch.deleteMe()
                del rail_bundles[key]

            loft_feature.name = _t(
                "feature.loft",
                count=len(section_paths),
                root=min(r for r, _ in section_paths),
                tip=max(r for r, _ in section_paths),
            )
            return loft_feature, strategy

        except Exception as error:
            attempt_errors.append(
                _t(
                    "loft.attempt_error",
                    number=attempt_number,
                    strategy=strategy,
                    detail=f"{type(error).__name__}: {error}",
                )
            )

    # On complete failure, keep any generated rail sketches for diagnosis.
    raise RuntimeError("\n\n".join(attempt_errors))


@dataclass(frozen=True)
class _LoftQualityRegionMetrics:
    accepted: bool
    sample_count: int
    rms_error_mm: float
    max_error_mm: float
    rms_percent_chord: float
    max_percent_chord: float
    rms_wave_angle_deg: float
    max_wave_angle_deg: float
    worst_radius_mm: float
    worst_contour_index: int
    worst_wave_radius_mm: float
    worst_wave_contour_index: int


@dataclass(frozen=True)
class _LoftQualityMetrics:
    accepted: bool
    sample_count: int
    rms_error_mm: float
    max_error_mm: float
    rms_percent_chord: float
    max_percent_chord: float
    limit_percent_chord: float
    rms_wave_angle_deg: float
    max_wave_angle_deg: float
    limit_wave_angle_deg: float
    worst_radius_mm: float
    worst_contour_index: int
    worst_wave_radius_mm: float
    worst_wave_contour_index: int
    fairing_end_radius_mm: float
    post_fairing_margin_multiplier: float
    post_fairing_margin_mm: float
    root_tolerance_end_radius_mm: float
    fairing: _LoftQualityRegionMetrics | None
    post_fairing: _LoftQualityRegionMetrics | None
    aerodynamic: _LoftQualityRegionMetrics | None

    @property
    def accepted_tolerating_fairing(self) -> bool:
        """Accept when misses are confined to the tolerated root transition."""
        root_samples = sum(
            region.sample_count
            for region in (self.fairing, self.post_fairing)
            if region is not None
        )
        return bool(
            not self.accepted
            and root_samples > 0
            and self.aerodynamic is not None
            and self.aerodynamic.sample_count > 0
            and self.aerodynamic.accepted
        )


@dataclass(frozen=True)
class _RobustCandidateOutcome:
    loft_created: bool
    trailing_edge_loft_created: bool
    surface_stitch_created: bool
    quality_checked: bool
    quality: _LoftQualityMetrics | None
    boundary_fill_created: bool
    cell_volumes_cm3: tuple[float, ...]
    failed_stage: str
    error_detail: str

    @property
    def finalizable(self) -> bool:
        return bool(self.boundary_fill_created)

    @property
    def strict_accepted(self) -> bool:
        if not self.finalizable:
            return False
        if not self.quality_checked:
            return True
        return bool(self.quality is not None and self.quality.accepted)

    @property
    def fairing_tolerated_accepted(self) -> bool:
        return bool(
            self.finalizable
            and self.quality_checked
            and self.quality is not None
            and self.quality.accepted_tolerating_fairing
        )

    @property
    def automatic_accepted(self) -> bool:
        return bool(
            self.strict_accepted or self.fairing_tolerated_accepted
        )


@dataclass(frozen=True)
class _RobustStrategyResult:
    construction_mode: str
    order: str
    guides: str
    rail_count: int
    rail_placement: str
    merge_tangent_edges: bool
    overlap_diameter_mm: float
    quality: _LoftQualityMetrics | None
    cell_volumes_cm3: tuple[float, ...]
    used_fallback: bool
    fairing_tolerated: bool
    attempt_log: tuple[str, ...]
    log_json_path: str
    log_text_path: str
    log_write_error: str


class _RobustSearchCancelledSignal(RuntimeError):
    """Internal cooperative-cancellation signal."""


class _ManualGenerationCancelledSignal(RuntimeError):
    """Internal cooperative-cancellation signal for manual generation."""


class _RobustSearchTerminalError(RuntimeError):
    """Carries saved diagnostics from a failed or cancelled preflight."""

    def __init__(
        self,
        summary: str,
        *,
        cancelled: bool,
        attempt_log: tuple[str, ...],
        log_json_path: str,
        log_text_path: str,
        log_write_error: str,
    ) -> None:
        super().__init__(summary)
        self.summary = summary
        self.cancelled = bool(cancelled)
        self.attempt_log = tuple(attempt_log)
        self.log_json_path = str(log_json_path)
        self.log_text_path = str(log_text_path)
        self.log_write_error = str(log_write_error)

    @property
    def attempt_count(self) -> int:
        return len(self.attempt_log)


ROBUST_MAX_BOUNDARY_OVERLAP_DIAMETER_MM = 0.1
ROBUST_QUALITY_CONTOUR_SAMPLE_LIMIT = 25
ROBUST_QUALITY_REFINED_INTERVALS = 3
ROBUST_QUALITY_REGIONAL_REFINED_INTERVALS = 1
ROBUST_LOG_SCHEMA_VERSION = 5
ROBUST_MAX_EXECUTION_ATTEMPTS = 15
ROBUST_LOG_DIRECTORY = os.path.join(
    USER_CONFIG_DIRECTORY,
    "robust_search_logs",
)
ROBUST_MESSAGE_ATTEMPT_LIMIT = 20


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _json_safe_value(value):
    """Convert dataclass/result values to JSON-compatible primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _json_safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {
            field.name: _json_safe_value(getattr(value, field.name))
            for field in fields(value)
        }
    return str(value)


def _command_inputs_snapshot(inputs) -> dict:
    """Best-effort raw snapshot of every visible or grouped command input."""

    def snapshot_collection(collection) -> dict:
        snapshot: dict[str, object] = {}
        try:
            count = int(collection.count)
        except Exception:
            return snapshot
        for index in range(count):
            try:
                item = collection.item(index)
            except Exception:
                continue
            if item is None:
                continue
            item_id = str(getattr(item, "id", "") or f"item_{index}")
            entry: dict[str, object] = {
                "name": str(getattr(item, "name", "") or ""),
                "object_type": str(getattr(item, "objectType", "") or ""),
            }
            for attribute in (
                "value",
                "expression",
                "unitType",
                "isEnabled",
                "isVisible",
                "isExpanded",
            ):
                try:
                    entry[attribute] = _json_safe_value(
                        getattr(item, attribute)
                    )
                except Exception:
                    pass
            try:
                selected = item.selectedItem
                if selected is not None:
                    entry["selected_item"] = str(selected.name)
            except Exception:
                pass
            try:
                children = item.children
            except Exception:
                children = None
            if children is not None:
                entry["children"] = snapshot_collection(children)
            snapshot[item_id] = entry
        return snapshot

    return snapshot_collection(inputs)


def _manual_generation_log_session(
    config: dict,
    resolved_radii: list[float],
    section_mode: str,
    loft_construction_mode: str,
    loft_section_order: str,
    loft_guide_rails: str,
) -> dict:
    """Create a detailed manual-run log with a full parameter snapshot."""
    return {
        "schema_version": 1,
        "session_id": uuid.uuid4().hex,
        "project": {
            "name": PROJECT_NAME,
            "version": PROJECT_VERSION,
        },
        "generator_version": PROJECT_VERSION,
        "runtime": {
            "fusion_version": str(getattr(APP, "version", "") or ""),
            "python_version": sys.version,
            "platform": sys.platform,
        },
        "mode": "manual",
        "status": "running",
        "started_at_utc": _utc_now_text(),
        "finished_at_utc": "",
        "elapsed_seconds": 0.0,
        "design": {
            "intent": _robust_design_intent_text(),
            "document": str(
                getattr(APP.activeDocument, "name", "") or ""
            ),
        },
        "selection": {
            "section_mode": section_mode,
            "loft_construction_mode": _loft_construction_mode_to_storage(
                loft_construction_mode
            ),
            "loft_section_order": _loft_section_order_to_storage(
                loft_section_order
            ),
            "loft_guides": _loft_guides_to_storage(loft_guide_rails),
        },
        "parameters": _json_safe_value(config),
        "input_snapshot": {},
        "resolved_radii_mm": [float(value) for value in resolved_radii],
        "result": None,
        "display_result_text": "",
        "display_error_text": "",
        "displayed_message": "",
        "timeline": {},
        "error": "",
    }


def _manual_result_has_errors(result: GenerationResult | None) -> bool:
    """Return whether a completed manual run reports any feature error."""
    if result is None:
        return False
    for field in fields(result):
        if field.name.endswith("_error"):
            value = getattr(result, field.name, "")
            if isinstance(value, str) and value.strip():
                return True
    return False


def _save_manual_generation_log(
    session: dict,
    started_perf: float,
    status: str,
    result: GenerationResult | None = None,
    error_detail: str = "",
    display_result_text: str = "",
    display_error_text: str = "",
) -> tuple[str, str]:
    """Persist one manual execution log and return (path, error)."""
    session["status"] = str(status)
    session["finished_at_utc"] = _utc_now_text()
    session["elapsed_seconds"] = max(
        0.0,
        time.perf_counter() - float(started_perf),
    )
    session["result"] = _json_safe_value(result)
    session["display_result_text"] = str(display_result_text or "")
    session["display_error_text"] = str(display_error_text or "")
    session["error"] = str(error_detail or "")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:-3]
    path = os.path.join(
        MANUAL_LOG_DIRECTORY,
        f"manual_generation_{timestamp}_{session['session_id'][:8]}.json",
    )
    try:
        os.makedirs(MANUAL_LOG_DIRECTORY, exist_ok=True)
        _write_json_atomically(path, session)
        return path, ""
    except Exception as error:
        return "", f"{type(error).__name__}: {error}"


def _robust_design_intent_text() -> str:
    design = adsk.fusion.Design.cast(APP.activeProduct)
    if design is None or not design.isValid:
        return "unavailable"
    try:
        return str(design.designIntent)
    except Exception:
        return "legacy_or_unavailable"


def _robust_quality_region_mapping(
    region: _LoftQualityRegionMetrics | None,
) -> dict | None:
    if region is None:
        return None
    return {
        "accepted": bool(region.accepted),
        "sample_count": int(region.sample_count),
        "rms_error_mm": float(region.rms_error_mm),
        "max_error_mm": float(region.max_error_mm),
        "rms_percent_chord": float(region.rms_percent_chord),
        "max_percent_chord": float(region.max_percent_chord),
        "rms_wave_angle_deg": float(region.rms_wave_angle_deg),
        "max_wave_angle_deg": float(region.max_wave_angle_deg),
        "worst_radius_mm": float(region.worst_radius_mm),
        "worst_contour_index": int(region.worst_contour_index),
        "worst_wave_radius_mm": float(region.worst_wave_radius_mm),
        "worst_wave_contour_index": int(
            region.worst_wave_contour_index
        ),
    }


def _robust_quality_mapping(
    quality: _LoftQualityMetrics | None,
) -> dict | None:
    if quality is None:
        return None
    return {
        "accepted": bool(quality.accepted),
        "accepted_tolerating_fairing": bool(
            quality.accepted_tolerating_fairing
        ),
        "accepted_tolerating_root_transition": bool(
            quality.accepted_tolerating_fairing
        ),
        "sample_count": int(quality.sample_count),
        "rms_error_mm": float(quality.rms_error_mm),
        "max_error_mm": float(quality.max_error_mm),
        "rms_percent_chord": float(quality.rms_percent_chord),
        "max_percent_chord": float(quality.max_percent_chord),
        "limit_percent_chord": float(quality.limit_percent_chord),
        "rms_wave_angle_deg": float(quality.rms_wave_angle_deg),
        "max_wave_angle_deg": float(quality.max_wave_angle_deg),
        "limit_wave_angle_deg": float(quality.limit_wave_angle_deg),
        "worst_radius_mm": float(quality.worst_radius_mm),
        "worst_contour_index": int(quality.worst_contour_index),
        "worst_wave_radius_mm": float(
            quality.worst_wave_radius_mm
        ),
        "worst_wave_contour_index": int(
            quality.worst_wave_contour_index
        ),
        "fairing_end_radius_mm": float(quality.fairing_end_radius_mm),
        "post_fairing_margin_multiplier": float(
            quality.post_fairing_margin_multiplier
        ),
        "post_fairing_margin_mm": float(quality.post_fairing_margin_mm),
        "root_tolerance_end_radius_mm": float(
            quality.root_tolerance_end_radius_mm
        ),
        "fairing": _robust_quality_region_mapping(quality.fairing),
        "post_fairing": _robust_quality_region_mapping(
            quality.post_fairing
        ),
        "aerodynamic": _robust_quality_region_mapping(
            quality.aerodynamic
        ),
    }


def _write_text_atomically(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary_path = path + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except Exception:
            pass
        raise


def _format_robust_search_log_text(session: dict) -> str:
    lines = [
        PROJECT_NAME,
        f"Version: {PROJECT_VERSION}",
        f"Schema: {session.get('schema_version')}",
        f"Session: {session.get('session_id', '')}",
        f"Status: {session.get('status', '')}",
        f"Started UTC: {session.get('started_at_utc', '')}",
        f"Finished UTC: {session.get('finished_at_utc', '')}",
        (
            "Elapsed: "
            f"{float(session.get('elapsed_seconds', 0.0)):.6f} s"
        ),
        "",
        "SEARCH CONFIGURATION",
        json.dumps(
            session.get("configuration", {}),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ),
        "",
        "ATTEMPTS",
    ]

    attempts = session.get("attempts", [])
    if not attempts:
        lines.append("(none)")
    for attempt in attempts:
        lines.extend(
            [
                "",
                (
                    f"[{int(attempt.get('attempt', 0)):03d}] "
                    f"{attempt.get('status', '')}"
                ),
                (
                    "  construction="
                    f"{attempt.get('construction_mode', '')}; "
                    "order="
                    f"{attempt.get('order', '')}; "
                    f"rails={attempt.get('rails', 0)}; "
                    "placement="
                    f"{attempt.get('rail_placement', '')}; "
                    "merge="
                    f"{attempt.get('merge_tangent_edges', False)}; "
                    "overlap="
                    f"{attempt.get('overlap_diameter_mm', 0.0):g} mm"
                ),
                (
                    "  loft="
                    f"{attempt.get('loft_success', False)}; "
                    "trailing_edge_loft="
                    f"{attempt.get('trailing_edge_loft_success', False)}; "
                    "surface_stitch="
                    f"{attempt.get('surface_stitch_success', False)}; "
                    "quality_checked="
                    f"{attempt.get('quality_checked', False)}; "
                    "quality_accepted="
                    f"{attempt.get('quality_accepted', False)}; "
                    "strict_accepted="
                    f"{attempt.get('strict_accepted', False)}; "
                    "fairing_tolerated_accepted="
                    f"{attempt.get('fairing_tolerated_accepted', False)}; "
                    "valid_fallback="
                    f"{attempt.get('valid_fallback', False)}; "
                    "boundary_fill="
                    f"{attempt.get('boundary_fill_success', False)}"
                ),
                (
                    "  sections_reused="
                    f"{attempt.get('sections_reused', False)}"
                ),
                (
                    "  elapsed="
                    f"{float(attempt.get('elapsed_seconds', 0.0)):.6f} s; "
                    "stages="
                    + json.dumps(
                        attempt.get("stage_seconds", {}),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                ),
                (
                    "  cleanup_success="
                    f"{attempt.get('cleanup_success', False)}"
                ),
            ]
        )
        quality = attempt.get("quality")
        if quality:
            lines.append(
                "  quality: "
                f"max={quality.get('max_percent_chord', 0.0):.9g}% chord; "
                f"RMS={quality.get('rms_percent_chord', 0.0):.9g}% chord; "
                f"equivalent_angle={quality.get('max_wave_angle_deg', 0.0):.9g} deg; "
                "equivalent_angle_RMS="
                f"{quality.get('rms_wave_angle_deg', 0.0):.9g} deg; "
                f"samples={quality.get('sample_count', 0)}; "
                "fairing_tolerated="
                f"{quality.get('accepted_tolerating_fairing', False)}"
            )
            for region_name in ("fairing", "post_fairing", "aerodynamic"):
                region = quality.get(region_name)
                if region:
                    lines.append(
                        f"  quality_{region_name}: "
                        f"accepted={region.get('accepted', False)}; "
                        f"max={region.get('max_percent_chord', 0.0):.9g}% chord; "
                        f"RMS={region.get('rms_percent_chord', 0.0):.9g}% chord; "
                        "equivalent_angle="
                        f"{region.get('max_wave_angle_deg', 0.0):.9g} deg; "
                        f"samples={region.get('sample_count', 0)}"
                    )
        volumes = attempt.get("cell_volumes_cm3", [])
        if volumes:
            lines.append(
                "  cell_volumes_cm3="
                + json.dumps(volumes, ensure_ascii=False)
            )
        if attempt.get("error_detail"):
            lines.append(
                "  error="
                + str(attempt.get("error_detail", "")).replace(
                    "\n",
                    "\n    ",
                )
            )
        if attempt.get("cleanup_error"):
            lines.append(
                "  cleanup_error="
                + str(attempt.get("cleanup_error", ""))
            )

    selected = session.get("selected_strategy")
    if selected:
        lines.extend(
            [
                "",
                "SELECTED STRATEGY",
                json.dumps(
                    selected,
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ]
        )

    if session.get("terminal_detail"):
        lines.extend(
            [
                "",
                "TERMINAL DETAIL",
                str(session.get("terminal_detail")),
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _save_robust_search_log(
    session: dict,
) -> tuple[str, str, str]:
    os.makedirs(ROBUST_LOG_DIRECTORY, exist_ok=True)
    session_id = str(session.get("session_id") or uuid.uuid4().hex)
    started = str(session.get("started_at_utc") or _utc_now_text())
    timestamp = re.sub(r"[^0-9]", "", started)[:17]
    base_name = f"robust_search_{timestamp}_{session_id[:8]}"
    json_path = os.path.join(
        ROBUST_LOG_DIRECTORY,
        base_name + ".json",
    )
    text_path = os.path.join(
        ROBUST_LOG_DIRECTORY,
        base_name + ".txt",
    )
    errors: list[str] = []

    try:
        _write_text_atomically(
            json_path,
            json.dumps(
                session,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
        )
    except Exception as error:
        json_path = ""
        errors.append(
            f"JSON: {type(error).__name__}: {error}"
        )

    try:
        _write_text_atomically(
            text_path,
            _format_robust_search_log_text(session),
        )
    except Exception as error:
        text_path = ""
        errors.append(
            f"TXT: {type(error).__name__}: {error}"
        )

    return json_path, text_path, " | ".join(errors)


def _robust_attempt_message_text(
    attempt_log: str,
    maximum_lines: int = ROBUST_MESSAGE_ATTEMPT_LIMIT,
) -> str:
    lines = [
        line
        for line in str(attempt_log).splitlines()
        if line.strip()
    ]
    if len(lines) <= maximum_lines:
        return "\n".join(lines)
    omitted = len(lines) - maximum_lines
    return (
        "\n".join(lines[:maximum_lines])
        + "\n"
        + _t(
            "result.robust_candidate_summary_omitted",
            count=omitted,
        )
    )



def _compact_robust_error_detail(
    detail: str,
    maximum_characters: int = 150,
) -> str:
    """Return one stable, short diagnostic for UI summaries."""
    lines = [
        line.strip()
        for line in str(detail).splitlines()
        if line.strip()
    ]
    if not lines:
        return ""

    for line in lines:
        match = re.search(
            r"\b(?:ASM|LOFT|BREP|BOUNDARY|MFG|SMT)_[A-Z0-9_]+\b",
            line,
        )
        if match:
            return match.group(0)

    first = lines[0]
    if len(first) <= maximum_characters:
        return first
    return first[: max(1, maximum_characters - 1)].rstrip() + "…"


def _robust_progress_outcome_text(
    outcome: _RobustCandidateOutcome,
    rails: int,
    overlap_mm: float,
    elapsed_seconds: float,
) -> str:
    if outcome.strict_accepted:
        key = "progress.result.accepted"
    elif outcome.fairing_tolerated_accepted:
        key = "progress.result.fairing_tolerated"
    elif outcome.finalizable:
        key = "progress.result.fallback"
    elif outcome.failed_stage == "loft":
        key = "progress.result.loft_failed"
    elif outcome.failed_stage == "quality":
        key = "progress.result.quality_rejected"
    elif outcome.failed_stage == "boundary_fill":
        key = "progress.result.boundary_fill_failed"
    else:
        key = "progress.result.rejected"
    return _t(
        key,
        rails=rails,
        overlap=overlap_mm,
        elapsed=elapsed_seconds,
    )


def _manual_progress_message(stage: str, detail: str = "") -> str:
    """Return a bounded-width message for Fusion's auto-sized progress UI."""
    stage_text = " ".join(str(stage or "").split())
    detail_text = " ".join(str(detail or "").split())

    stage_lines = textwrap.wrap(
        stage_text,
        width=MANUAL_PROGRESS_LINE_WIDTH,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [""]
    detail_lines = textwrap.wrap(
        detail_text,
        width=MANUAL_PROGRESS_LINE_WIDTH,
        break_long_words=True,
        break_on_hyphens=False,
    )
    if len(detail_lines) > MANUAL_PROGRESS_MAX_DETAIL_LINES:
        detail_lines = detail_lines[:MANUAL_PROGRESS_MAX_DETAIL_LINES]
        last = detail_lines[-1].rstrip()
        final_line = (
            last[:-1]
            if len(last) >= MANUAL_PROGRESS_LINE_WIDTH
            else last
        )
        detail_lines[-1] = final_line + "…"

    return _t(
        "progress.manual_message",
        stage="\n".join(stage_lines),
        detail="\n".join(detail_lines),
    ).rstrip()


class _ManualProgressController:
    """Small, independent progress dialog for one manual generation run."""

    def __init__(self) -> None:
        self.dialog = None
        self._was_observed_showing = False
        self._closing_normally = False

    def show(self) -> None:
        global _active_manual_progress

        try:
            dialog = UI.createProgressDialog()
            dialog.isBackgroundTranslucent = False
            dialog.isCancelButtonShown = True
            dialog.cancelButtonText = _t("progress.manual_cancel")
            shown = dialog.show(
                _t("progress.manual_title"),
                _t("progress.manual_starting"),
                0,
                100,
                0,
            )
            if shown:
                self.dialog = dialog
                _active_manual_progress = self
                adsk.doEvents()
                try:
                    self._was_observed_showing = bool(dialog.isShowing)
                except Exception:
                    self._was_observed_showing = False
        except Exception:
            self.dialog = None
            self._was_observed_showing = False
            _active_manual_progress = None

    def close(self) -> None:
        global _active_manual_progress

        self._closing_normally = True
        if self.dialog is not None:
            try:
                if self.dialog.isShowing:
                    self.dialog.hide()
            except Exception:
                pass
        self.dialog = None
        if _active_manual_progress is self:
            _active_manual_progress = None

    def _raise_if_cancelled_or_closed(self) -> None:
        if self.dialog is None or self._closing_normally:
            return

        try:
            cancelled = bool(self.dialog.wasCancelled)
        except Exception:
            cancelled = False
        try:
            showing = bool(self.dialog.isShowing)
        except Exception:
            showing = False

        if showing:
            self._was_observed_showing = True
        unexpectedly_closed = self._was_observed_showing and not showing
        if cancelled or unexpectedly_closed:
            raise _ManualGenerationCancelledSignal(
                _t("progress.manual_cancelled")
            )

    def checkpoint(
        self,
        progress_value: int,
        stage: str,
        detail: str = "",
    ) -> None:
        self._raise_if_cancelled_or_closed()
        if self.dialog is not None:
            try:
                self.dialog.progressValue = max(
                    0,
                    min(100, int(progress_value)),
                )
                self.dialog.message = _manual_progress_message(
                    stage,
                    detail,
                )
            except Exception:
                pass
        try:
            adsk.doEvents()
        except Exception:
            pass
        self._raise_if_cancelled_or_closed()


def _manual_progress_checkpoint(
    progress_value: int,
    stage: str,
    detail: str = "",
) -> None:
    """Update the active manual dialog, or do nothing outside manual mode."""
    controller = _active_manual_progress
    if controller is not None:
        controller.checkpoint(progress_value, stage, detail)


class _RobustProgressController:
    """Cooperative ProgressDialog wrapper for the robust preflight."""

    def __init__(self, total_strategies: int) -> None:
        self.total_strategies = max(1, int(total_strategies))
        self.dialog = None
        self._was_observed_showing = False
        self._closing_normally = False

    def __enter__(self) -> "_RobustProgressController":
        try:
            dialog = UI.createProgressDialog()
            dialog.isBackgroundTranslucent = False
            dialog.isCancelButtonShown = True
            dialog.cancelButtonText = _t("progress.cancel")
            shown = dialog.show(
                _t("progress.robust_title"),
                _t("progress.robust_starting"),
                0,
                self.total_strategies,
                0,
            )
            if shown:
                self.dialog = dialog
                adsk.doEvents()
                try:
                    self._was_observed_showing = bool(
                        dialog.isShowing
                    )
                except Exception:
                    self._was_observed_showing = False
        except Exception:
            self.dialog = None
            self._was_observed_showing = False
        return self

    def __exit__(self, exc_type, exc_value, traceback_value) -> None:
        self._closing_normally = True
        if self.dialog is not None:
            try:
                if self.dialog.isShowing:
                    self.dialog.hide()
            except Exception:
                pass
        self.dialog = None

    def _raise_if_cancelled_or_closed(self) -> None:
        if self.dialog is None or self._closing_normally:
            return

        try:
            cancelled = bool(self.dialog.wasCancelled)
        except Exception:
            cancelled = False

        try:
            showing = bool(self.dialog.isShowing)
        except Exception:
            showing = False

        if showing:
            self._was_observed_showing = True

        unexpectedly_closed = (
            self._was_observed_showing and not showing
        )
        if cancelled or unexpectedly_closed:
            raise _RobustSearchCancelledSignal(
                _t("progress.cancelled")
            )

    def checkpoint(
        self,
        strategy_number: int,
        stage: str,
        detail: str = "",
        *,
        completed: bool = False,
    ) -> None:
        self._raise_if_cancelled_or_closed()

        if self.dialog is not None:
            try:
                value = (
                    int(strategy_number)
                    if completed
                    else max(0, int(strategy_number) - 1)
                )
                self.dialog.progressValue = min(
                    value,
                    self.total_strategies,
                )
                self.dialog.message = _t(
                    "progress.robust_message",
                    current=strategy_number,
                    total=self.total_strategies,
                    stage=stage,
                    detail=detail,
                )
            except Exception:
                pass

        try:
            adsk.doEvents()
        except Exception:
            pass

        self._raise_if_cancelled_or_closed()

def _quality_contour_indices(
    contour_point_count: int,
    sample_limit: int = ROBUST_QUALITY_CONTOUR_SAMPLE_LIMIT,
) -> tuple[int, ...]:
    """Sample the NACA contour while excluding ambiguous exact TE vertices."""
    if contour_point_count < 5:
        raise ValueError("O contorno possui poucos pontos para avaliação.")

    candidates = list(range(1, contour_point_count - 1))
    target = min(max(3, int(sample_limit)), len(candidates))
    if target == len(candidates):
        return tuple(candidates)

    selected_positions = {
        round(index * (len(candidates) - 1) / (target - 1))
        for index in range(target)
    }
    midpoint = (contour_point_count - 1) // 2
    selected = {candidates[position] for position in selected_positions}
    selected.add(midpoint)
    return tuple(sorted(selected))


def _closest_distance_to_surface_body_mm(
    surface_body: adsk.fusion.BRepBody,
    point_xyz_mm: tuple[float, float, float],
) -> float:
    """Return the nearest bounded-face distance for one theoretical point."""
    query = adsk.core.Point3D.create(
        point_xyz_mm[0] / 10.0,
        point_xyz_mm[1] / 10.0,
        point_xyz_mm[2] / 10.0,
    )
    best_cm = math.inf

    faces = surface_body.faces
    for face_index in range(faces.count):
        face = faces.item(face_index)
        if face is None or not face.isValid:
            continue
        evaluator = face.evaluator
        if evaluator is None or not evaluator.isValid:
            continue
        ok_parameter, parameter = evaluator.getParameterAtPoint(query)
        if not ok_parameter or parameter is None:
            continue
        try:
            if not evaluator.isParameterOnFace(parameter):
                continue
        except Exception:
            continue
        ok_point, surface_point = evaluator.getPointAtParameter(parameter)
        if not ok_point or surface_point is None:
            continue
        distance_cm = float(query.distanceTo(surface_point))
        if distance_cm < best_cm:
            best_cm = distance_cm

    if not math.isfinite(best_cm):
        raise RuntimeError(
            "Não foi possível projetar um ponto teórico nas faces do loft."
        )
    return best_cm * 10.0


def _quality_interval_indices(radii: list[float]) -> tuple[int, ...]:
    """Exclude overlap-dominated end intervals when enough sections exist."""
    interval_count = len(radii) - 1
    if interval_count < 1:
        return ()
    if interval_count >= 4:
        return tuple(range(1, interval_count - 1))
    return tuple(range(interval_count))


def _evaluate_loft_surface_quality(
    surface_body: adsk.fusion.BRepBody,
    config: BladeConfig,
    radii: list[float],
    apply_angle: bool,
    profile_points: int,
    limit_percent_chord: float,
    limit_wave_angle_deg: float,
    post_fairing_margin_multiplier: float,
    cancel_checkpoint=None,
) -> _LoftQualityMetrics:
    """Measure fidelity in fairing, post-fairing, and aerodynamic regions.

    The equivalent angle is derived from positional deviation and radial
    spacing. It remains a useful strict comparison target in the aerodynamic
    blade region, but is not a direct curvature or zebra-stripe measurement.
    Fairing and configurable post-fairing samples are reported separately and
    may be tolerated when every later aerodynamic station meets the targets.
    """
    if limit_percent_chord <= 0.0:
        raise ValueError(
            "Loft_Quality_Max_Deviation_Percent deve ser positivo."
        )
    if limit_wave_angle_deg <= 0.0:
        raise ValueError(
            "Loft_Quality_Max_Wave_Angle_Deg deve ser positivo."
        )
    if post_fairing_margin_multiplier < 0.0:
        raise ValueError(
            "Loft_Quality_Post_Fairing_Margin_Multiplier não pode ser negativo."
        )

    ordered_radii = sorted(float(value) for value in radii)
    interval_indices = _quality_interval_indices(ordered_radii)
    if not interval_indices:
        raise ValueError(
            "São necessárias pelo menos duas seções para avaliar o loft."
        )

    probe = wrapped_section_geometry(
        config,
        0.5 * (ordered_radii[0] + ordered_radii[1]),
        apply_geometric_angle=apply_angle,
        profile_points_override=profile_points,
    )
    contour_indices = _quality_contour_indices(len(probe.points_xyz_mm))

    fairing_end_radius_mm = min(
        float(config.tip_radius_mm),
        float(config.root_radius_mm + max(0.0, config.fairing_size_mm)),
    )
    has_fairing_region = (
        config.fairing_size_mm > 0.0
        and fairing_end_radius_mm > config.root_radius_mm + 1e-9
    )
    post_fairing_margin_mm = (
        max(0.0, float(post_fairing_margin_multiplier))
        * max(0.0, float(config.fairing_size_mm))
        if has_fairing_region
        else 0.0
    )
    root_tolerance_end_radius_mm = min(
        float(config.tip_radius_mm),
        fairing_end_radius_mm + post_fairing_margin_mm,
    )
    has_post_fairing_region = (
        has_fairing_region
        and root_tolerance_end_radius_mm > fairing_end_radius_mm + 1e-9
    )

    def new_accumulator() -> dict:
        return {
            "errors_mm": [],
            "errors_percent": [],
            "wave_angles_deg": [],
            "worst_error_mm": -1.0,
            "worst_percent": -1.0,
            "worst_radius_mm": 0.0,
            "worst_contour_index": -1,
            "worst_wave_angle_deg": -1.0,
            "worst_wave_radius_mm": 0.0,
            "worst_wave_contour_index": -1,
        }

    global_acc = new_accumulator()
    fairing_acc = new_accumulator()
    post_fairing_acc = new_accumulator()
    aerodynamic_acc = new_accumulator()
    interval_scores: list[tuple[float, float, int, str]] = []

    def record_sample(
        accumulator: dict,
        error_mm: float,
        error_percent: float,
        wave_angle_deg: float,
        radius_mm: float,
        contour_index: int,
    ) -> None:
        accumulator["errors_mm"].append(error_mm)
        accumulator["errors_percent"].append(error_percent)
        accumulator["wave_angles_deg"].append(wave_angle_deg)
        if error_percent > accumulator["worst_percent"]:
            accumulator["worst_error_mm"] = error_mm
            accumulator["worst_percent"] = error_percent
            accumulator["worst_radius_mm"] = radius_mm
            accumulator["worst_contour_index"] = contour_index
        if wave_angle_deg > accumulator["worst_wave_angle_deg"]:
            accumulator["worst_wave_angle_deg"] = wave_angle_deg
            accumulator["worst_wave_radius_mm"] = radius_mm
            accumulator["worst_wave_contour_index"] = contour_index

    def finish_region(
        accumulator: dict,
    ) -> _LoftQualityRegionMetrics | None:
        errors_mm = accumulator["errors_mm"]
        if not errors_mm:
            return None
        errors_percent = accumulator["errors_percent"]
        wave_angles_deg = accumulator["wave_angles_deg"]
        rms_error_mm = math.sqrt(
            sum(value * value for value in errors_mm) / len(errors_mm)
        )
        rms_percent = math.sqrt(
            sum(value * value for value in errors_percent)
            / len(errors_percent)
        )
        rms_wave_angle_deg = math.sqrt(
            sum(value * value for value in wave_angles_deg)
            / len(wave_angles_deg)
        )
        max_percent = max(0.0, accumulator["worst_percent"])
        max_wave = max(0.0, accumulator["worst_wave_angle_deg"])
        return _LoftQualityRegionMetrics(
            accepted=(
                max_percent <= limit_percent_chord
                and max_wave <= limit_wave_angle_deg
            ),
            sample_count=len(errors_mm),
            rms_error_mm=rms_error_mm,
            max_error_mm=max(0.0, accumulator["worst_error_mm"]),
            rms_percent_chord=rms_percent,
            max_percent_chord=max_percent,
            rms_wave_angle_deg=rms_wave_angle_deg,
            max_wave_angle_deg=max_wave,
            worst_radius_mm=accumulator["worst_radius_mm"],
            worst_contour_index=accumulator["worst_contour_index"],
            worst_wave_radius_mm=accumulator["worst_wave_radius_mm"],
            worst_wave_contour_index=(
                accumulator["worst_wave_contour_index"]
            ),
        )

    def sample_station(
        interval_index: int,
        fraction: float,
    ) -> tuple[float, float, str]:
        left = ordered_radii[interval_index]
        right = ordered_radii[interval_index + 1]
        interval_mm = right - left
        if interval_mm <= 0.0:
            raise RuntimeError("Intervalo radial não positivo.")
        radius_mm = left + fraction * interval_mm
        if cancel_checkpoint is not None:
            cancel_checkpoint(
                _t(
                    "progress.quality_station",
                    radius=radius_mm,
                    fraction=100.0 * fraction,
                )
            )
        section = wrapped_section_geometry(
            config,
            radius_mm,
            apply_geometric_angle=apply_angle,
            profile_points_override=profile_points,
        )
        chord_mm = max(float(section.chord_mm), 1e-12)
        denominator_mm = max(
            interval_mm * fraction * (1.0 - fraction),
            1e-12,
        )
        station_worst_percent = 0.0
        station_worst_wave = 0.0
        in_fairing = bool(
            has_fairing_region
            and radius_mm < fairing_end_radius_mm - 1e-9
        )
        in_post_fairing = bool(
            has_post_fairing_region
            and radius_mm >= fairing_end_radius_mm - 1e-9
            and radius_mm < root_tolerance_end_radius_mm - 1e-9
        )
        if in_fairing:
            region_name = "fairing"
            region_acc = fairing_acc
        elif in_post_fairing:
            region_name = "post_fairing"
            region_acc = post_fairing_acc
        else:
            region_name = "aerodynamic"
            region_acc = aerodynamic_acc

        for contour_index in contour_indices:
            error_mm = _closest_distance_to_surface_body_mm(
                surface_body,
                tuple(section.points_xyz_mm[contour_index]),
            )
            error_percent = 100.0 * error_mm / chord_mm
            wave_angle_deg = math.degrees(
                math.atan(error_mm / denominator_mm)
            )
            record_sample(
                global_acc,
                error_mm,
                error_percent,
                wave_angle_deg,
                radius_mm,
                contour_index,
            )
            record_sample(
                region_acc,
                error_mm,
                error_percent,
                wave_angle_deg,
                radius_mm,
                contour_index,
            )
            station_worst_percent = max(
                station_worst_percent,
                error_percent,
            )
            station_worst_wave = max(
                station_worst_wave,
                wave_angle_deg,
            )
        return station_worst_percent, station_worst_wave, region_name

    for interval_index in interval_indices:
        percent_score, wave_score, region_name = sample_station(
            interval_index, 0.5
        )
        interval_scores.append(
            (percent_score, wave_score, interval_index, region_name)
        )

    refinement_indices: set[int] = set()
    by_position = sorted(
        interval_scores,
        key=lambda item: item[0],
        reverse=True,
    )
    by_wave = sorted(
        interval_scores,
        key=lambda item: item[1],
        reverse=True,
    )
    for entries in (by_position, by_wave):
        for _, _, interval_index, _ in entries[
            :ROBUST_QUALITY_REFINED_INTERVALS
        ]:
            refinement_indices.add(interval_index)

    # When fairing tolerance could affect acceptance, always refine at least
    # one worst aerodynamic interval independently of the global outliers.
    if has_fairing_region:
        aerodynamic_scores = [
            item for item in interval_scores if item[3] == "aerodynamic"
        ]
        for key_index in (0, 1):
            entries = sorted(
                aerodynamic_scores,
                key=lambda item: item[key_index],
                reverse=True,
            )
            for _, _, interval_index, _ in entries[
                :ROBUST_QUALITY_REGIONAL_REFINED_INTERVALS
            ]:
                refinement_indices.add(interval_index)

    for interval_index in sorted(refinement_indices):
        sample_station(interval_index, 0.25)
        sample_station(interval_index, 0.75)

    global_region = finish_region(global_acc)
    if global_region is None:
        raise RuntimeError("A avaliação do loft não produziu amostras válidas.")
    fairing_region = finish_region(fairing_acc)
    post_fairing_region = finish_region(post_fairing_acc)
    aerodynamic_region = finish_region(aerodynamic_acc)

    return _LoftQualityMetrics(
        accepted=global_region.accepted,
        sample_count=global_region.sample_count,
        rms_error_mm=global_region.rms_error_mm,
        max_error_mm=global_region.max_error_mm,
        rms_percent_chord=global_region.rms_percent_chord,
        max_percent_chord=global_region.max_percent_chord,
        limit_percent_chord=limit_percent_chord,
        rms_wave_angle_deg=global_region.rms_wave_angle_deg,
        max_wave_angle_deg=global_region.max_wave_angle_deg,
        limit_wave_angle_deg=limit_wave_angle_deg,
        worst_radius_mm=global_region.worst_radius_mm,
        worst_contour_index=global_region.worst_contour_index,
        worst_wave_radius_mm=global_region.worst_wave_radius_mm,
        worst_wave_contour_index=global_region.worst_wave_contour_index,
        fairing_end_radius_mm=fairing_end_radius_mm,
        post_fairing_margin_multiplier=float(
            post_fairing_margin_multiplier
        ),
        post_fairing_margin_mm=post_fairing_margin_mm,
        root_tolerance_end_radius_mm=root_tolerance_end_radius_mm,
        fairing=fairing_region,
        post_fairing=post_fairing_region,
        aerodynamic=aerodynamic_region,
    )


def _automatic_overlap_sequence(
    initial_overlap_diameter_mm: float,
    maximum_overlap_diameter_mm: float = (
        ROBUST_MAX_BOUNDARY_OVERLAP_DIAMETER_MM
    ),
) -> tuple[float, ...]:
    """Return overlap, overlap*10, ... up to the configured safety ceiling."""
    initial = float(initial_overlap_diameter_mm)
    maximum = float(maximum_overlap_diameter_mm)
    if initial <= 0.0 or maximum <= 0.0:
        raise ValueError("Os overlaps automáticos devem ser positivos.")
    if initial > maximum:
        return (initial,)

    values: list[float] = []
    current = initial
    while current <= maximum * (1.0 + 1e-12):
        values.append(current)
        current *= 10.0
    return tuple(values)


def _robust_rail_counts(
    maximum_rail_count: int,
    profile_points_per_surface: int,
    rail_placement: str,
) -> tuple[int, ...]:
    """Search at least through nine rails when resolution permits."""
    requested = _normalize_distributed_rail_count(maximum_rail_count)
    supported = _maximum_distributed_rail_count(
        profile_points_per_surface,
        rail_placement,
    )
    maximum = min(max(9, requested), supported)
    if maximum < 3:
        return (0,)
    if maximum % 2 == 0:
        maximum -= 1
    return (0, *range(3, maximum + 1, 2))



@dataclass(frozen=True)
class _RobustComponentSnapshot:
    sketch_tokens: frozenset[str]
    loft_tokens: frozenset[str]
    stitch_tokens: frozenset[str]
    extrude_tokens: frozenset[str]
    boundary_fill_tokens: frozenset[str]
    body_tokens: frozenset[str]


def _robust_entity_token(entity: object) -> str:
    """Return the stable Fusion token used to distinguish pre-existing items."""
    try:
        token = str(entity.entityToken)
    except Exception:
        token = ""
    if not token:
        raise RuntimeError(
            "Uma entidade da busca robusta não possui entityToken."
        )
    return token


def _robust_collection_tokens(collection: object) -> frozenset[str]:
    tokens: set[str] = set()
    count = int(collection.count)
    for index in range(count):
        entity = collection.item(index)
        if entity is None:
            continue
        try:
            if not entity.isValid:
                continue
        except Exception:
            pass
        tokens.add(_robust_entity_token(entity))
    return frozenset(tokens)


def _capture_robust_component_snapshot(
    component: adsk.fusion.Component,
) -> _RobustComponentSnapshot:
    """Capture entities that must survive a same-component preflight."""
    features = component.features
    return _RobustComponentSnapshot(
        sketch_tokens=_robust_collection_tokens(component.sketches),
        loft_tokens=_robust_collection_tokens(features.loftFeatures),
        stitch_tokens=_robust_collection_tokens(features.stitchFeatures),
        extrude_tokens=_robust_collection_tokens(features.extrudeFeatures),
        boundary_fill_tokens=_robust_collection_tokens(
            features.boundaryFillFeatures
        ),
        body_tokens=_robust_collection_tokens(component.bRepBodies),
    )


def _robust_new_entities(
    collection: object,
    existing_tokens: frozenset[str],
) -> list[object]:
    result: list[object] = []
    count = int(collection.count)
    for index in range(count):
        entity = collection.item(index)
        if entity is None:
            continue
        try:
            if not entity.isValid:
                continue
        except Exception:
            pass
        try:
            token = _robust_entity_token(entity)
        except Exception:
            continue
        if token not in existing_tokens:
            result.append(entity)
    return result


def _delete_robust_entities(
    collection: object,
    existing_tokens: frozenset[str],
    label: str,
    errors: list[str],
) -> None:
    """Delete candidate-owned entities in reverse collection order."""
    for entity in reversed(
        _robust_new_entities(collection, existing_tokens)
    ):
        try:
            if entity is not None and entity.isValid:
                result = entity.deleteMe()
                if result is False and entity.isValid:
                    raise RuntimeError("deleteMe retornou False")
        except Exception as error:
            errors.append(
                f"{label}: {type(error).__name__}: {error}"
            )


def _cleanup_robust_component_candidate(
    component: adsk.fusion.Component,
    snapshot: _RobustComponentSnapshot,
) -> None:
    """Remove all preflight geometry without touching the user's geometry.

    Dependency order matters: Boundary Fill first, followed by its cylinder
    extrusions, the loft, rail/section sketches, and finally any orphan body.
    """
    errors: list[str] = []
    features = component.features

    _delete_robust_entities(
        features.boundaryFillFeatures,
        snapshot.boundary_fill_tokens,
        "Boundary Fill temporário",
        errors,
    )
    _delete_robust_entities(
        features.extrudeFeatures,
        snapshot.extrude_tokens,
        "extrusão temporária",
        errors,
    )
    _delete_robust_entities(
        features.stitchFeatures,
        snapshot.stitch_tokens,
        "costura temporária",
        errors,
    )
    _delete_robust_entities(
        features.loftFeatures,
        snapshot.loft_tokens,
        "loft temporário",
        errors,
    )
    _delete_robust_entities(
        component.sketches,
        snapshot.sketch_tokens,
        "esboço temporário",
        errors,
    )
    _delete_robust_entities(
        component.bRepBodies,
        snapshot.body_tokens,
        "corpo temporário órfão",
        errors,
    )

    remaining = (
        len(
            _robust_new_entities(
                features.boundaryFillFeatures,
                snapshot.boundary_fill_tokens,
            )
        )
        + len(
            _robust_new_entities(
                features.extrudeFeatures,
                snapshot.extrude_tokens,
            )
        )
        + len(
            _robust_new_entities(
                features.stitchFeatures,
                snapshot.stitch_tokens,
            )
        )
        + len(
            _robust_new_entities(
                features.loftFeatures,
                snapshot.loft_tokens,
            )
        )
        + len(
            _robust_new_entities(
                component.sketches,
                snapshot.sketch_tokens,
            )
        )
        + len(
            _robust_new_entities(
                component.bRepBodies,
                snapshot.body_tokens,
            )
        )
    )
    if remaining:
        errors.append(
            f"{remaining} entidade(s) temporária(s) permaneceram no componente"
        )

    if errors:
        raise RuntimeError(
            "A limpeza do candidato robusto falhou: "
            + " | ".join(errors)
        )


def _robust_can_use_internal_component() -> bool:
    """Use child-component isolation only in a Hybrid Design.

    Part Design supports one component only. Assembly Design also does not
    support internal child components in the same way as a Hybrid Design.
    Older Fusion builds without Design.designIntent retain the legacy behavior.
    """
    design = adsk.fusion.Design.cast(APP.activeProduct)
    if design is None or not design.isValid:
        return False

    try:
        intent = design.designIntent
        hybrid_intent = (
            adsk.fusion.DesignIntentTypes.HybridDesignIntentType
        )
        return intent == hybrid_intent
    except Exception:
        # Compatibility with Fusion builds predating Design.designIntent.
        return True


@dataclass
class _RobustPreflightWorkspace:
    parent_component: adsk.fusion.Component
    component: adsk.fusion.Component
    occurrence: object | None
    parent_snapshot: _RobustComponentSnapshot | None
    candidate_snapshot: _RobustComponentSnapshot
    section_path_sources: list[
        tuple[
            float,
            adsk.fusion.SketchFittedSpline,
            adsk.fusion.SketchFittedSpline,
        ]
    ]
    section_profile_points: list[
        tuple[float, tuple[tuple[float, float, float], ...]]
    ]
    trailing_edge_points: list[
        tuple[
            float,
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ]
    root_radius_mm: float
    tip_radius_mm: float
    overlap_diameter_mm: float
    sections_seconds: float
    sections_reported: bool = False


def _create_robust_preflight_workspace(
    parent_component: adsk.fusion.Component,
    config: BladeConfig,
    radii: list[float],
    apply_angle: bool,
    profile_points: int,
    overlap_diameter_mm: float,
    require_boundary_fill: bool,
    progress: _RobustProgressController,
    strategy_number: int,
) -> _RobustPreflightWorkspace:
    """Create one reusable set of wrapped sections for one overlap value."""
    occurrence = None
    parent_snapshot = None
    component = parent_component

    progress.checkpoint(
        strategy_number,
        _t("progress.stage.prepare"),
        _t(
            "progress.candidate_detail",
            order="workspace",
            rails=0,
            overlap=overlap_diameter_mm,
        ),
    )

    if _robust_can_use_internal_component():
        try:
            occurrence = parent_component.occurrences.addNewComponent(
                adsk.core.Matrix3D.create()
            )
        except Exception:
            occurrence = None

    if occurrence is not None and occurrence.isValid:
        occurrence.isLightBulbOn = False
        component = occurrence.component
        component.name = (
            "Robust preflight workspace — "
            f"overlap {overlap_diameter_mm:g} mm"
        )
    else:
        parent_snapshot = _capture_robust_component_snapshot(
            parent_component
        )

    try:
        root_radius_mm = min(radii)
        tip_radius_mm = max(radii)
        overlap_radius_mm = 0.5 * overlap_diameter_mm
        if overlap_radius_mm >= root_radius_mm:
            raise ValueError(
                "O overlap radial é maior que o raio da raiz."
            )

        section_path_sources: list[
            tuple[
                float,
                adsk.fusion.SketchFittedSpline,
                adsk.fusion.SketchFittedSpline,
            ]
        ] = []
        section_profile_points: list[
            tuple[float, tuple[tuple[float, float, float], ...]]
        ] = []
        trailing_edge_points: list[
            tuple[
                float,
                tuple[float, float, float],
                tuple[float, float, float],
            ]
        ] = []

        stage_started = time.perf_counter()
        progress.checkpoint(
            strategy_number,
            _t("progress.stage.sections"),
            _t(
                "progress.section_count",
                current=0,
                total=len(radii),
            ),
        )
        for index, radius_mm in enumerate(radii, start=1):
            if index == 1 or index == len(radii) or index % 4 == 0:
                progress.checkpoint(
                    strategy_number,
                    _t("progress.stage.sections"),
                    _t(
                        "progress.section_count",
                        current=index,
                        total=len(radii),
                    ),
                )

            wrap_radius_mm = radius_mm
            if require_boundary_fill:
                if math.isclose(
                    radius_mm,
                    root_radius_mm,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                ):
                    wrap_radius_mm -= overlap_radius_mm
                elif math.isclose(
                    radius_mm,
                    tip_radius_mm,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                ):
                    wrap_radius_mm += overlap_radius_mm

            section = wrapped_section_geometry(
                config,
                radius_mm,
                apply_geometric_angle=apply_angle,
                profile_points_override=profile_points,
                wrap_radius_mm=wrap_radius_mm,
            )
            sketch = component.sketches.add(
                component.xYConstructionPlane
            )
            if sketch is None or not sketch.isValid:
                raise RuntimeError(
                    f"Falha ao criar a seção temporária R={radius_mm:g} mm."
                )
            sketch.name = f"Preflight section {index}"
            sketch.isComputeDeferred = True
            try:
                spline, closing_curve = _add_closed_spline_3d(
                    sketch,
                    section.points_xyz_mm,
                    section.closing_points_xyz_mm,
                    radius_mm,
                )
            finally:
                sketch.isComputeDeferred = False
            sketch.isLightBulbOn = False

            section_path_sources.append(
                (radius_mm, spline, closing_curve)
            )
            section_profile_points.append(
                (radius_mm, tuple(section.points_xyz_mm))
            )
            trailing_edge_points.append(
                (
                    radius_mm,
                    tuple(section.points_xyz_mm[0]),
                    tuple(section.points_xyz_mm[-1]),
                )
            )

        sections_seconds = time.perf_counter() - stage_started
        candidate_snapshot = _capture_robust_component_snapshot(
            component
        )
        return _RobustPreflightWorkspace(
            parent_component=parent_component,
            component=component,
            occurrence=occurrence,
            parent_snapshot=parent_snapshot,
            candidate_snapshot=candidate_snapshot,
            section_path_sources=section_path_sources,
            section_profile_points=section_profile_points,
            trailing_edge_points=trailing_edge_points,
            root_radius_mm=root_radius_mm,
            tip_radius_mm=tip_radius_mm,
            overlap_diameter_mm=float(overlap_diameter_mm),
            sections_seconds=sections_seconds,
        )
    except Exception:
        if occurrence is not None and occurrence.isValid:
            occurrence.deleteMe()
        elif parent_snapshot is not None:
            _cleanup_robust_component_candidate(
                parent_component,
                parent_snapshot,
            )
        raise


def _create_robust_workspace_section_paths(
    workspace: _RobustPreflightWorkspace,
    construction_mode: str,
) -> tuple[
    list[tuple[float, adsk.fusion.Path]],
    list[tuple[float, adsk.fusion.Path]],
]:
    """Create fresh paths for either a closed loft or two open lofts."""
    profile_paths: list[tuple[float, adsk.fusion.Path]] = []
    closing_paths: list[tuple[float, adsk.fusion.Path]] = []
    for radius_mm, spline, closing_curve in workspace.section_path_sources:
        if (
            spline is None
            or not spline.isValid
            or closing_curve is None
            or not closing_curve.isValid
        ):
            raise RuntimeError(
                "Uma curva de seção reutilizável ficou inválida em "
                f"R={radius_mm:g} mm."
            )

        if construction_mode == LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE:
            profile_paths.append(
                (
                    radius_mm,
                    _create_single_curve_section_path(
                        workspace.component,
                        spline,
                        radius_mm,
                        "aberto do contorno NACA",
                    ),
                )
            )
            closing_paths.append(
                (
                    radius_mm,
                    _create_single_curve_section_path(
                        workspace.component,
                        closing_curve,
                        radius_mm,
                        "do fechamento do bordo de fuga",
                    ),
                )
            )
        elif construction_mode == LOFT_CONSTRUCTION_CLOSED:
            profile_paths.append(
                (
                    radius_mm,
                    _create_closed_section_path(
                        workspace.component,
                        spline,
                        closing_curve,
                        radius_mm,
                    ),
                )
            )
        else:
            raise ValueError(
                f"Modo de construção de loft desconhecido: {construction_mode!r}."
            )
    return profile_paths, closing_paths


def _cleanup_robust_preflight_workspace(
    workspace: _RobustPreflightWorkspace,
) -> None:
    if workspace.occurrence is not None:
        occurrence = workspace.occurrence
        if occurrence.isValid:
            occurrence.deleteMe()
        return
    if workspace.parent_snapshot is not None:
        _cleanup_robust_component_candidate(
            workspace.parent_component,
            workspace.parent_snapshot,
        )


def _run_robust_candidate(
    workspace: _RobustPreflightWorkspace,
    config: BladeConfig,
    radii: list[float],
    apply_angle: bool,
    profile_points: int,
    construction_mode: str,
    order: str,
    rail_count: int,
    rail_placement: str,
    merge_tangent_edges: bool,
    split_surface_stitch_tolerance_mm: float,
    cylinder_axial_margin_mm: float,
    quality_check: bool,
    quality_limit_percent_chord: float,
    quality_limit_wave_angle_deg: float,
    post_fairing_margin_multiplier: float,
    require_boundary_fill: bool,
    progress: _RobustProgressController,
    strategy_number: int,
    attempt_record: dict,
    attempt_started_perf: float | None = None,
) -> _RobustCandidateOutcome:
    """Build and evaluate one candidate while reusing wrapped sections."""
    candidate_started = (
        time.perf_counter()
        if attempt_started_perf is None
        else float(attempt_started_perf)
    )
    stage_seconds: dict[str, float] = {}
    attempt_record["stage_seconds"] = stage_seconds
    attempt_record["sections_reused"] = bool(
        workspace.sections_reported
    )
    stage_seconds["sections"] = (
        0.0
        if workspace.sections_reported
        else float(workspace.sections_seconds)
    )
    workspace.sections_reported = True
    component = workspace.component

    progress.checkpoint(
        strategy_number,
        _t("progress.stage.loft"),
        _t(
            "progress.candidate_detail",
            order=order,
            rails=rail_count,
            overlap=workspace.overlap_diameter_mm,
        ),
    )

    try:
        guides = (
            LOFT_GUIDES_NONE
            if rail_count == 0
            else LOFT_GUIDES_DISTRIBUTED
        )
        resolved_rail_count = (
            0 if rail_count == 0 else max(3, rail_count)
        )
        stage_started = time.perf_counter()
        profile_loft_created = False
        trailing_edge_loft_created = False
        surface_stitch_created = False
        try:
            profile_paths, closing_paths = (
                _create_robust_workspace_section_paths(
                    workspace,
                    construction_mode,
                )
            )
            if construction_mode == LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE:
                try:
                    (
                        loft_feature,
                        _closing_loft_feature,
                        _surface_stitch_feature,
                        surface_body,
                        _,
                        _base_trim_applied,
                    ) = _create_split_trailing_edge_surface_loft(
                        component,
                        profile_paths,
                        closing_paths,
                        workspace.trailing_edge_points,
                        workspace.section_profile_points,
                        order,
                        guides,
                        resolved_rail_count,
                        rail_placement,
                        merge_tangent_edges,
                        split_surface_stitch_tolerance_mm,
                        False,
                        True,
                    )
                    profile_loft_created = True
                    trailing_edge_loft_created = True
                    surface_stitch_created = True
                except Exception as error:
                    if isinstance(error, _SplitTrailingEdgeStageError):
                        message = error.detail
                        failed_stage = error.stage
                    else:
                        message = f"{type(error).__name__}: {error}"
                        failed_stage = "loft"
                    stage_seconds["loft"] = (
                        time.perf_counter() - stage_started
                    )
                    return _RobustCandidateOutcome(
                        profile_loft_created,
                        trailing_edge_loft_created,
                        surface_stitch_created,
                        False,
                        None,
                        False,
                        (),
                        failed_stage,
                        message,
                    )
            else:
                loft_feature, _ = _create_surface_loft(
                    component,
                    profile_paths,
                    workspace.trailing_edge_points,
                    workspace.section_profile_points,
                    order,
                    guides,
                    resolved_rail_count,
                    rail_placement,
                    merge_tangent_edges,
                    True,
                )
                profile_loft_created = True
                surface_body = _feature_first_body(
                    loft_feature,
                    "o loft temporário da busca robusta",
                )
        except _RobustSearchCancelledSignal:
            raise
        except Exception as error:
            stage_seconds["loft"] = (
                time.perf_counter() - stage_started
            )
            return _RobustCandidateOutcome(
                profile_loft_created,
                trailing_edge_loft_created,
                surface_stitch_created,
                False,
                None,
                False,
                (),
                "loft",
                f"{type(error).__name__}: {error}",
            )
        stage_seconds["loft"] = time.perf_counter() - stage_started

        progress.checkpoint(
            strategy_number,
            _t("progress.stage.loft"),
            _t("progress.stage_complete"),
        )

        quality = None
        quality_detail = ""
        if quality_check:
            progress.checkpoint(
                strategy_number,
                _t("progress.stage.quality"),
                _t("progress.quality_start"),
            )
            stage_started = time.perf_counter()

            def quality_checkpoint(detail: str) -> None:
                progress.checkpoint(
                    strategy_number,
                    _t("progress.stage.quality"),
                    detail,
                )

            try:
                quality = _evaluate_loft_surface_quality(
                    surface_body,
                    config,
                    radii,
                    apply_angle,
                    profile_points,
                    quality_limit_percent_chord,
                    quality_limit_wave_angle_deg,
                    post_fairing_margin_multiplier,
                    quality_checkpoint,
                )
            except _RobustSearchCancelledSignal:
                raise
            except Exception as error:
                quality_detail = (
                    "A avaliação de qualidade falhou, mas a validade "
                    "geométrica ainda foi testada: "
                    f"{type(error).__name__}: {error}"
                )
            finally:
                stage_seconds["quality"] = (
                    time.perf_counter() - stage_started
                )

            if quality is not None and not quality.accepted:
                if quality.accepted_tolerating_fairing:
                    quality_detail = (
                        "limites estritos atendidos fora da transição da raiz; "
                        f"pior erro global={quality.max_percent_chord:.6g}% "
                        f"da corda em R={quality.worst_radius_mm:.6g} mm; "
                        f"fairing termina em R="
                        f"{quality.fairing_end_radius_mm:.6g} mm; "
                        f"margem tolerada termina em R="
                        f"{quality.root_tolerance_end_radius_mm:.6g} mm"
                    )
                else:
                    quality_detail = (
                        f"pior erro={quality.max_percent_chord:.6g}% da "
                        f"corda (limite={quality.limit_percent_chord:.6g}%); "
                        f"ângulo equivalente="
                        f"{quality.max_wave_angle_deg:.6g}° "
                        f"(limite={quality.limit_wave_angle_deg:.6g}°)"
                    )

        if not require_boundary_fill:
            return _RobustCandidateOutcome(
                True,
                trailing_edge_loft_created,
                surface_stitch_created,
                quality_check,
                quality,
                True,
                (),
                "",
                quality_detail,
            )

        progress.checkpoint(
            strategy_number,
            _t("progress.stage.boundary_fill"),
            _t(
                "progress.overlap_detail",
                overlap=workspace.overlap_diameter_mm,
            ),
        )
        stage_started = time.perf_counter()
        try:
            _, inner_body, _, outer_body = _create_limit_cylinders(
                component,
                surface_body,
                workspace.root_radius_mm,
                workspace.tip_radius_mm,
                cylinder_axial_margin_mm,
                True,
            )
            _, _, volumes = _create_boundary_fill_blade_solid(
                component,
                surface_body,
                inner_body,
                outer_body,
                workspace.root_radius_mm,
                workspace.tip_radius_mm,
            )
        except _RobustSearchCancelledSignal:
            raise
        except Exception as error:
            stage_seconds["boundary_fill"] = (
                time.perf_counter() - stage_started
            )
            return _RobustCandidateOutcome(
                True,
                trailing_edge_loft_created,
                surface_stitch_created,
                quality_check,
                quality,
                False,
                (),
                "boundary_fill",
                f"{type(error).__name__}: {error}",
            )
        stage_seconds["boundary_fill"] = (
            time.perf_counter() - stage_started
        )

        progress.checkpoint(
            strategy_number,
            _t("progress.stage.boundary_fill"),
            _t("progress.stage_complete"),
        )
        return _RobustCandidateOutcome(
            True,
            trailing_edge_loft_created,
            surface_stitch_created,
            quality_check,
            quality,
            True,
            tuple(float(value) for value in volumes),
            "",
            quality_detail,
        )
    finally:
        cleanup_started = time.perf_counter()
        try:
            _cleanup_robust_component_candidate(
                component,
                workspace.candidate_snapshot,
            )
        except Exception as cleanup_error:
            attempt_record["cleanup_success"] = False
            attempt_record["cleanup_error"] = (
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
            raise
        else:
            attempt_record["cleanup_success"] = True
            attempt_record["cleanup_error"] = ""
        finally:
            stage_seconds["cleanup"] = (
                time.perf_counter() - cleanup_started
            )
            attempt_record["elapsed_seconds"] = (
                time.perf_counter() - candidate_started
            )
            attempt_record["finished_at_utc"] = _utc_now_text()


def _robust_fallback_score(
    outcome: _RobustCandidateOutcome,
) -> tuple[float, float, float, float, float]:
    """Rank fallbacks by aerodynamic fidelity before fairing outliers."""
    quality = outcome.quality
    if quality is None:
        return (1.0, math.inf, math.inf, math.inf, math.inf)
    region = quality.aerodynamic
    if region is None:
        return (
            0.5,
            float(quality.rms_percent_chord),
            float(quality.max_percent_chord),
            float(quality.rms_wave_angle_deg),
            float(quality.max_wave_angle_deg),
        )
    return (
        0.0,
        float(region.rms_percent_chord),
        float(region.max_percent_chord),
        float(region.rms_wave_angle_deg),
        float(region.max_wave_angle_deg),
    )


def _robust_candidate_plan(
    rail_values: tuple[int, ...],
    selected_placement: str,
    preferred_merge: bool,
) -> list[tuple[str, str, int, str, bool]]:
    """Build the closed-profile automatic plan; split TE is manual-only."""
    positive = [value for value in rail_values if value > 0]
    first_two = positive[:2]
    placements = [
        selected_placement,
        LOFT_RAIL_PLACEMENT_UNIFORM_CHORD,
        LOFT_RAIL_PLACEMENT_FIRST_POINTS,
        LOFT_RAIL_PLACEMENT_VERTICES,
    ]
    unique_placements: list[str] = []
    for value in placements:
        if value not in unique_placements:
            unique_placements.append(value)

    result: list[tuple[str, str, int, str, bool]] = []

    def add(
        order: str,
        rails: int,
        placement: str,
        merge: bool,
    ) -> None:
        candidate = (
            LOFT_CONSTRUCTION_CLOSED,
            order,
            int(rails),
            placement,
            bool(merge),
        )
        if candidate not in result:
            result.append(candidate)

    add(
        LOFT_ORDER_ROOT_TO_TIP,
        0,
        selected_placement,
        preferred_merge,
    )
    for rails in positive:
        add(
            LOFT_ORDER_ROOT_TO_TIP,
            rails,
            selected_placement,
            preferred_merge,
        )

    for placement in unique_placements[1:]:
        for rails in first_two:
            add(
                LOFT_ORDER_ROOT_TO_TIP,
                rails,
                placement,
                preferred_merge,
            )

    for rails in first_two:
        add(
            LOFT_ORDER_TIP_TO_ROOT,
            rails,
            selected_placement,
            preferred_merge,
        )
    for rails in first_two:
        add(
            LOFT_ORDER_ROOT_TO_TIP,
            rails,
            selected_placement,
            not preferred_merge,
        )

    add(
        LOFT_ORDER_TIP_TO_ROOT,
        0,
        selected_placement,
        preferred_merge,
    )
    add(
        LOFT_ORDER_ROOT_TO_TIP,
        0,
        selected_placement,
        not preferred_merge,
    )
    return result[:ROBUST_MAX_EXECUTION_ATTEMPTS]


def _find_robust_strategy(
    parent_component: adsk.fusion.Component,
    config: BladeConfig,
    radii: list[float],
    apply_angle: bool,
    profile_points: int,
    maximum_rail_count: int,
    rail_placement: str,
    preferred_merge_tangent_edges: bool,
    initial_overlap_diameter_mm: float,
    split_surface_stitch_tolerance_mm: float,
    cylinder_axial_margin_mm: float,
    quality_check: bool,
    quality_limit_percent_chord: float,
    quality_limit_wave_angle_deg: float,
    post_fairing_margin_multiplier: float,
    require_boundary_fill: bool,
) -> _RobustStrategyResult:
    """Search adaptively, preserving the best valid finalizable fallback."""
    overlap_values = (
        _automatic_overlap_sequence(initial_overlap_diameter_mm)
        if require_boundary_fill
        else (initial_overlap_diameter_mm,)
    )
    rail_values = _robust_rail_counts(
        maximum_rail_count,
        profile_points,
        rail_placement,
    )
    candidate_plan = _robust_candidate_plan(
        rail_values,
        rail_placement,
        preferred_merge_tangent_edges,
    )
    total_strategy_candidates = len(candidate_plan)
    maximum_theoretical_attempts = (
        total_strategy_candidates * len(overlap_values)
    )
    maximum_execution_attempts = min(
        ROBUST_MAX_EXECUTION_ATTEMPTS,
        maximum_theoretical_attempts,
    )

    session_started = time.perf_counter()
    session = {
        "schema_version": ROBUST_LOG_SCHEMA_VERSION,
        "session_id": uuid.uuid4().hex,
        "project": {
            "name": PROJECT_NAME,
            "version": PROJECT_VERSION,
        },
        "status": "running",
        "started_at_utc": _utc_now_text(),
        "finished_at_utc": "",
        "elapsed_seconds": 0.0,
        "design": {
            "intent": _robust_design_intent_text(),
            "document": str(
                getattr(APP.activeDocument, "name", "") or ""
            ),
            "component": str(parent_component.name or ""),
        },
        "configuration": {
            "blade_config": dict(config.__dict__),
            "radii_mm": [float(value) for value in radii],
            "apply_angle": bool(apply_angle),
            "profile_points": int(profile_points),
            "rail_upper_limit": int(maximum_rail_count),
            "rail_search_values": [
                int(value) for value in rail_values
            ],
            "adaptive_candidate_plan": [
                {
                    "construction_mode": construction_mode,
                    "order": _loft_section_order_to_storage(order),
                    "rails": int(rails),
                    "rail_placement": _loft_rail_placement_to_storage(
                        placement
                    ),
                    "merge_tangent_edges": bool(merge),
                }
                for (
                    construction_mode,
                    order,
                    rails,
                    placement,
                    merge,
                ) in candidate_plan
            ],
            "rail_placement": _loft_rail_placement_to_storage(
                rail_placement
            ),
            "preferred_merge_tangent_edges": bool(
                preferred_merge_tangent_edges
            ),
            "primary_surface_construction": (
                LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE
            ),
            "split_surface_stitch_tolerance_mm": float(
                split_surface_stitch_tolerance_mm
            ),
            "overlap_values_mm": [
                float(value) for value in overlap_values
            ],
            "cylinder_axial_margin_mm": float(
                cylinder_axial_margin_mm
            ),
            "quality_check": bool(quality_check),
            "quality_limit_percent_chord": float(
                quality_limit_percent_chord
            ),
            "quality_limit_wave_angle_deg": float(
                quality_limit_wave_angle_deg
            ),
            "post_fairing_margin_multiplier": float(
                post_fairing_margin_multiplier
            ),
            "post_fairing_margin_mm": float(
                max(0.0, config.fairing_size_mm)
                * max(0.0, post_fairing_margin_multiplier)
            ),
            "quality_angle_role": "strict_after_root_transition_region",
            "fairing_quality_policy": (
                "tolerate_fairing_and_configurable_post_fairing_margin"
            ),
            "fairing_end_radius_mm": float(
                min(
                    config.tip_radius_mm,
                    config.root_radius_mm
                    + max(0.0, config.fairing_size_mm),
                )
            ),
            "root_tolerance_end_radius_mm": float(
                min(
                    config.tip_radius_mm,
                    config.root_radius_mm
                    + max(0.0, config.fairing_size_mm)
                    * (1.0 + max(0.0, post_fairing_margin_multiplier)),
                )
            ),
            "require_boundary_fill": bool(require_boundary_fill),
            "maximum_strategy_candidates": int(
                total_strategy_candidates
            ),
            "maximum_execution_attempts": int(
                maximum_execution_attempts
            ),
            "maximum_theoretical_attempts": int(
                maximum_theoretical_attempts
            ),
            "section_reuse": True,
            "self_intersection_pruning_after": 2,
        },
        "attempts": [],
        "selected_strategy": None,
        "terminal_detail": "",
    }
    compact_logs: list[str] = []
    attempt_number = 0
    current_attempt: dict | None = None
    current_attempt_appended = False
    workspaces: dict[float, _RobustPreflightWorkspace] = {}
    best_fallback = None
    best_fallback_score = None
    zero_rail_loft_created_modes: set[str] = set()
    self_intersection_streaks: dict[
        tuple[str, str, str, bool], int
    ] = {}

    def finish_session(
        status: str,
        terminal_detail: str = "",
    ) -> tuple[str, str, str]:
        session["status"] = status
        session["terminal_detail"] = terminal_detail
        session["finished_at_utc"] = _utc_now_text()
        session["elapsed_seconds"] = (
            time.perf_counter() - session_started
        )
        return _save_robust_search_log(session)

    def get_workspace(
        overlap_mm: float,
        progress: _RobustProgressController,
        strategy_number: int,
    ) -> _RobustPreflightWorkspace:
        key = float(overlap_mm)
        workspace = workspaces.get(key)
        if workspace is None:
            workspace = _create_robust_preflight_workspace(
                parent_component,
                config,
                radii,
                apply_angle,
                profile_points,
                key,
                require_boundary_fill,
                progress,
                strategy_number,
            )
            workspaces[key] = workspace
        return workspace

    def complete_attempt_record(
        attempt: dict,
        outcome: _RobustCandidateOutcome,
    ) -> str:
        attempt["loft_success"] = bool(outcome.loft_created)
        attempt["trailing_edge_loft_success"] = bool(
            outcome.trailing_edge_loft_created
        )
        attempt["surface_stitch_success"] = bool(
            outcome.surface_stitch_created
        )
        attempt["quality_checked"] = bool(outcome.quality_checked)
        attempt["quality_accepted"] = bool(
            not outcome.quality_checked
            or (
                outcome.quality is not None
                and outcome.quality.accepted
            )
        )
        attempt["boundary_fill_success"] = bool(
            outcome.boundary_fill_created
        )
        attempt["strict_accepted"] = bool(outcome.strict_accepted)
        attempt["fairing_tolerated_accepted"] = bool(
            outcome.fairing_tolerated_accepted
        )
        attempt["valid_fallback"] = bool(
            outcome.finalizable and not outcome.automatic_accepted
        )
        attempt["quality"] = _robust_quality_mapping(
            outcome.quality
        )
        attempt["cell_volumes_cm3"] = [
            float(value) for value in outcome.cell_volumes_cm3
        ]
        attempt["failed_stage"] = str(outcome.failed_stage)
        attempt["error_detail"] = str(outcome.error_detail)

        if outcome.strict_accepted:
            status = "accepted_strict"
        elif outcome.fairing_tolerated_accepted:
            status = "accepted_fairing_tolerated"
        elif outcome.finalizable:
            status = "valid_fallback"
        elif outcome.failed_stage:
            status = f"{outcome.failed_stage}_failed"
        else:
            status = "rejected"
        attempt["status"] = status

        quality_text = ""
        if outcome.quality is not None:
            quality_text = (
                f"; max={outcome.quality.max_percent_chord:.6g}%"
                f"; RMS={outcome.quality.rms_percent_chord:.6g}%"
                f"; equivalent_angle="
                f"{outcome.quality.max_wave_angle_deg:.6g}°"
            )
        if outcome.strict_accepted:
            result_text = "accepted strictly"
        elif outcome.fairing_tolerated_accepted:
            result_text = "accepted with root-fairing tolerance"
        elif outcome.finalizable:
            result_text = "valid fallback"
        else:
            result_text = f"failed at {outcome.failed_stage}"
        return (
            f"#{attempt['attempt']:02d} "
            f"construction={attempt['construction_mode']}; "
            f"order={attempt['order']}; "
            f"rails={attempt['rails']}; "
            f"placement={attempt['rail_placement']}; "
            f"merge={attempt['merge_tangent_edges']}; "
            f"overlap={attempt['overlap_diameter_mm']:g} mm; "
            f"{result_text}{quality_text}; "
            f"time={float(attempt.get('elapsed_seconds', 0.0)):.3f} s"
            + (
                f"; {_compact_robust_error_detail(outcome.error_detail)}"
                if outcome.error_detail
                else ""
            )
        )

    def selected_mapping(
        strategy_number: int,
        construction_mode: str,
        order: str,
        rail_count: int,
        placement: str,
        merge_edges: bool,
        overlap_mm: float,
        outcome: _RobustCandidateOutcome,
        used_fallback: bool,
    ) -> dict:
        return {
            "attempt": strategy_number,
            "construction_mode": construction_mode,
            "selection": (
                "best_valid_fallback"
                if used_fallback
                else (
                    "fairing_tolerated"
                    if outcome.fairing_tolerated_accepted
                    else "strict"
                )
            ),
            "order": _loft_section_order_to_storage(order),
            "order_display": order,
            "guides": (
                "none" if rail_count == 0 else "distributed"
            ),
            "rails": int(
                0 if rail_count == 0 else max(3, rail_count)
            ),
            "rail_placement": _loft_rail_placement_to_storage(
                placement
            ),
            "rail_placement_display": placement,
            "merge_tangent_edges": bool(merge_edges),
            "overlap_diameter_mm": float(overlap_mm),
            "quality": _robust_quality_mapping(outcome.quality),
            "cell_volumes_cm3": [
                float(value) for value in outcome.cell_volumes_cm3
            ],
        }

    def make_result(
        construction_mode: str,
        order: str,
        rail_count: int,
        placement: str,
        merge_edges: bool,
        overlap_mm: float,
        outcome: _RobustCandidateOutcome,
        used_fallback: bool,
        json_path: str,
        text_path: str,
        log_error: str,
    ) -> _RobustStrategyResult:
        return _RobustStrategyResult(
            construction_mode=construction_mode,
            order=order,
            guides=(
                LOFT_GUIDES_NONE
                if rail_count == 0
                else LOFT_GUIDES_DISTRIBUTED
            ),
            rail_count=(
                0 if rail_count == 0 else max(3, rail_count)
            ),
            rail_placement=placement,
            merge_tangent_edges=merge_edges,
            overlap_diameter_mm=overlap_mm,
            quality=outcome.quality,
            cell_volumes_cm3=outcome.cell_volumes_cm3,
            used_fallback=used_fallback,
            fairing_tolerated=outcome.fairing_tolerated_accepted,
            attempt_log=tuple(compact_logs),
            log_json_path=json_path,
            log_text_path=text_path,
            log_write_error=log_error,
        )

    try:
        with _RobustProgressController(
            total_strategy_candidates
        ) as progress:
            for strategy_number, candidate in enumerate(
                candidate_plan,
                start=1,
            ):
                if attempt_number >= maximum_execution_attempts:
                    break
                (
                    construction_mode,
                    order,
                    rail_count,
                    placement,
                    merge_edges,
                ) = candidate
                family = (
                    construction_mode,
                    _loft_section_order_to_storage(order),
                    _loft_rail_placement_to_storage(placement),
                    bool(merge_edges),
                )

                if (
                    rail_count == 0
                    and construction_mode in zero_rail_loft_created_modes
                ):
                    progress.checkpoint(
                        strategy_number,
                        _t("progress.stage.attempt_complete"),
                        "Zero-rail equivalent skipped after a valid "
                        "zero-rail loft was already created.",
                        completed=True,
                    )
                    continue
                if (
                    rail_count > 0
                    and self_intersection_streaks.get(family, 0) >= 2
                ):
                    progress.checkpoint(
                        strategy_number,
                        _t("progress.stage.attempt_complete"),
                        "Higher rail count skipped after two consecutive "
                        "loft self-intersections in the same family.",
                        completed=True,
                    )
                    continue

                for overlap_index, overlap_mm in enumerate(overlap_values):
                    if attempt_number >= maximum_execution_attempts:
                        break
                    attempt_started_perf = time.perf_counter()
                    attempt_started_at_utc = _utc_now_text()
                    workspace = get_workspace(
                        overlap_mm,
                        progress,
                        strategy_number,
                    )
                    attempt_number += 1
                    current_attempt_appended = False
                    current_attempt = {
                        "attempt": attempt_number,
                        "started_at_utc": attempt_started_at_utc,
                        "finished_at_utc": "",
                        "status": "running",
                        "construction_mode": construction_mode,
                        "order": _loft_section_order_to_storage(order),
                        "order_display": order,
                        "rails": int(rail_count),
                        "guides": (
                            "none"
                            if rail_count == 0
                            else "distributed"
                        ),
                        "rail_placement": (
                            _loft_rail_placement_to_storage(placement)
                        ),
                        "rail_placement_display": placement,
                        "merge_tangent_edges": bool(merge_edges),
                        "overlap_diameter_mm": float(overlap_mm),
                        "loft_success": False,
                        "trailing_edge_loft_success": False,
                        "surface_stitch_success": False,
                        "quality_checked": False,
                        "quality_accepted": False,
                        "strict_accepted": False,
                        "fairing_tolerated_accepted": False,
                        "valid_fallback": False,
                        "boundary_fill_success": False,
                        "quality": None,
                        "cell_volumes_cm3": [],
                        "failed_stage": "",
                        "error_detail": "",
                        "stage_seconds": {},
                        "sections_reused": False,
                        "cleanup_success": False,
                        "cleanup_error": "",
                        "elapsed_seconds": 0.0,
                    }

                    outcome = _run_robust_candidate(
                        workspace,
                        config,
                        radii,
                        apply_angle,
                        profile_points,
                        construction_mode,
                        order,
                        rail_count,
                        placement,
                        merge_edges,
                        split_surface_stitch_tolerance_mm,
                        cylinder_axial_margin_mm,
                        quality_check,
                        quality_limit_percent_chord,
                        quality_limit_wave_angle_deg,
                        post_fairing_margin_multiplier,
                        require_boundary_fill,
                        progress,
                        strategy_number,
                        current_attempt,
                        attempt_started_perf,
                    )
                    compact_line = complete_attempt_record(
                        current_attempt,
                        outcome,
                    )
                    session["attempts"].append(current_attempt)
                    current_attempt_appended = True
                    compact_logs.append(compact_line)

                    if (
                        rail_count == 0
                        and outcome.loft_created
                        and outcome.failed_stage not in {
                            "trailing_edge_loft",
                            "surface_stitch",
                        }
                    ):
                        zero_rail_loft_created_modes.add(
                            construction_mode
                        )

                    is_self_intersection = (
                        outcome.failed_stage == "loft"
                        and "ASM_LOFT_SURFACE_SELF_INTERSECTS"
                        in outcome.error_detail
                    )
                    if rail_count > 0:
                        if is_self_intersection:
                            self_intersection_streaks[family] = (
                                self_intersection_streaks.get(family, 0)
                                + 1
                            )
                        else:
                            self_intersection_streaks[family] = 0

                    strategy_is_complete = (
                        outcome.finalizable
                        or outcome.failed_stage == "loft"
                        or not require_boundary_fill
                        or overlap_index == len(overlap_values) - 1
                    )
                    progress.checkpoint(
                        strategy_number,
                        _t("progress.stage.attempt_complete"),
                        _robust_progress_outcome_text(
                            outcome,
                            rail_count,
                            overlap_mm,
                            float(
                                current_attempt.get(
                                    "elapsed_seconds",
                                    0.0,
                                )
                            ),
                        ),
                        completed=strategy_is_complete,
                    )

                    if outcome.strict_accepted:
                        session["selected_strategy"] = selected_mapping(
                            attempt_number,
                            construction_mode,
                            order,
                            rail_count,
                            placement,
                            merge_edges,
                            overlap_mm,
                            outcome,
                            False,
                        )
                        progress.checkpoint(
                            strategy_number,
                            _t("progress.stage.accepted"),
                            _t(
                                "progress.accepted_detail",
                                rails=rail_count,
                                overlap=overlap_mm,
                            ),
                            completed=True,
                        )
                        json_path, text_path, log_error = finish_session(
                            "success"
                        )
                        return make_result(
                            construction_mode,
                            order,
                            rail_count,
                            placement,
                            merge_edges,
                            overlap_mm,
                            outcome,
                            False,
                            json_path,
                            text_path,
                            log_error,
                        )

                    if outcome.fairing_tolerated_accepted:
                        session["selected_strategy"] = selected_mapping(
                            attempt_number,
                            construction_mode,
                            order,
                            rail_count,
                            placement,
                            merge_edges,
                            overlap_mm,
                            outcome,
                            False,
                        )
                        progress.checkpoint(
                            strategy_number,
                            _t("progress.stage.accepted"),
                            _t(
                                "progress.fairing_tolerated_detail",
                                rails=rail_count,
                                overlap=overlap_mm,
                            ),
                            completed=True,
                        )
                        detail = (
                            "Every sampled station beyond the configured root "
                            "transition met the strict quality targets. "
                            "Deviations inside the fairing and post-fairing "
                            "margin were "
                            "tolerated and reported separately."
                        )
                        json_path, text_path, log_error = finish_session(
                            "success_fairing_tolerated",
                            detail,
                        )
                        return make_result(
                            construction_mode,
                            order,
                            rail_count,
                            placement,
                            merge_edges,
                            overlap_mm,
                            outcome,
                            False,
                            json_path,
                            text_path,
                            log_error,
                        )

                    if outcome.finalizable:
                        score = _robust_fallback_score(outcome)
                        if (
                            best_fallback is None
                            or score < best_fallback_score
                        ):
                            best_fallback_score = score
                            best_fallback = (
                                attempt_number,
                                construction_mode,
                                order,
                                rail_count,
                                placement,
                                merge_edges,
                                overlap_mm,
                                outcome,
                            )
                        # More overlap cannot improve fidelity after the
                        # candidate already finalized successfully.
                        break

                    if outcome.failed_stage == "loft":
                        break
                    if not require_boundary_fill:
                        break
                    if overlap_index == len(overlap_values) - 1:
                        break

        if best_fallback is not None:
            (
                selected_attempt,
                selected_construction_mode,
                order,
                rail_count,
                placement,
                merge_edges,
                overlap_mm,
                outcome,
            ) = best_fallback
            session["selected_strategy"] = selected_mapping(
                selected_attempt,
                selected_construction_mode,
                order,
                rail_count,
                placement,
                merge_edges,
                overlap_mm,
                outcome,
                True,
            )
            detail = (
                "No candidate met every strict quality target. "
                "The best geometrically valid and finalizable candidate "
                "was selected as a fallback."
            )
            json_path, text_path, log_error = finish_session(
                "success_fallback",
                detail,
            )
            return make_result(
                selected_construction_mode,
                order,
                rail_count,
                placement,
                merge_edges,
                overlap_mm,
                outcome,
                True,
                json_path,
                text_path,
                log_error,
            )

        detail = _t(
            "result.robust_exhausted_detail",
            attempts=len(session["attempts"]),
        )
        json_path, text_path, log_error = finish_session(
            "failed",
            detail,
        )
        raise _RobustSearchTerminalError(
            detail,
            cancelled=False,
            attempt_log=tuple(compact_logs),
            log_json_path=json_path,
            log_text_path=text_path,
            log_write_error=log_error,
        )

    except _RobustSearchCancelledSignal:
        if current_attempt is not None and not current_attempt_appended:
            current_attempt["status"] = "cancelled"
            current_attempt["error_detail"] = _t(
                "progress.cancelled"
            )
            if not current_attempt.get("finished_at_utc"):
                current_attempt["finished_at_utc"] = _utc_now_text()
            session["attempts"].append(current_attempt)
            compact_logs.append(
                f"#{current_attempt['attempt']:02d} "
                f"order={current_attempt['order']}; "
                f"rails={current_attempt['rails']}; "
                f"placement={current_attempt['rail_placement']}; "
                f"merge={current_attempt['merge_tangent_edges']}; "
                f"overlap={current_attempt['overlap_diameter_mm']:g} mm; "
                "cancelled"
            )

        detail = _t(
            "result.robust_cancelled_detail",
            attempts=len(session["attempts"]),
        )
        json_path, text_path, log_error = finish_session(
            "cancelled",
            detail,
        )
        raise _RobustSearchTerminalError(
            detail,
            cancelled=True,
            attempt_log=tuple(compact_logs),
            log_json_path=json_path,
            log_text_path=text_path,
            log_write_error=log_error,
        )

    except _RobustSearchTerminalError:
        raise
    except Exception as error:
        if current_attempt is not None and not current_attempt_appended:
            current_attempt["status"] = "internal_error"
            current_attempt["error_detail"] = (
                f"{type(error).__name__}: {error}"
            )
            if not current_attempt.get("finished_at_utc"):
                current_attempt["finished_at_utc"] = _utc_now_text()
            session["attempts"].append(current_attempt)
            compact_logs.append(
                f"#{current_attempt['attempt']:02d} "
                f"order={current_attempt['order']}; "
                f"rails={current_attempt['rails']}; "
                "internal error; "
                f"{type(error).__name__}: {error}"
            )

        detail = f"{type(error).__name__}: {error}"
        json_path, text_path, log_error = finish_session(
            "error",
            detail,
        )
        raise _RobustSearchTerminalError(
            detail,
            cancelled=False,
            attempt_log=tuple(compact_logs),
            log_json_path=json_path,
            log_text_path=text_path,
            log_write_error=log_error,
        ) from error
    finally:
        cleanup_errors: list[str] = []
        for workspace in reversed(list(workspaces.values())):
            try:
                _cleanup_robust_preflight_workspace(workspace)
            except Exception as error:
                cleanup_errors.append(
                    f"{type(error).__name__}: {error}"
                )
        if cleanup_errors and sys.exc_info()[0] is None:
            raise RuntimeError(
                "A limpeza final do workspace robusto falhou: "
                + " | ".join(cleanup_errors)
            )

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
    surface_body: adsk.fusion.BRepBody,
    root_radius_mm: float,
    tip_radius_mm: float,
    distance_mm: float,
) -> tuple[
    adsk.fusion.ExtendFeature,
    adsk.fusion.ExtendFeature,
    adsk.fusion.BRepBody,
]:
    """Estende primeiro a raiz e depois a ponta, recuperando o corpo a cada etapa."""
    if surface_body is None or not surface_body.isValid:
        raise RuntimeError(
            "A superfície que será estendida não é válida."
        )

    root_feature, body_after_root = _extend_surface_end(
        component,
        surface_body,
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


def _trim_split_loft_surfaces_below_xy(
    component: adsk.fusion.Component,
    profile_body: adsk.fusion.BRepBody,
    closing_body: adsk.fusion.BRepBody,
    tolerance_mm: float = 1e-5,
) -> tuple[
    adsk.fusion.TrimFeature | None,
    adsk.fusion.BRepBody,
    adsk.fusion.BRepBody,
    bool,
]:
    """Trim both split-loft surfaces below global Z=0 in one feature.

    The Fusion kernel can fail when a very narrow stitched solid is split at
    Z=0. Trimming the two source surfaces before Stitch avoids that fragile
    topology. If neither surface extends below the plane, no Trim feature is
    needed; Boundary Fill can still use the XY plane as a tool.
    """
    if tolerance_mm < 0.0:
        raise ValueError("A tolerância do corte inferior não pode ser negativa.")

    tolerance_cm = tolerance_mm / 10.0
    source_bodies = (profile_body, closing_body)
    for body in source_bodies:
        if body is None or not body.isValid:
            raise RuntimeError(
                "O corte inferior requer as duas superfícies válidas do loft."
            )

    def extends_below_xy(body: adsk.fusion.BRepBody) -> bool:
        box = body.boundingBox
        if box is None:
            raise RuntimeError(
                "Não foi possível medir uma das superfícies antes do Trim."
            )
        return box.minPoint.z < -tolerance_cm

    profile_extends_below = extends_below_xy(profile_body)
    closing_extends_below = extends_below_xy(closing_body)
    if not (profile_extends_below or closing_extends_below):
        return None, profile_body, closing_body, False

    # Capture source areas before Trim, because Fusion can invalidate the
    # original body references as soon as the feature is committed.
    profile_area_before = _body_area_and_average_radius(profile_body)[0]
    closing_area_before = _body_area_and_average_radius(closing_body)[0]

    def select_below_cells(metrics: list[_CellMetric]) -> int:
        selected_count = 0
        for metric in metrics:
            cell_body = metric.cell.cellBody
            if cell_body is None or not cell_body.isValid:
                continue
            box = cell_body.boundingBox
            if box is None:
                continue
            center_z = 0.5 * (box.minPoint.z + box.maxPoint.z)
            entirely_below_or_on = box.maxPoint.z <= tolerance_cm
            predominantly_below = center_z < -tolerance_cm
            if entirely_below_or_on or predominantly_below:
                metric.cell.isSelected = True
                selected_count += 1
        return selected_count

    trim_feature = _add_trim_feature(
        component,
        component.xYConstructionPlane,
        select_below_cells,
        "Trim das superfícies abaixo do plano XY",
    )

    trim_results: list[adsk.fusion.BRepBody] = []
    seen: set[str] = set()

    def add_candidate(
        collection: list[adsk.fusion.BRepBody],
        body: adsk.fusion.BRepBody | None,
    ) -> None:
        if body is None or not body.isValid or body.isSolid:
            return
        try:
            token = str(body.entityToken)
        except Exception:
            token = ""
        key = token or f"python:{id(body)}"
        if key in seen:
            return
        seen.add(key)
        collection.append(body)

    for body in _feature_surface_bodies(
        trim_feature,
        "O Trim inferior das superfícies",
    ):
        add_candidate(trim_results, body)

    # If only one source surface crossed XY, the untouched source can remain
    # outside the Trim feature's result collection. Add originals only when
    # the feature itself returned fewer than the two required surfaces.
    if len(trim_results) < 2:
        if not profile_extends_below:
            add_candidate(trim_results, profile_body)
        if not closing_extends_below:
            add_candidate(trim_results, closing_body)

    if len(trim_results) < 2:
        raise RuntimeError(
            "O Trim inferior não preservou as duas superfícies necessárias "
            f"para a costura; encontrou {len(trim_results)} corpo(s)."
        )

    # Match the post-Trim bodies to their source surfaces by area. This is
    # safer than relying on collection order and also tolerates a harmless
    # extra fragment returned by the Fusion kernel.
    best_pair: tuple[
        float,
        adsk.fusion.BRepBody,
        adsk.fusion.BRepBody,
    ] | None = None
    area_epsilon = 1e-15
    for profile_candidate in trim_results:
        profile_area = _body_area_and_average_radius(profile_candidate)[0]
        for closing_candidate in trim_results:
            if closing_candidate is profile_candidate:
                continue
            closing_area = _body_area_and_average_radius(closing_candidate)[0]
            score = (
                abs(profile_area - profile_area_before)
                / max(profile_area_before, area_epsilon)
                + abs(closing_area - closing_area_before)
                / max(closing_area_before, area_epsilon)
            )
            if best_pair is None or score < best_pair[0]:
                best_pair = (
                    score,
                    profile_candidate,
                    closing_candidate,
                )

    if best_pair is None:
        raise RuntimeError(
            "Não foi possível associar as superfícies aparadas aos dois lofts."
        )

    _, trimmed_profile_body, trimmed_closing_body = best_pair
    trimmed_profile_body.name = (
        "Superfície principal aparada no plano XY"
    )
    trimmed_closing_body.name = (
        "Superfície do bordo de fuga aparada no plano XY"
    )
    return (
        trim_feature,
        trimmed_profile_body,
        trimmed_closing_body,
        True,
    )


def _stitch_surface_bodies(
    component: adsk.fusion.Component,
    bodies: tuple[adsk.fusion.BRepBody, ...],
    tolerance_mm: float,
    feature_name: str,
    body_name: str,
) -> tuple[
    adsk.fusion.StitchFeature,
    adsk.fusion.BRepBody,
]:
    """Stitch multiple surface bodies and require one connected result."""
    if tolerance_mm <= 0.0:
        raise ValueError("A tolerância de costura deve ser positiva.")
    valid_bodies = tuple(
        body for body in bodies
        if body is not None and body.isValid
    )
    if len(valid_bodies) < 2:
        raise ValueError(
            "São necessárias pelo menos duas superfícies válidas para costurar."
        )

    surfaces = adsk.core.ObjectCollection.create()
    for body in valid_bodies:
        surfaces.add(body)

    tolerance = adsk.core.ValueInput.createByReal(tolerance_mm / 10.0)
    stitches = component.features.stitchFeatures
    stitch_input = stitches.createInput(
        surfaces,
        tolerance,
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    if stitch_input is None or not stitch_input.isValid:
        raise RuntimeError(
            "Não foi possível preparar a costura das superfícies do loft."
        )

    stitch_feature = stitches.add(stitch_input)
    if stitch_feature is None or not stitch_feature.isValid:
        raise RuntimeError(
            "O Fusion não conseguiu costurar as superfícies do loft."
        )
    stitch_feature.name = feature_name

    result_bodies = _feature_surface_bodies(
        stitch_feature,
        feature_name,
    )
    if len(result_bodies) != 1:
        raise RuntimeError(
            "A costura não produziu uma única superfície conectada; "
            f"foram encontrados {len(result_bodies)} corpos."
        )
    result_body = result_bodies[0]
    shells = result_body.shells
    if shells is None or shells.count != 1:
        shell_count = 0 if shells is None else int(shells.count)
        raise RuntimeError(
            "A costura não uniu as superfícies em uma única casca; "
            f"foram encontradas {shell_count} cascas."
        )
    result_body.name = body_name
    return stitch_feature, result_body


class _SplitTrailingEdgeStageError(RuntimeError):
    """Failure of one explicit stage in the split trailing-edge workflow."""

    def __init__(self, stage: str, error: Exception):
        self.stage = str(stage)
        self.original_error = error
        self.detail = f"{type(error).__name__}: {error}"
        super().__init__(f"{self.stage}: {self.detail}")


def _create_split_trailing_edge_surface_loft(
    component: adsk.fusion.Component,
    profile_paths: list[tuple[float, adsk.fusion.Path]],
    closing_paths: list[tuple[float, adsk.fusion.Path]],
    trailing_edge_points: list[
        tuple[
            float,
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ],
    section_profile_points: list[
        tuple[
            float,
            tuple[tuple[float, float, float], ...],
        ]
    ],
    requested_order: str,
    requested_guides: str,
    distributed_rail_count: int,
    rail_placement: str,
    merge_tangent_edges: bool,
    stitch_tolerance_mm: float,
    trim_below_xy_before_stitch: bool,
    hide_created_sketches: bool,
) -> tuple[
    adsk.fusion.LoftFeature,
    adsk.fusion.LoftFeature,
    adsk.fusion.StitchFeature,
    adsk.fusion.BRepBody,
    str,
    bool,
]:
    """Loft the NACA contour and trailing-edge closure separately.

    When requested, both open surfaces are trimmed below XY before Stitch.
    This matches the robust manual workflow validated in Fusion 360.
    """
    if len(profile_paths) != len(closing_paths):
        raise ValueError(
            "Os lofts do perfil e do bordo de fuga não possuem as mesmas seções."
        )

    _manual_progress_checkpoint(
        42,
        _t("progress.manual.stage.main_loft"),
        _t("progress.manual.stage_detail_main_loft"),
    )
    try:
        profile_loft, strategy = _create_surface_loft(
            component,
            profile_paths,
            trailing_edge_points,
            section_profile_points,
            requested_order,
            requested_guides,
            distributed_rail_count,
            rail_placement,
            merge_tangent_edges,
            hide_created_sketches,
        )
    except _ManualGenerationCancelledSignal:
        raise
    except Exception as error:
        raise _SplitTrailingEdgeStageError(
            "main_surface_loft",
            error,
        ) from error
    profile_loft.name = "Loft principal — contorno NACA aberto"
    profile_body = _feature_first_body(
        profile_loft,
        "o loft principal sem o fechamento do bordo de fuga",
    )

    _manual_progress_checkpoint(
        50,
        _t("progress.manual.stage.trailing_edge"),
        _t("progress.manual.stage_detail_trailing_edge"),
    )
    try:
        closing_loft, closing_strategy = _create_surface_loft(
            component,
            closing_paths,
            trailing_edge_points,
            section_profile_points,
            requested_order,
            LOFT_GUIDES_DUAL_TRAILING_EDGE,
            3,
            LOFT_RAIL_PLACEMENT_VERTICES,
            merge_tangent_edges,
            hide_created_sketches,
        )
    except _ManualGenerationCancelledSignal:
        raise
    except Exception as error:
        raise _SplitTrailingEdgeStageError(
            "trailing_edge_loft",
            error,
        ) from error
    closing_loft.name = "Loft separado — fechamento do bordo de fuga"
    closing_body = _feature_first_body(
        closing_loft,
        "o loft separado do bordo de fuga",
    )

    base_trim_applied = False
    if trim_below_xy_before_stitch:
        _manual_progress_checkpoint(
            57,
            _t("progress.manual.stage.trim"),
            _t("progress.manual.stage_detail_trim"),
        )
        try:
            (
                _base_trim_feature,
                profile_body,
                closing_body,
                base_trim_applied,
            ) = _trim_split_loft_surfaces_below_xy(
                component,
                profile_body,
                closing_body,
            )
        except _ManualGenerationCancelledSignal:
            raise
        except Exception as error:
            raise _SplitTrailingEdgeStageError(
                "surface_trim",
                error,
            ) from error

    _manual_progress_checkpoint(
        62,
        _t("progress.manual.stage.stitch"),
        _t("progress.manual.stage_detail_stitch"),
    )
    try:
        stitch_feature, stitched_body = _stitch_surface_bodies(
            component,
            (profile_body, closing_body),
            stitch_tolerance_mm,
            "Costura do loft principal com o bordo de fuga",
            "Superfície completa da pá — bordo de fuga separado",
        )
    except _ManualGenerationCancelledSignal:
        raise
    except Exception as error:
        raise _SplitTrailingEdgeStageError(
            "surface_stitch",
            error,
        ) from error
    return (
        profile_loft,
        closing_loft,
        stitch_feature,
        stitched_body,
        (
            "split trailing edge; main surface: "
            + strategy
            + "; trailing-edge surface: "
            + closing_strategy
            + " (two rails through the exact trailing-edge vertices)"
            + (
                "; both surfaces trimmed below XY before Stitch"
                if base_trim_applied
                else (
                    "; XY trim checked before Stitch; no material below plane"
                    if trim_below_xy_before_stitch
                    else ""
                )
            )
        ),
        base_trim_applied,
    )


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



@dataclass(frozen=True)
class _BoundaryFillCellMetric:
    cell: object
    volume_cm3: float


def _create_boundary_fill_blade_solid(
    component: adsk.fusion.Component,
    blade_surface_body: adsk.fusion.BRepBody,
    inner_cylinder_body: adsk.fusion.BRepBody,
    outer_cylinder_body: adsk.fusion.BRepBody,
    root_radius_mm: float,
    tip_radius_mm: float,
    include_xy_plane: bool = False,
) -> tuple[
    adsk.fusion.BoundaryFillFeature,
    adsk.fusion.BRepBody,
    list[float],
]:
    """Create the blade solid and keep the positive-volume largest cell.

    Boundary Fill performs a partial compute when its input is created. Every
    failure path before ``add`` must therefore call ``cancel``.
    """
    tools = adsk.core.ObjectCollection.create()
    tools.add(blade_surface_body)
    tools.add(inner_cylinder_body)
    tools.add(outer_cylinder_body)
    if include_xy_plane:
        tools.add(component.xYConstructionPlane)

    features = component.features.boundaryFillFeatures
    boundary_input = features.createInput(
        tools,
        adsk.fusion.FeatureOperations.NewBodyFeatureOperation,
    )
    if boundary_input is None or not boundary_input.isValid:
        raise RuntimeError(
            "Não foi possível preparar o Boundary Fill da pá."
        )

    add_called = False
    try:
        cells = boundary_input.bRepCells
        if cells is None or cells.count < 1:
            raise RuntimeError(
                "O Boundary Fill não encontrou células fechadas."
            )

        metrics: list[_BoundaryFillCellMetric] = []
        for index in range(cells.count):
            cell = cells.item(index)
            if cell is None or not cell.isValid:
                continue
            body = cell.cellBody
            if body is None or not body.isValid:
                continue
            volume_cm3 = float(body.volume)
            if volume_cm3 > 1e-18:
                metrics.append(
                    _BoundaryFillCellMetric(
                        cell=cell,
                        volume_cm3=volume_cm3,
                    )
                )

        if not metrics:
            raise RuntimeError(
                "O Boundary Fill encontrou células, mas nenhuma possui "
                "volume positivo."
            )

        metrics.sort(
            key=lambda item: item.volume_cm3,
            reverse=True,
        )
        metrics[0].cell.isSelected = True
        boundary_input.isRemoveTools = True

        # add() completes the internal Boundary Fill transaction even if it
        # returns null; do not call cancel after this point.
        add_called = True
        feature = features.add(boundary_input)
        if feature is None or not feature.isValid:
            raise RuntimeError(
                "O Fusion não conseguiu concluir o Boundary Fill."
            )
    finally:
        if not add_called and boundary_input.isValid:
            try:
                boundary_input.cancel()
            except Exception:
                pass

    feature.name = _t(
        "feature.boundary_fill",
        count=len(metrics),
    )
    bodies = _feature_surface_bodies(
        feature,
        "O Boundary Fill",
    )
    solid_bodies = [
        body for body in bodies
        if body is not None and body.isValid and body.isSolid
    ]
    if len(solid_bodies) != 1:
        raise RuntimeError(
            "O Boundary Fill deveria produzir exatamente um sólido, mas "
            f"produziu {len(solid_bodies)}."
        )

    result_body = solid_bodies[0]
    result_body.name = _t(
        "feature.solid_blade",
        root=root_radius_mm,
        tip=tip_radius_mm,
    )
    return (
        feature,
        result_body,
        [metric.volume_cm3 for metric in metrics],
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


def _body_identity_key(body: adsk.fusion.BRepBody) -> str:
    try:
        token = str(body.entityToken or "")
    except Exception:
        token = ""
    return token or f"python:{id(body)}"


def _unique_valid_solid_bodies(
    bodies: list[adsk.fusion.BRepBody],
) -> list[adsk.fusion.BRepBody]:
    unique: list[adsk.fusion.BRepBody] = []
    seen: set[str] = set()

    for body in bodies:
        if not body or not body.isValid or not body.isSolid:
            continue
        key = _body_identity_key(body)
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

    try:
        split_feature = split_features.add(split_input)
    except RuntimeError as error:
        # The BRep bounding box can extend a tiny amount below Z=0 even when
        # the exact body only touches the plane or lies completely above it.
        # In that case Fusion rejects Split Body with
        # SPLIT_TARGET_TOOL_NOT_INTERSECT. There is no lower region to remove,
        # so treating the cut as an already-clear base is both safe and allows
        # the remaining assembly stages to continue.
        if "SPLIT_TARGET_TOOL_NOT_INTERSECT" in str(error):
            blade_body.name = _t("feature.blade_base_clear")
            return blade_body, None, False
        raise

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


def _spinner_profile_point(
    radius_mm: float,
    local_axial_mm: float,
    base_z_mm: float,
) -> adsk.core.Point3D:
    """Cria um ponto do spinner com a base apoiada no topo do hub.

    ``local_axial_mm`` é medido a partir da base do spinner. A coordenada
    global resulta de ``base_z_mm + local_axial_mm``. O helper separado evita
    alterar `_spinner_point`, que também é usado pelo anel aerodinâmico e já
    recebe coordenadas axiais globais.
    """
    return _spinner_point(
        radius_mm,
        base_z_mm + local_axial_mm,
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
            _spinner_profile_point(
                radius_mm * x,
                length_mm * (1.0 - x * x),
                hub_length_mm,
            )
        )

    spline = sketch.sketchCurves.sketchFittedSplines.add(fit_points)
    if not spline:
        raise RuntimeError("Não foi possível criar a parábola do spinner.")

    origin = _spinner_profile_point(0.0, 0.0, hub_length_mm)
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

    top = _spinner_profile_point(0.0, length_mm, hub_length_mm)
    tangent = _spinner_profile_point(
        nose_radius_mm * math.cos(start_angle),
        reduced_height_mm + nose_radius_mm * math.sin(start_angle),
        hub_length_mm,
    )
    nose_mid_angle = 0.5 * (0.5 * math.pi + start_angle)
    nose_mid = _spinner_profile_point(
        nose_radius_mm * math.cos(nose_mid_angle),
        reduced_height_mm + nose_radius_mm * math.sin(nose_mid_angle),
        hub_length_mm,
    )
    main_mid_angle = 0.5 * start_angle
    main_mid = _spinner_profile_point(
        main_radius_mm * math.cos(main_mid_angle) - center_offset_mm,
        main_radius_mm * math.sin(main_mid_angle),
        hub_length_mm,
    )
    base = _spinner_profile_point(
        0.5 * diameter_mm,
        0.0,
        hub_length_mm,
    )
    origin = _spinner_profile_point(0.0, 0.0, hub_length_mm)

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


def _apply_final_propeller_orientation(
    component: adsk.fusion.Component,
    bodies: list[adsk.fusion.BRepBody],
    primary_body: adsk.fusion.BRepBody,
    orientation: str,
    root_length_mm: float,
) -> tuple[
    adsk.fusion.BRepBody,
    adsk.fusion.MoveFeature | None,
    tuple[adsk.fusion.BRepBody, ...],
]:
    """Apply the rigid final transform used by demo_boatpropblades().

    The OpenSCAD ``hublen`` argument maps to this add-in's ``Root_Length``.
    Therefore ``translate([0,0,Root_Length]) rotate([180,0,0])`` maps each
    point to ``(x, -y, Root_Length-z)``. A 180-degree rotation about an
    X-parallel axis at Z=Root_Length/2 is exactly equivalent and can be
    committed as one native Move feature.
    """
    normalized = _normalize_propeller_orientation(orientation)
    valid_bodies = _unique_valid_solid_bodies(list(bodies))
    if normalized == PROPELLER_ORIENTATION_STANDARD:
        return primary_body, None, tuple(valid_bodies)
    if normalized != PROPELLER_ORIENTATION_FLIPPED_180:
        raise ValueError(f"Orientação final desconhecida: {orientation!r}.")
    if root_length_mm <= 0.0:
        raise ValueError(
            "Root_Length deve ser positivo para aplicar a orientação invertida."
        )
    if not valid_bodies:
        raise RuntimeError(
            "Não há corpos sólidos válidos para aplicar a orientação final."
        )

    entities = adsk.core.ObjectCollection.create()
    for body in valid_bodies:
        entities.add(body)

    transform = adsk.core.Matrix3D.create()
    axis = adsk.core.Vector3D.create(1.0, 0.0, 0.0)
    axis_origin = adsk.core.Point3D.create(
        0.0,
        0.0,
        root_length_mm / 20.0,
    )
    if not transform.setToRotation(math.pi, axis, axis_origin):
        raise RuntimeError(
            "Não foi possível preparar a matriz da orientação final."
        )

    move_features = component.features.moveFeatures
    move_input = move_features.createInput2(entities)
    if not move_input:
        raise RuntimeError(
            "Não foi possível preparar a transformação final da hélice."
        )
    if not move_input.defineAsFreeMove(transform):
        raise RuntimeError(
            "Não foi possível definir a transformação final da hélice."
        )

    move_feature = move_features.add(move_input)
    if not move_feature:
        raise RuntimeError(
            "O Fusion não conseguiu aplicar a orientação final da hélice."
        )
    move_feature.name = _t(
        "feature.final_orientation_flipped",
        root_length=root_length_mm,
    )

    moved_bodies = _unique_valid_solid_bodies(
        _feature_surface_bodies(
            move_feature,
            "A orientação final",
        )
    )
    if not moved_bodies:
        raise RuntimeError(
            "A orientação final não retornou corpos sólidos válidos."
        )

    primary_name = str(getattr(primary_body, "name", "") or "")
    moved_primary = next(
        (
            body for body in moved_bodies
            if primary_name and str(body.name or "") == primary_name
        ),
        max(moved_bodies, key=_body_volume_or_zero),
    )
    return moved_primary, move_feature, tuple(moved_bodies)


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
    final_orientation_applied: bool
    final_orientation_mode: str
    final_orientation_angle_deg: float
    final_orientation_body_count: int
    final_orientation_error: str
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
    root_length_mm: float,
    hole_diameter_mm: float,
    prop_z_offset_mm: float,
    propeller_orientation: str,
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
    final_orientation_applied = False
    final_orientation_angle_deg = 0.0
    final_orientation_error = ""
    final_orientation_body_count = 0

    if (
        _normalize_propeller_orientation(propeller_orientation)
        == PROPELLER_ORIENTATION_FLIPPED_180
    ):
        _manual_progress_checkpoint(
            89,
            _t("progress.manual.stage.orientation"),
            _t("progress.manual.stage_detail_orientation"),
        )
        try:
            blade_body, orientation_feature, moved_bodies = (
                _apply_final_propeller_orientation(
                    component,
                    [blade_body],
                    blade_body,
                    propeller_orientation,
                    root_length_mm,
                )
            )
            final_orientation_applied = orientation_feature is not None
            final_orientation_angle_deg = 180.0
            final_orientation_body_count = len(moved_bodies)
        except _ManualGenerationCancelledSignal:
            raise
        except Exception as error:
            final_orientation_error = f"{type(error).__name__}: {error}"

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

    orientation_bodies: list[adsk.fusion.BRepBody] = list(blade_bodies)

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
        orientation_bodies = [final_body]

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
            orientation_bodies.append(ring_body)
            join_candidates = (
                [final_body]
                if assembly_is_single_body
                else list(blade_bodies)
            )
            consumed_orientation_keys = {
                _body_identity_key(body)
                for body in [ring_body] + join_candidates
            }
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
                orientation_bodies = [final_body] + [
                    body
                    for body in orientation_bodies
                    if (
                        body
                        and body.isValid
                        and _body_identity_key(body)
                        not in consumed_orientation_keys
                    )
                ]
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
            orientation_bodies.append(spinner_body)
            join_candidates = [final_body] if assembly_is_single_body else list(blade_bodies)
            consumed_orientation_keys = {
                _body_identity_key(body)
                for body in [spinner_body] + join_candidates
            }
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
                orientation_bodies = [final_body] + [
                    body
                    for body in orientation_bodies
                    if (
                        body
                        and body.isValid
                        and _body_identity_key(body)
                        not in consumed_orientation_keys
                    )
                ]
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
            orientation_bodies.append(spinner_body)
            join_candidates = [final_body] if assembly_is_single_body else list(blade_bodies)
            consumed_orientation_keys = {
                _body_identity_key(body)
                for body in [spinner_body] + join_candidates
            }
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
                orientation_bodies = [final_body] + [
                    body
                    for body in orientation_bodies
                    if (
                        body
                        and body.isValid
                        and _body_identity_key(body)
                        not in consumed_orientation_keys
                    )
                ]
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
            orientation_bodies.append(hoop_body)
            join_candidates = [final_body] if assembly_is_single_body else list(blade_bodies)
            consumed_orientation_keys = {
                _body_identity_key(body)
                for body in [hoop_body] + join_candidates
            }
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
                orientation_bodies = [final_body] + [
                    body
                    for body in orientation_bodies
                    if (
                        body
                        and body.isValid
                        and _body_identity_key(body)
                        not in consumed_orientation_keys
                    )
                ]
            except Exception as error:
                hoop_error = f"{type(error).__name__}: {error}"
        except Exception as error:
            hoop_error = f"{type(error).__name__}: {error}"

    if final_orientation_body_count == 0 and final_orientation_applied:
        final_orientation_body_count = 1

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
        final_orientation_applied=final_orientation_applied,
        final_orientation_mode=_propeller_orientation_to_storage(
            propeller_orientation
        ),
        final_orientation_angle_deg=final_orientation_angle_deg,
        final_orientation_body_count=final_orientation_body_count,
        final_orientation_error=final_orientation_error,
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
    loft_construction_mode: str,
    loft_section_order: str,
    loft_guide_rails: str,
    loft_distributed_rail_count: int,
    loft_rail_placement: str,
    loft_merge_tangent_edges: bool,
    finalization_method: str,
    boundary_overlap_diameter_mm: float,
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
    propeller_orientation: str,
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
    section_path_sources: list[
        tuple[
            float,
            adsk.fusion.SketchFittedSpline,
            adsk.fusion.SketchFittedSpline,
        ]
    ] = []
    section_profile_points: list[
        tuple[
            float,
            tuple[tuple[float, float, float], ...],
        ]
    ] = []
    trailing_edge_points: list[
        tuple[
            float,
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ] = []

    root_radius_mm = min(radii)
    tip_radius_mm = max(radii)
    use_boundary_fill = (
        finalization_method == FINALIZATION_BOUNDARY_FILL
    )
    apply_boundary_overlap = (
        use_boundary_fill
        and finalize_solid
        and create_surface_loft
    )
    cylinders_required = (
        create_limit_cylinders
        or (use_boundary_fill and finalize_solid)
    )

    boundary_overlap_radius_mm = 0.0
    if apply_boundary_overlap:
        if boundary_overlap_diameter_mm <= 0.0:
            raise ValueError(
                "Boundary_Fill_Diameter_Overlap_mm deve ser positivo."
            )
        boundary_overlap_radius_mm = 0.5 * boundary_overlap_diameter_mm
        if boundary_overlap_radius_mm >= root_radius_mm:
            raise ValueError(
                "O overlap radial do Boundary Fill deve ser menor que o "
                "raio do hub."
            )

    _manual_progress_checkpoint(
        12,
        _t("progress.manual.stage.sections"),
        _t("progress.manual.section_detail", current=0, total=len(radii)),
    )

    root_probe = wrapped_section_geometry(
        config,
        root_radius_mm,
        apply_geometric_angle=apply_angle,
        profile_points_override=profile_points,
        wrap_radius_mm=(
            root_radius_mm - boundary_overlap_radius_mm
            if apply_boundary_overlap
            else root_radius_mm
        ),
    )
    root_wrap_min_deg = root_probe.angular_min_deg
    root_wrap_max_deg = root_probe.angular_max_deg

    created = 0
    for index, radius_mm in enumerate(radii, start=1):
        wrap_radius_mm = radius_mm
        if apply_boundary_overlap:
            if math.isclose(
                radius_mm, root_radius_mm, rel_tol=0.0, abs_tol=1e-9
            ):
                wrap_radius_mm -= boundary_overlap_radius_mm
            elif math.isclose(
                radius_mm, tip_radius_mm, rel_tol=0.0, abs_tol=1e-9
            ):
                wrap_radius_mm += boundary_overlap_radius_mm

        if math.isclose(
            radius_mm, root_radius_mm, rel_tol=0.0, abs_tol=1e-9
        ):
            section = root_probe
        else:
            section = wrapped_section_geometry(
                config,
                radius_mm,
                apply_geometric_angle=apply_angle,
                profile_points_override=profile_points,
                wrap_radius_mm=wrap_radius_mm,
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
            spline, closing_curve = _add_closed_spline_3d(
                sketch,
                section.points_xyz_mm,
                section.closing_points_xyz_mm,
                radius_mm,
            )
        finally:
            sketch.isComputeDeferred = False

        section_path_sources.append(
            (radius_mm, spline, closing_curve)
        )
        section_profile_points.append(
            (
                radius_mm,
                tuple(section.points_xyz_mm),
            )
        )
        trailing_edge_points.append(
            (
                radius_mm,
                tuple(section.points_xyz_mm[0]),
                tuple(section.points_xyz_mm[-1]),
            )
        )
        sketch.isLightBulbOn = not hide_created_sketches
        created += 1
        if created == len(radii) or created == 1 or created % 5 == 0:
            progress_value = 12 + round(23 * created / max(1, len(radii)))
            _manual_progress_checkpoint(
                progress_value,
                _t("progress.manual.stage.sections"),
                _t(
                    "progress.manual.section_detail",
                    current=created,
                    total=len(radii),
                ),
            )

    if not create_surface_loft:
        return GenerationResult(
            section_count=created,
            section_mode=MODE_WRAPPED,
            surface_loft_requested=False,
            root_wrap_min_deg=root_wrap_min_deg,
            root_wrap_max_deg=root_wrap_max_deg,
            boundary_overlap_diameter_mm=(
                boundary_overlap_diameter_mm
                if apply_boundary_overlap
                else 0.0
            ),
            extension_requested=(
                extend_surface_ends and not use_boundary_fill
            ),
            extension_error=(
                "A extensão requer que o loft de superfície seja criado."
                if (extend_surface_ends and not use_boundary_fill)
                else ""
            ),
            cylinders_requested=cylinders_required,
            cylinders_error=(
                "Os cilindros requerem que o loft seja criado."
                if cylinders_required else ""
            ),
            finalization_requested=finalize_solid,
            finalization_method=finalization_method,
            finalization_error=(
                "A finalização sólida requer que o loft seja criado."
                if finalize_solid else ""
            ),
        )

    split_pretrim_requested = False
    split_base_trim_applied = False

    _manual_progress_checkpoint(
        38,
        _t("progress.manual.stage.loft_prepare"),
        _t("progress.manual.stage_detail_paths"),
    )

    try:
        profile_paths: list[tuple[float, adsk.fusion.Path]] = []
        closing_paths: list[tuple[float, adsk.fusion.Path]] = []
        for radius_mm, spline, closing_curve in section_path_sources:
            if loft_construction_mode == LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE:
                profile_paths.append(
                    (
                        radius_mm,
                        _create_single_curve_section_path(
                            component,
                            spline,
                            radius_mm,
                            "aberto do contorno NACA",
                        ),
                    )
                )
                closing_paths.append(
                    (
                        radius_mm,
                        _create_single_curve_section_path(
                            component,
                            closing_curve,
                            radius_mm,
                            "do fechamento do bordo de fuga",
                        ),
                    )
                )
            else:
                profile_paths.append(
                    (
                        radius_mm,
                        _create_closed_section_path(
                            component,
                            spline,
                            closing_curve,
                            radius_mm,
                        ),
                    )
                )

        if loft_construction_mode == LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE:
            split_pretrim_requested = bool(
                cut_below_hub_base and use_boundary_fill
            )
            (
                loft_feature,
                _closing_loft_feature,
                _split_stitch_feature,
                current_body,
                loft_strategy,
                split_base_trim_applied,
            ) = _create_split_trailing_edge_surface_loft(
                component,
                profile_paths,
                closing_paths,
                trailing_edge_points,
                section_profile_points,
                loft_section_order,
                loft_guide_rails,
                loft_distributed_rail_count,
                loft_rail_placement,
                loft_merge_tangent_edges,
                stitch_tolerance_mm,
                split_pretrim_requested,
                hide_created_sketches,
            )
        else:
            loft_feature, loft_strategy = _create_surface_loft(
                component,
                profile_paths,
                trailing_edge_points,
                section_profile_points,
                loft_section_order,
                loft_guide_rails,
                loft_distributed_rail_count,
                loft_rail_placement,
                loft_merge_tangent_edges,
                hide_created_sketches,
            )
            current_body = _feature_first_body(
                loft_feature,
                "o loft de superfície",
            )
    except _ManualGenerationCancelledSignal:
        raise
    except Exception as error:
        split_stage = (
            error.stage
            if isinstance(error, _SplitTrailingEdgeStageError)
            else ""
        )
        base_error = (
            error.detail
            if isinstance(error, _SplitTrailingEdgeStageError)
            else f"{type(error).__name__}: {error}"
        )
        preserved_note = (
            "\n\nOs esboços, lofts, rails e costuras criados antes "
            "da falha foram preservados na linha do tempo para "
            "inspeção manual."
            if loft_construction_mode
            == LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE
            else ""
        )
        detailed_error = base_error + preserved_note
        return GenerationResult(
            section_count=created,
            section_mode=MODE_WRAPPED,
            surface_loft_requested=True,
            surface_loft_created=False,
            surface_loft_error=detailed_error,
            surface_loft_failed_stage=split_stage,
            main_surface_loft_error=(
                detailed_error if split_stage == "main_surface_loft" else ""
            ),
            trailing_edge_loft_error=(
                detailed_error if split_stage == "trailing_edge_loft" else ""
            ),
            surface_trim_error=(
                detailed_error if split_stage == "surface_trim" else ""
            ),
            surface_stitch_error=(
                detailed_error if split_stage == "surface_stitch" else ""
            ),
            root_wrap_min_deg=root_wrap_min_deg,
            root_wrap_max_deg=root_wrap_max_deg,
            boundary_overlap_diameter_mm=(
                boundary_overlap_diameter_mm
                if apply_boundary_overlap
                else 0.0
            ),
            extension_requested=(
                extend_surface_ends and not use_boundary_fill
            ),
            cylinders_requested=(
                create_limit_cylinders
                or (use_boundary_fill and finalize_solid)
            ),
            finalization_requested=finalize_solid,
            finalization_method=finalization_method,
        )

    _manual_progress_checkpoint(
        65,
        _t("progress.manual.stage.loft_complete"),
        loft_strategy,
    )

    root_extension_created = False
    tip_extension_created = False
    extension_error = ""

    if extend_surface_ends and not use_boundary_fill:
        try:
            _, _, current_body = _extend_both_surface_ends(
                component,
                current_body,
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

    if cylinders_required:
        _manual_progress_checkpoint(
            70,
            _t("progress.manual.stage.cylinders"),
            _t("progress.manual.stage_detail_cylinders"),
        )
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

    boundary_fill_created = False
    boundary_fill_cell_count = 0
    boundary_fill_selected_volume_cm3 = 0.0
    boundary_fill_second_volume_cm3 = 0.0
    cylinder_caps_created = False
    blade_trimmed = split_base_trim_applied
    stitch_created = False
    solid_created = False
    solid_body_name = ""
    finalization_error = ""
    single_blade_body = None

    if finalize_solid:
        if use_boundary_fill:
            prerequisites_ok = (
                inner_cylinder_created
                and outer_cylinder_created
                and inner_cylinder_body is not None
                and outer_cylinder_body is not None
            )
            if not prerequisites_ok:
                finalization_error = (
                    "O Boundary Fill requer o loft e os dois cilindros "
                    "limite nominais."
                )
            else:
                _manual_progress_checkpoint(
                    78,
                    _t("progress.manual.stage.boundary_fill"),
                    _t("progress.manual.stage_detail_boundary_fill"),
                )
                try:
                    (
                        _,
                        final_body,
                        cell_volumes_cm3,
                    ) = _create_boundary_fill_blade_solid(
                        component,
                        current_body,
                        inner_cylinder_body,
                        outer_cylinder_body,
                        root_radius_mm,
                        tip_radius_mm,
                        include_xy_plane=split_pretrim_requested,
                    )
                    boundary_fill_created = True
                    boundary_fill_cell_count = len(cell_volumes_cm3)
                    boundary_fill_selected_volume_cm3 = (
                        cell_volumes_cm3[0]
                    )
                    boundary_fill_second_volume_cm3 = (
                        cell_volumes_cm3[1]
                        if len(cell_volumes_cm3) > 1
                        else 0.0
                    )
                    solid_created = bool(final_body.isSolid)
                    solid_body_name = final_body.name
                    if solid_created:
                        single_blade_body = final_body
                    else:
                        finalization_error = (
                            "O Boundary Fill foi criado, mas o corpo "
                            "selecionado não é sólido."
                        )
                except Exception as error:
                    finalization_error = f"{type(error).__name__}: {error}"
        else:
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
                    "A finalização legada requer as duas extensões e os "
                    "dois cilindros."
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
                            "A costura foi criada, mas o resultado ainda é "
                            "uma superfície aberta. Verifique as bordas livres."
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
        or (
            _normalize_propeller_orientation(propeller_orientation)
            != PROPELLER_ORIENTATION_STANDARD
        )
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
    final_orientation_requested = (
        _normalize_propeller_orientation(propeller_orientation)
        != PROPELLER_ORIENTATION_STANDARD
    )
    final_orientation_applied = False
    final_orientation_mode = _propeller_orientation_to_storage(
        propeller_orientation
    )
    final_orientation_angle_deg = 0.0
    final_orientation_body_count = 0
    final_orientation_error = ""
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
        _manual_progress_checkpoint(
            88,
            _t("progress.manual.stage.assembly"),
            _t("progress.manual.stage_detail_assembly"),
        )
        if single_blade_body is None:
            assembly_error = (
                "A montagem final requer que a finalização tenha "
                "produzido uma pá sólida."
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
                    config.root_length_mm,
                    hole_diameter_mm,
                    prop_z_offset_mm,
                    propeller_orientation,
                    (
                        cut_below_hub_base
                        and not split_pretrim_requested
                    ),
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
                underside_cut_completed = (
                    split_pretrim_requested
                    or assembly.underside_cut_completed
                )
                underside_cut_applied = (
                    split_base_trim_applied
                    or assembly.underside_cut_applied
                )
                z_offset_applied = assembly.z_offset_applied
                blade_pattern_created = assembly.blade_pattern_created
                blade_body_count = len(assembly.blade_bodies)
                hub_created = assembly.hub_created
                hub_joined = assembly.hub_joined
                final_propeller_created = assembly.final_propeller_created
                final_propeller_name = assembly.final_propeller_name
                final_orientation_applied = (
                    assembly.final_orientation_applied
                )
                final_orientation_mode = assembly.final_orientation_mode
                final_orientation_angle_deg = (
                    assembly.final_orientation_angle_deg
                )
                final_orientation_body_count = (
                    assembly.final_orientation_body_count
                )
                final_orientation_error = assembly.final_orientation_error
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

    _manual_progress_checkpoint(
        98,
        _t("progress.manual.stage.complete"),
        _t("progress.manual.stage_detail_complete"),
    )

    return GenerationResult(
        section_count=created,
        section_mode=MODE_WRAPPED,
        surface_loft_requested=True,
        surface_loft_created=True,
        surface_loft_name=loft_feature.name,
        surface_loft_strategy=loft_strategy,
        root_wrap_min_deg=root_wrap_min_deg,
        root_wrap_max_deg=root_wrap_max_deg,
        boundary_overlap_diameter_mm=(
            boundary_overlap_diameter_mm
            if apply_boundary_overlap
            else 0.0
        ),
        extension_requested=(
            extend_surface_ends and not use_boundary_fill
        ),
        root_extension_created=root_extension_created,
        tip_extension_created=tip_extension_created,
        extension_error=extension_error,
        cylinders_requested=cylinders_required,
        inner_cylinder_created=inner_cylinder_created,
        outer_cylinder_created=outer_cylinder_created,
        inner_cylinder_name=inner_cylinder_name,
        outer_cylinder_name=outer_cylinder_name,
        cylinders_error=cylinders_error,
        finalization_requested=finalize_solid,
        finalization_method=finalization_method,
        boundary_fill_created=boundary_fill_created,
        boundary_fill_cell_count=boundary_fill_cell_count,
        boundary_fill_selected_volume_cm3=(
            boundary_fill_selected_volume_cm3
        ),
        boundary_fill_second_volume_cm3=(
            boundary_fill_second_volume_cm3
        ),
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
        final_orientation_requested=final_orientation_requested,
        final_orientation_applied=final_orientation_applied,
        final_orientation_mode=final_orientation_mode,
        final_orientation_angle_deg=final_orientation_angle_deg,
        final_orientation_body_count=final_orientation_body_count,
        final_orientation_error=final_orientation_error,
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
    loft_construction_mode: str,
    loft_section_order: str,
    loft_guide_rails: str,
    loft_distributed_rail_count: int,
    loft_rail_placement: str,
    loft_merge_tangent_edges: bool,
    loft_quality_check: bool,
    loft_quality_max_deviation_percent: float,
    loft_quality_max_wave_angle_deg: float,
    loft_quality_post_fairing_margin_multiplier: float,
    finalization_method: str,
    boundary_overlap_diameter_mm: float,
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
    propeller_orientation: str,
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
    if loft_quality_check:
        if loft_quality_max_deviation_percent <= 0.0:
            raise ValueError(
                "Loft_Quality_Max_Deviation_Percent deve ser positivo."
            )
        if loft_quality_max_wave_angle_deg <= 0.0:
            raise ValueError(
                "Loft_Quality_Max_Wave_Angle_Deg deve ser positivo."
            )
        if loft_quality_post_fairing_margin_multiplier < 0.0:
            raise ValueError(
                "Loft_Quality_Post_Fairing_Margin_Multiplier não pode "
                "ser negativo."
            )

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
        robust_result = None
        resolved_loft_construction_mode = loft_construction_mode
        resolved_loft_section_order = loft_section_order
        resolved_loft_guide_rails = loft_guide_rails
        resolved_loft_rail_count = loft_distributed_rail_count
        resolved_loft_rail_placement = loft_rail_placement
        resolved_loft_merge_tangent_edges = loft_merge_tangent_edges
        resolved_boundary_overlap_diameter_mm = (
            boundary_overlap_diameter_mm
        )

        robust_requested = (
            create_surface_loft
            and loft_section_order == LOFT_ORDER_AUTOMATIC
        )
        if robust_requested:
            require_boundary_fill = (
                finalize_solid
                and finalization_method == FINALIZATION_BOUNDARY_FILL
            )
            try:
                robust_result = _find_robust_strategy(
                    component,
                    config,
                    radii,
                    apply_angle,
                    profile_points,
                    loft_distributed_rail_count,
                    loft_rail_placement,
                    loft_merge_tangent_edges,
                    boundary_overlap_diameter_mm,
                    stitch_tolerance_mm,
                    cylinder_axial_margin_mm,
                    loft_quality_check,
                    loft_quality_max_deviation_percent,
                    loft_quality_max_wave_angle_deg,
                    loft_quality_post_fairing_margin_multiplier,
                    require_boundary_fill,
                )
            except _RobustSearchTerminalError as error:
                return GenerationResult(
                    section_count=0,
                    section_mode=MODE_WRAPPED,
                    component_name=component_name,
                    surface_loft_requested=True,
                    surface_loft_created=False,
                    surface_loft_error=error.summary,
                    robust_search_requested=True,
                    robust_search_succeeded=False,
                    robust_search_cancelled=error.cancelled,
                    robust_attempt_count=error.attempt_count,
                    robust_attempt_log="\n".join(
                        error.attempt_log
                    ),
                    robust_log_json_path=error.log_json_path,
                    robust_log_text_path=error.log_text_path,
                    robust_log_write_error=error.log_write_error,
                    loft_quality_checked=loft_quality_check,
                    loft_quality_limit_percent_chord=(
                        loft_quality_max_deviation_percent
                    ),
                    loft_quality_limit_wave_angle_deg=(
                        loft_quality_max_wave_angle_deg
                    ),
                    finalization_requested=finalize_solid,
                    finalization_method=finalization_method,
                )
            except Exception as error:
                return GenerationResult(
                    section_count=0,
                    section_mode=MODE_WRAPPED,
                    component_name=component_name,
                    surface_loft_requested=True,
                    surface_loft_created=False,
                    surface_loft_error=(
                        f"{type(error).__name__}: {error}"
                    ),
                    robust_search_requested=True,
                    robust_search_succeeded=False,
                    robust_attempt_count=0,
                    robust_attempt_log="",
                    loft_quality_checked=loft_quality_check,
                    loft_quality_limit_percent_chord=(
                        loft_quality_max_deviation_percent
                    ),
                    loft_quality_limit_wave_angle_deg=(
                        loft_quality_max_wave_angle_deg
                    ),
                    finalization_requested=finalize_solid,
                    finalization_method=finalization_method,
                )

            resolved_loft_construction_mode = (
                robust_result.construction_mode
            )
            resolved_loft_section_order = robust_result.order
            resolved_loft_guide_rails = robust_result.guides
            resolved_loft_rail_count = robust_result.rail_count
            resolved_loft_rail_placement = robust_result.rail_placement
            resolved_loft_merge_tangent_edges = (
                robust_result.merge_tangent_edges
            )
            resolved_boundary_overlap_diameter_mm = (
                robust_result.overlap_diameter_mm
            )

        wrapped_result = _generate_wrapped_sections(
            component,
            config,
            radii,
            apply_angle,
            profile_points,
            create_surface_loft,
            resolved_loft_construction_mode,
            resolved_loft_section_order,
            resolved_loft_guide_rails,
            resolved_loft_rail_count,
            resolved_loft_rail_placement,
            resolved_loft_merge_tangent_edges,
            finalization_method,
            resolved_boundary_overlap_diameter_mm,
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
            propeller_orientation,
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
        if robust_result is None:
            return replace(
                wrapped_result,
                component_name=component_name,
            )

        quality = robust_result.quality
        return replace(
            wrapped_result,
            component_name=component_name,
            robust_search_requested=True,
            robust_search_succeeded=True,
            robust_search_cancelled=False,
            robust_search_used_fallback=robust_result.used_fallback,
            robust_search_fairing_tolerated=(
                robust_result.fairing_tolerated
            ),
            robust_attempt_count=len(robust_result.attempt_log),
            robust_attempt_log="\n".join(robust_result.attempt_log),
            robust_log_json_path=robust_result.log_json_path,
            robust_log_text_path=robust_result.log_text_path,
            robust_log_write_error=robust_result.log_write_error,
            loft_quality_checked=quality is not None,
            loft_quality_accepted=(
                quality.accepted if quality is not None else True
            ),
            loft_quality_sample_count=(
                quality.sample_count if quality is not None else 0
            ),
            loft_quality_rms_error_mm=(
                quality.rms_error_mm if quality is not None else 0.0
            ),
            loft_quality_max_error_mm=(
                quality.max_error_mm if quality is not None else 0.0
            ),
            loft_quality_rms_percent_chord=(
                quality.rms_percent_chord if quality is not None else 0.0
            ),
            loft_quality_max_percent_chord=(
                quality.max_percent_chord if quality is not None else 0.0
            ),
            loft_quality_limit_percent_chord=(
                quality.limit_percent_chord
                if quality is not None
                else loft_quality_max_deviation_percent
            ),
            loft_quality_rms_wave_angle_deg=(
                quality.rms_wave_angle_deg if quality is not None else 0.0
            ),
            loft_quality_max_wave_angle_deg=(
                quality.max_wave_angle_deg if quality is not None else 0.0
            ),
            loft_quality_limit_wave_angle_deg=(
                quality.limit_wave_angle_deg
                if quality is not None
                else loft_quality_max_wave_angle_deg
            ),
            loft_quality_worst_radius_mm=(
                quality.worst_radius_mm if quality is not None else 0.0
            ),
            loft_quality_worst_contour_index=(
                quality.worst_contour_index if quality is not None else -1
            ),
            loft_quality_worst_wave_radius_mm=(
                quality.worst_wave_radius_mm if quality is not None else 0.0
            ),
            loft_quality_worst_wave_contour_index=(
                quality.worst_wave_contour_index
                if quality is not None
                else -1
            ),
            loft_quality_fairing_end_radius_mm=(
                quality.fairing_end_radius_mm
                if quality is not None
                else 0.0
            ),
            loft_quality_post_fairing_margin_multiplier=(
                quality.post_fairing_margin_multiplier
                if quality is not None
                else loft_quality_post_fairing_margin_multiplier
            ),
            loft_quality_post_fairing_margin_mm=(
                quality.post_fairing_margin_mm
                if quality is not None
                else 0.0
            ),
            loft_quality_root_tolerance_end_radius_mm=(
                quality.root_tolerance_end_radius_mm
                if quality is not None
                else 0.0
            ),
            loft_quality_post_fairing_sample_count=(
                quality.post_fairing.sample_count
                if quality is not None and quality.post_fairing is not None
                else 0
            ),
            loft_quality_post_fairing_max_percent_chord=(
                quality.post_fairing.max_percent_chord
                if quality is not None and quality.post_fairing is not None
                else 0.0
            ),
            loft_quality_post_fairing_max_wave_angle_deg=(
                quality.post_fairing.max_wave_angle_deg
                if quality is not None and quality.post_fairing is not None
                else 0.0
            ),
            loft_quality_aerodynamic_sample_count=(
                quality.aerodynamic.sample_count
                if quality is not None and quality.aerodynamic is not None
                else 0
            ),
            loft_quality_aerodynamic_max_percent_chord=(
                quality.aerodynamic.max_percent_chord
                if quality is not None and quality.aerodynamic is not None
                else 0.0
            ),
            loft_quality_aerodynamic_max_wave_angle_deg=(
                quality.aerodynamic.max_wave_angle_deg
                if quality is not None and quality.aerodynamic is not None
                else 0.0
            ),
            loft_quality_fairing_sample_count=(
                quality.fairing.sample_count
                if quality is not None and quality.fairing is not None
                else 0
            ),
            loft_quality_fairing_max_percent_chord=(
                quality.fairing.max_percent_chord
                if quality is not None and quality.fairing is not None
                else 0.0
            ),
            loft_quality_fairing_max_wave_angle_deg=(
                quality.fairing.max_wave_angle_deg
                if quality is not None and quality.fairing is not None
                else 0.0
            ),
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


def _finalize_manual_log_display(
    path: str,
    displayed_message: str,
    timeline: dict,
) -> None:
    """Add the exact post-commit message and timeline outcome to a manual log."""
    if not path or not os.path.isfile(path):
        return
    try:
        payload = _read_config_object(path, os.path.basename(path))
        payload["displayed_message"] = str(displayed_message or "")
        payload["timeline"] = _json_safe_value(timeline)
        _write_json_atomically(path, payload)
    except Exception:
        # A diagnostics enrichment failure must never hide the generation result.
        pass


def _queue_generation_result(
    request: dict,
    message: str,
    incomplete: bool,
    manual_log_path: str = "",
) -> None:
    """Store one result until the current transacted execution is committed."""
    global _pending_timeline_run
    _pending_timeline_run = {
        "request": request,
        "message": message,
        "incomplete": bool(incomplete),
        "manual_log_path": str(manual_log_path or ""),
    }


def _flush_pending_generation_result() -> bool:
    """Group the just-created timeline items and show the queued result."""
    global _pending_timeline_run

    pending = _pending_timeline_run
    _pending_timeline_run = None
    if not pending:
        return False

    group_name, group_error, skipped_message = (
        _create_timeline_group_for_run(
            pending["request"],
            incomplete=pending["incomplete"],
        )
    )

    if group_name:
        timeline_note = _t(
            "error.timeline_partial_group"
            if pending["incomplete"]
            else "result.timeline_group",
            name=group_name,
        )
    elif skipped_message:
        timeline_note = skipped_message
    else:
        timeline_note = _t(
            "result.timeline_group_fail",
            detail=group_error,
        )

    final_message = pending["message"] + "\n\n" + timeline_note
    _finalize_manual_log_display(
        pending.get("manual_log_path", ""),
        final_message,
        {
            "group_name": group_name,
            "error": group_error,
            "skipped_message": skipped_message,
            "note": timeline_note,
            "incomplete": bool(pending["incomplete"]),
        },
    )
    UI.messageBox(final_message)
    return True


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
        manual_log_session = None
        manual_log_started_perf = time.perf_counter()
        manual_log_path = ""
        manual_log_error = ""
        manual_progress = None
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
            loft_construction_mode = _loft_construction_mode_from_display(
                _selected_dropdown_name(
                    inputs,
                    "loftConstructionMode",
                )
            )
            loft_section_order = _selected_dropdown_name(
                inputs,
                "loftSectionOrder",
            )
            loft_guide_rails = _selected_dropdown_name(
                inputs,
                "loftGuideRails",
            )

            if (
                section_mode == MODE_WRAPPED
                and loft_section_order != LOFT_ORDER_AUTOMATIC
            ):
                manual_progress = _ManualProgressController()
                manual_progress.show()
                _manual_progress_checkpoint(
                    3,
                    _t("progress.manual.stage.validate"),
                    _t("progress.manual.stage_detail_validate"),
                )
                manual_log_session = _manual_generation_log_session(
                    {},
                    [],
                    section_mode,
                    loft_construction_mode,
                    loft_section_order,
                    loft_guide_rails,
                )
                manual_log_session["input_snapshot"] = (
                    _command_inputs_snapshot(inputs)
                )

            loft_distributed_rail_count = (
                _normalize_distributed_rail_count(
                    _required_command_input(
                        inputs,
                        "loftDistributedRailCount",
                    ).value
                )
            )
            loft_rail_placement = _selected_dropdown_name(
                inputs,
                "loftRailPlacement",
            )
            loft_merge_tangent_edges = bool(
                _required_command_input(
                    inputs,
                    "loftMergeTangentEdges",
                ).value
            )
            loft_quality_check = bool(
                _required_command_input(
                    inputs,
                    "loftQualityCheck",
                ).value
            )
            loft_quality_max_deviation_percent = _parse_float_text(
                _string_input_value(
                    inputs,
                    "loftQualityMaxDeviationPercent",
                ),
                "Loft_Quality_Max_Deviation_Percent",
            )
            loft_quality_max_wave_angle_deg = _parse_float_text(
                _string_input_value(
                    inputs,
                    "loftQualityMaxWaveAngleDeg",
                ),
                "Loft_Quality_Max_Wave_Angle_Deg",
            )
            loft_quality_post_fairing_margin_multiplier = _parse_float_text(
                _string_input_value(
                    inputs,
                    "loftQualityPostFairingMarginMultiplier",
                ),
                "Loft_Quality_Post_Fairing_Margin_Multiplier",
            )
            finalization_method = _selected_dropdown_name(
                inputs,
                "finalizationMethod",
            )
            boundary_overlap_diameter_mm = _value_input_mm(
                inputs,
                "boundaryOverlapDiameter",
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
            current_config = _save_current_config(inputs)
            _manual_progress_checkpoint(
                8,
                _t("progress.manual.stage.prepare"),
                _t(
                    "progress.manual.stage_detail_prepare",
                    count=len(resolved_radii),
                ),
            )

            if manual_log_session is not None:
                manual_log_session["parameters"] = _json_safe_value(
                    current_config
                )
                manual_log_session["resolved_radii_mm"] = [
                    float(value) for value in resolved_radii
                ]

            timeline_group_request = _capture_timeline_group_request()

            result = _generate_sections(
                resolved_radii,
                apply_angle,
                section_mode,
                profile_points,
                create_surface_loft,
                loft_construction_mode,
                loft_section_order,
                loft_guide_rails,
                loft_distributed_rail_count,
                loft_rail_placement,
                loft_merge_tangent_edges,
                loft_quality_check,
                loft_quality_max_deviation_percent,
                loft_quality_max_wave_angle_deg,
                loft_quality_post_fairing_margin_multiplier,
                finalization_method,
                boundary_overlap_diameter_mm,
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
                assembly_parameters["propeller_orientation"],
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
                robust_failed_before_geometry = (
                    result.robust_search_requested
                    and not result.robust_search_succeeded
                    and result.section_count == 0
                )
                if robust_failed_before_geometry:
                    lines = [_t("result.robust_preflight_no_geometry")]
                else:
                    lines = [_t("result.wrapped")]
                    lines.append(
                        _t(
                            "result.root_wrap_range",
                            min_angle=result.root_wrap_min_deg,
                            max_angle=result.root_wrap_max_deg,
                        )
                    )
                if result.boundary_overlap_diameter_mm > 0.0:
                    lines.append(
                        _t(
                            "result.boundary_overlap",
                            diameter=(
                                result.boundary_overlap_diameter_mm
                            ),
                        )
                    )

                if result.surface_loft_created:
                    lines.append(
                        _t(
                            "result.loft_success",
                            name=result.surface_loft_name,
                        )
                    )
                    if result.surface_loft_strategy:
                        lines.append(
                            _t(
                                "result.loft_strategy",
                                strategy=result.surface_loft_strategy,
                            )
                        )
                    if result.robust_search_succeeded:
                        lines.append(
                            _t(
                                (
                                    "result.robust_search_fallback"
                                    if result.robust_search_used_fallback
                                    else (
                                        "result.robust_search_fairing_tolerated"
                                        if result.robust_search_fairing_tolerated
                                        else "result.robust_search_success"
                                    )
                                ),
                                attempts=result.robust_attempt_count,
                            )
                        )
                    if result.loft_quality_checked:
                        lines.append(
                            _t(
                                "result.loft_quality",
                                samples=result.loft_quality_sample_count,
                                maximum=result.loft_quality_max_error_mm,
                                maximum_percent=(
                                    result.loft_quality_max_percent_chord
                                ),
                                rms=result.loft_quality_rms_error_mm,
                                rms_percent=(
                                    result.loft_quality_rms_percent_chord
                                ),
                                limit=(
                                    result.loft_quality_limit_percent_chord
                                ),
                                wave=(
                                    result.loft_quality_max_wave_angle_deg
                                ),
                                wave_rms=(
                                    result.loft_quality_rms_wave_angle_deg
                                ),
                                wave_limit=(
                                    result.loft_quality_limit_wave_angle_deg
                                ),
                                radius=result.loft_quality_worst_radius_mm,
                                contour=(
                                    result.loft_quality_worst_contour_index
                                ),
                                wave_radius=(
                                    result.loft_quality_worst_wave_radius_mm
                                ),
                                wave_contour=(
                                    result.loft_quality_worst_wave_contour_index
                                ),
                            )
                        )
                        if result.robust_search_fairing_tolerated:
                            lines.append(
                                _t(
                                    "result.loft_quality_regions",
                                    fairing_end=(
                                        result.loft_quality_fairing_end_radius_mm
                                    ),
                                    margin_multiplier=(
                                        result
                                        .loft_quality_post_fairing_margin_multiplier
                                    ),
                                    margin_mm=(
                                        result.loft_quality_post_fairing_margin_mm
                                    ),
                                    tolerance_end=(
                                        result.loft_quality_root_tolerance_end_radius_mm
                                    ),
                                    post_samples=(
                                        result.loft_quality_post_fairing_sample_count
                                    ),
                                    post_max=(
                                        result
                                        .loft_quality_post_fairing_max_percent_chord
                                    ),
                                    post_angle=(
                                        result
                                        .loft_quality_post_fairing_max_wave_angle_deg
                                    ),
                                    aerodynamic_samples=(
                                        result.loft_quality_aerodynamic_sample_count
                                    ),
                                    aerodynamic_max=(
                                        result.loft_quality_aerodynamic_max_percent_chord
                                    ),
                                    aerodynamic_angle=(
                                        result.loft_quality_aerodynamic_max_wave_angle_deg
                                    ),
                                    fairing_samples=(
                                        result.loft_quality_fairing_sample_count
                                    ),
                                    fairing_max=(
                                        result.loft_quality_fairing_max_percent_chord
                                    ),
                                    fairing_angle=(
                                        result.loft_quality_fairing_max_wave_angle_deg
                                    ),
                                )
                            )
                elif result.surface_loft_requested:
                    if (
                        robust_failed_before_geometry
                        and result.robust_search_cancelled
                    ):
                        lines.append(
                            _t(
                                "result.robust_search_cancelled",
                                attempts=result.robust_attempt_count,
                            )
                        )
                    elif robust_failed_before_geometry:
                        lines.append(
                            _t(
                                "result.robust_preflight_error",
                                detail=result.surface_loft_error,
                            )
                        )
                        lines.append(
                            _t(
                                "result.robust_search_fail",
                                attempts=result.robust_attempt_count,
                            )
                        )
                    else:
                        split_stage_labels = {
                            "main_surface_loft": _t(
                                "loft_stage.main_surface_loft"
                            ),
                            "trailing_edge_loft": _t(
                                "loft_stage.trailing_edge_loft"
                            ),
                            "surface_trim": _t("loft_stage.surface_trim"),
                            "surface_stitch": _t(
                                "loft_stage.surface_stitch"
                            ),
                        }
                        if result.surface_loft_failed_stage:
                            lines.append(
                                _t(
                                    "result.loft_component_fail",
                                    stage=split_stage_labels.get(
                                        result.surface_loft_failed_stage,
                                        result.surface_loft_failed_stage,
                                    ),
                                    detail=result.surface_loft_error,
                                )
                            )
                        else:
                            lines.append(
                                _t(
                                    "result.loft_fail",
                                    detail=result.surface_loft_error,
                                )
                            )
                else:
                    lines.append(_t("result.loft_disabled"))

                if result.robust_search_requested:
                    if result.robust_attempt_log:
                        lines.append(
                            _t(
                                "result.robust_candidate_summary",
                                summary=_robust_attempt_message_text(
                                    result.robust_attempt_log
                                ),
                            )
                        )
                    if (
                        result.robust_log_json_path
                        or result.robust_log_text_path
                    ):
                        lines.append(
                            _t(
                                "result.robust_log_saved",
                                json_path=(
                                    result.robust_log_json_path
                                    or _t("common.not_available")
                                ),
                                text_path=(
                                    result.robust_log_text_path
                                    or _t("common.not_available")
                                ),
                            )
                        )
                    if result.robust_log_write_error:
                        lines.append(
                            _t(
                                "result.robust_log_write_error",
                                detail=result.robust_log_write_error,
                            )
                        )

                if result.extension_requested and not robust_failed_before_geometry:
                    if result.root_extension_created and result.tip_extension_created:
                        lines.append(_t("result.extend_success", distance=extension_distance_mm))
                    else:
                        lines.append(_t(
                            "result.extend_fail",
                            detail=result.extension_error or _t("common.detail_unavailable"),
                        ))

                if result.cylinders_requested and not robust_failed_before_geometry:
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

                if result.finalization_requested and not robust_failed_before_geometry:
                    if (
                        result.finalization_method
                        == FINALIZATION_BOUNDARY_FILL
                    ):
                        if result.solid_created:
                            lines.append(
                                _t(
                                    "result.boundary_fill_success",
                                    name=result.solid_body_name,
                                    count=result.boundary_fill_cell_count,
                                    selected=(
                                        result.boundary_fill_selected_volume_cm3
                                    ),
                                    second=(
                                        result.boundary_fill_second_volume_cm3
                                    ),
                                )
                            )
                        else:
                            lines.append(
                                _t(
                                    "result.boundary_fill_fail",
                                    detail=result.finalization_error,
                                )
                            )
                    elif result.solid_created:
                        lines.append(
                            _t(
                                "result.finalize_success",
                                name=result.solid_body_name,
                            )
                        )
                    elif result.stitch_created:
                        lines.append(
                            _t(
                                "result.finalize_open",
                                detail=result.finalization_error,
                            )
                        )
                    else:
                        lines.append(
                            _t(
                                "result.finalize_fail",
                                detail=result.finalization_error,
                            )
                        )

                if result.assembly_requested and not robust_failed_before_geometry:
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
                        if result.final_orientation_requested:
                            if result.final_orientation_applied:
                                assembly_lines.append(
                                    _t(
                                        "result.final_orientation_applied",
                                        count=(
                                            result.final_orientation_body_count
                                        ),
                                    )
                                )
                            elif result.final_orientation_error:
                                assembly_lines.append(
                                    _t(
                                        "result.final_orientation_fail",
                                        detail=(
                                            result.final_orientation_error
                                        ),
                                    )
                                )
                        lines.append("\n".join(assembly_lines))

                detail = "\n\n".join(lines)

            visibility_note = (
                ""
                if (
                    section_mode == MODE_WRAPPED
                    and robust_failed_before_geometry
                )
                else (
                    _t("result.hidden")
                    if hide_created_sketches
                    else _t("result.visible")
                )
            )
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

            result_header = (
                _t(
                    "result.robust_preflight_header",
                    component=result.component_name,
                )
                if (
                    result.robust_search_requested
                    and not result.robust_search_succeeded
                    and result.section_count == 0
                )
                else _t(
                    "result.header",
                    count=result.section_count,
                    component=result.component_name,
                )
            )
            result_message = (
                result_header
                + "\n\n" + distribution_note
                + "\n\n" + detail
                + (
                    "\n\n" + visibility_note
                    if visibility_note
                    else ""
                )
            )
            if manual_log_session is not None:
                manual_log_path, manual_log_error = (
                    _save_manual_generation_log(
                        manual_log_session,
                        manual_log_started_perf,
                        (
                            "completed_with_errors"
                            if _manual_result_has_errors(result)
                            else "success"
                        ),
                        result=result,
                        display_result_text=result_message,
                    )
                )

            if manual_log_path:
                result_message += "\n\n" + _t(
                    "result.manual_log_saved",
                    path=manual_log_path,
                )
            elif manual_log_error:
                result_message += "\n\n" + _t(
                    "result.manual_log_error",
                    detail=manual_log_error,
                )

            if (
                section_mode == MODE_WRAPPED
                and robust_failed_before_geometry
            ):
                UI.messageBox(result_message)
                timeline_group_request = None
            else:
                _queue_generation_result(
                    timeline_group_request,
                    result_message,
                    incomplete=(
                        section_mode == MODE_WRAPPED
                        and result.surface_loft_requested
                        and not result.surface_loft_created
                    ),
                    manual_log_path=manual_log_path,
                )
        except _ManualGenerationCancelledSignal as error:
            error_detail = str(error)
            error_message = _t(
                "result.manual_generation_cancelled",
                detail=error_detail,
            )
            if manual_log_session is not None:
                manual_log_path, manual_log_error = (
                    _save_manual_generation_log(
                        manual_log_session,
                        manual_log_started_perf,
                        "cancelled",
                        error_detail=error_detail,
                        display_error_text=error_message,
                    )
                )
            if manual_log_path:
                error_message += "\n\n" + _t(
                    "result.manual_log_saved",
                    path=manual_log_path,
                )
            elif manual_log_error:
                error_message += "\n\n" + _t(
                    "result.manual_log_error",
                    detail=manual_log_error,
                )
            if timeline_group_request is not None:
                _queue_generation_result(
                    timeline_group_request,
                    error_message,
                    incomplete=True,
                    manual_log_path=manual_log_path,
                )
            else:
                _finalize_manual_log_display(
                    manual_log_path,
                    error_message,
                    {
                        "group_name": "",
                        "error": "",
                        "skipped_message": _t(
                            "result.timeline_group_not_started"
                        ),
                        "note": _t("result.timeline_group_not_started"),
                        "incomplete": True,
                    },
                )
                UI.messageBox(error_message)
        except Exception:
            error_detail = traceback.format_exc()
            if manual_log_session is not None:
                manual_log_path, manual_log_error = (
                    _save_manual_generation_log(
                        manual_log_session,
                        manual_log_started_perf,
                        "failed",
                        error_detail=error_detail,
                        display_error_text=_t(
                            "error.generate",
                            detail=error_detail,
                        ),
                    )
                )
            error_message = _t(
                "error.generate",
                detail=error_detail,
            )
            if manual_log_path:
                error_message += "\n\n" + _t(
                    "result.manual_log_saved",
                    path=manual_log_path,
                )
            elif manual_log_error:
                error_message += "\n\n" + _t(
                    "result.manual_log_error",
                    detail=manual_log_error,
                )

            # If geometry creation had already begun, delay the error message
            # too. The transaction will then be committed before any partial
            # features are inspected and grouped.
            if timeline_group_request is not None:
                _queue_generation_result(
                    timeline_group_request,
                    error_message,
                    incomplete=True,
                    manual_log_path=manual_log_path,
                )
            else:
                _finalize_manual_log_display(
                    manual_log_path,
                    error_message,
                    {
                        "group_name": "",
                        "error": "",
                        "skipped_message": _t(
                            "result.timeline_group_not_started"
                        ),
                        "note": _t("result.timeline_group_not_started"),
                        "incomplete": True,
                    },
                )
                UI.messageBox(error_message)
        finally:
            if manual_progress is not None:
                manual_progress.close()


class CommandTerminatedHandler(
    adsk.core.ApplicationCommandEventHandler
):
    def notify(self, args: adsk.core.ApplicationCommandEventArgs):
        global _pending_timeline_run

        try:
            if args.commandId != CMD_ID:
                return
            # The native Generate/OK button ends the command. Only now is
            # the command transaction committed, so timeline grouping and
            # visibility changes created here persist normally.
            _flush_pending_generation_result()
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

            if changed_input.id == "sampleConfiguration":
                _update_sample_description(command_inputs)
            elif changed_input.id == "loadSample":
                try:
                    sample = _load_selected_sample(command_inputs)
                    UI.messageBox(
                        _t(
                            "sample.loaded_message",
                            name=sample.display_name,
                        )
                    )
                except Exception:
                    UI.messageBox(
                        _t(
                            "sample.error_load",
                            detail=traceback.format_exc(),
                        )
                    )
            elif changed_input.id == "saveSample":
                try:
                    name, path = _save_current_as_user_sample(
                        command_inputs
                    )
                    UI.messageBox(
                        _t(
                            "sample.saved_message",
                            name=name,
                            path=path,
                        )
                    )
                except Exception:
                    UI.messageBox(
                        _t(
                            "sample.error_save",
                            detail=traceback.format_exc(),
                        )
                    )
            elif changed_input.id == "radiusDistributionMode":
                _update_radius_distribution_inputs(command_inputs)
            elif changed_input.id == "createSurfaceLoft":
                _update_loft_inputs(command_inputs)
                _update_finalization_inputs(command_inputs)
            elif changed_input.id in (
                "loftGuideRails",
                "loftSectionOrder",
                "loftConstructionMode",
                "loftQualityCheck",
            ):
                _update_loft_inputs(command_inputs)
                _update_finalization_inputs(command_inputs)
            elif changed_input.id in (
                "finalizationMethod",
                "finalizeSolid",
                "createLimitCylinders",
                "extendSurfaceEnds",
            ):
                _update_finalization_inputs(command_inputs)
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
        global _sample_catalog
        global _sample_discovery_errors

        try:
            _pending_timeline_run = None
            raw_config = _load_raw_config()
            _set_dialog_config_base(raw_config)
            (
                _sample_catalog,
                _sample_discovery_errors,
            ) = _discover_sample_configurations()

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
            loft_construction_mode_default = (
                _normalize_loft_construction_mode(
                    raw_config.get(
                        "Loft_Construction_Mode",
                        "split_trailing_edge",
                    )
                )
            )
            loft_section_order_default = _normalize_loft_section_order(
                raw_config.get("Loft_Section_Order", "root_to_tip")
            )
            loft_guide_rails_default = _normalize_loft_guides(
                raw_config.get("Loft_Guide_Rails", "none")
            )
            loft_distributed_rail_count_default = (
                _normalize_distributed_rail_count(
                    raw_config.get(
                        "Loft_Distributed_Rail_Count",
                        9,
                    )
                )
            )
            loft_rail_placement_default = (
                _normalize_loft_rail_placement(
                    raw_config.get(
                        "Loft_Distributed_Rail_Placement"
                    ),
                    raw_config.get(
                        "Loft_Distributed_Rails_Use_TE_Vertices",
                        False,
                    ),
                )
            )
            loft_merge_tangent_edges_default = bool(
                raw_config.get("Loft_Merge_Tangent_Edges", True)
            )
            loft_quality_check_default = bool(
                raw_config.get("Loft_Quality_Check", True)
            )
            loft_quality_max_deviation_percent_default = float(
                raw_config.get(
                    "Loft_Quality_Max_Deviation_Percent",
                    0.1,
                )
            )
            loft_quality_max_wave_angle_deg_default = float(
                raw_config.get(
                    "Loft_Quality_Max_Wave_Angle_Deg",
                    0.2,
                )
            )
            loft_quality_post_fairing_margin_multiplier_default = float(
                raw_config.get(
                    "Loft_Quality_Post_Fairing_Margin_Multiplier",
                    2.0,
                )
            )
            finalization_method_default = _normalize_finalization_method(
                raw_config.get(
                    "Blade_Finalization_Method",
                    "boundary_fill",
                )
            )
            boundary_overlap_diameter_default_mm = float(
                raw_config.get(
                    "Boundary_Fill_Diameter_Overlap_mm",
                    0.1,
                )
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
                raw_config.get("Stitch_Tolerance_mm", 0.1)
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
            propeller_orientation_default = (
                _normalize_propeller_orientation(
                    raw_config.get("Propeller_Orientation", "standard")
                )
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
            command.isOKButtonVisible = True
            command.okButtonText = _t("ui.generate")
            command.isExecutedWhenPreEmpted = False
            command.setDialogInitialSize(
                DIALOG_INITIAL_WIDTH,
                DIALOG_INITIAL_HEIGHT,
            )
            command.setDialogMinimumSize(
                DIALOG_MINIMUM_WIDTH,
                DIALOG_MINIMUM_HEIGHT,
            )

            inputs = command.commandInputs

            # ---------------------------------------------------------------
            # Group: automatically discovered sample JSON configurations
            # ---------------------------------------------------------------
            samples_group = inputs.addGroupCommandInput(
                "samplesGroup",
                _t("ui.group.samples"),
            )
            samples_group.isExpanded = True
            sample_inputs = samples_group.children

            sample_dropdown = sample_inputs.addDropDownCommandInput(
                "sampleConfiguration",
                _t("ui.sample_configuration"),
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            sample_dropdown.tooltip = _t("ui.samples_scan_tooltip")
            sample_dropdown.tooltipDescription = (
                _sample_tooltip_description()
            )

            if _sample_catalog:
                for index, menu_label in enumerate(_sample_catalog):
                    sample_dropdown.listItems.add(
                        menu_label,
                        index == 0,
                    )
            else:
                sample_dropdown.listItems.add(
                    _t("sample.menu_empty"),
                    True,
                )
                sample_dropdown.isEnabled = False

            load_sample_button = sample_inputs.addBoolValueInput(
                "loadSample",
                _t("ui.load_sample"),
                False,
                "",
                False,
            )
            load_sample_button.isFullWidth = True
            load_sample_button.isEnabled = bool(_sample_catalog)
            load_sample_button.tooltip = _t("ui.load_sample_tooltip")
            load_sample_button.tooltipDescription = _t(
                "ui.load_sample_tooltip_description"
            )

            sample_name_input = sample_inputs.addStringValueInput(
                "newSampleName",
                _t("ui.new_sample_name"),
                "",
            )
            sample_name_input.tooltip = _t(
                "ui.new_sample_name_tooltip"
            )

            save_sample_button = sample_inputs.addBoolValueInput(
                "saveSample",
                _t("ui.save_sample"),
                False,
                "",
                False,
            )
            save_sample_button.isFullWidth = True
            save_sample_button.tooltip = _t(
                "ui.save_sample_tooltip"
            )
            save_sample_button.tooltipDescription = _t(
                "ui.save_sample_tooltip_description",
                path=USER_SAMPLES_DIRECTORY,
            )

            sample_description = sample_inputs.addTextBoxCommandInput(
                "sampleDescription",
                "",
                "",
                3,
                True,
            )
            sample_description.isFullWidth = True
            _update_sample_description(inputs)

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

            orientation_input = geometry_inputs.addDropDownCommandInput(
                "propellerOrientation",
                _t("ui.propeller_orientation"),
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            orientation_input.listItems.add(
                PROPELLER_ORIENTATION_STANDARD_DISPLAY,
                propeller_orientation_default
                == PROPELLER_ORIENTATION_STANDARD,
            )
            orientation_input.listItems.add(
                PROPELLER_ORIENTATION_FLIPPED_180_DISPLAY,
                propeller_orientation_default
                == PROPELLER_ORIENTATION_FLIPPED_180,
            )
            orientation_input.tooltip = _t(
                "ui.propeller_orientation_tooltip"
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

            loft_construction_input = (
                operations_inputs.addDropDownCommandInput(
                    "loftConstructionMode",
                    _t("ui.loft_construction_mode"),
                    adsk.core.DropDownStyles.TextListDropDownStyle,
                )
            )
            for mode, display in (
                (
                    LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE,
                    LOFT_CONSTRUCTION_SPLIT_TRAILING_EDGE_DISPLAY,
                ),
                (
                    LOFT_CONSTRUCTION_CLOSED,
                    LOFT_CONSTRUCTION_CLOSED_DISPLAY,
                ),
            ):
                loft_construction_input.listItems.add(
                    display,
                    mode == loft_construction_mode_default,
                )
            loft_construction_input.tooltip = _t(
                "ui.loft_construction_mode_tooltip"
            )

            loft_order_input = operations_inputs.addDropDownCommandInput(
                "loftSectionOrder",
                _t("ui.loft_section_order"),
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            for option in (
                LOFT_ORDER_ROOT_TO_TIP,
                LOFT_ORDER_TIP_TO_ROOT,
                LOFT_ORDER_AUTOMATIC,
            ):
                loft_order_input.listItems.add(
                    option,
                    option == loft_section_order_default,
                )
            loft_order_input.tooltip = _t(
                "ui.loft_section_order_tooltip"
            )

            loft_guides_input = operations_inputs.addDropDownCommandInput(
                "loftGuideRails",
                _t("ui.loft_guide_rails"),
                adsk.core.DropDownStyles.TextListDropDownStyle,
            )
            for option in (
                LOFT_GUIDES_NONE,
                LOFT_GUIDES_DISTRIBUTED,
                LOFT_GUIDES_DUAL_TRAILING_EDGE,
            ):
                loft_guides_input.listItems.add(
                    option,
                    option == loft_guide_rails_default,
                )
            loft_guides_input.tooltip = _t(
                "ui.loft_guide_rails_tooltip"
            )

            distributed_count_input = (
                operations_inputs.addIntegerSpinnerCommandInput(
                    "loftDistributedRailCount",
                    _t("ui.loft_distributed_rail_count"),
                    3,
                    803,
                    2,
                    loft_distributed_rail_count_default,
                )
            )
            distributed_count_input.tooltip = _t(
                "ui.loft_distributed_rail_count_tooltip"
            )

            rail_placement_input = (
                operations_inputs.addDropDownCommandInput(
                    "loftRailPlacement",
                    _t("ui.loft_rail_placement"),
                    adsk.core.DropDownStyles.TextListDropDownStyle,
                )
            )
            for option in (
                LOFT_RAIL_PLACEMENT_UNIFORM_CHORD,
                LOFT_RAIL_PLACEMENT_FIRST_POINTS,
                LOFT_RAIL_PLACEMENT_VERTICES,
            ):
                rail_placement_input.listItems.add(
                    option,
                    option == loft_rail_placement_default,
                )
            rail_placement_input.tooltip = _t(
                "ui.loft_rail_placement_tooltip"
            )

            operations_inputs.addBoolValueInput(
                "loftMergeTangentEdges",
                _t("ui.loft_merge_tangent_edges"),
                True,
                "",
                loft_merge_tangent_edges_default,
            )

            quality_check_input = operations_inputs.addBoolValueInput(
                "loftQualityCheck",
                _t("ui.loft_quality_check"),
                True,
                "",
                loft_quality_check_default,
            )
            quality_check_input.tooltip = _t(
                "ui.loft_quality_check_tooltip"
            )

            quality_limit_input = operations_inputs.addStringValueInput(
                "loftQualityMaxDeviationPercent",
                _t("ui.loft_quality_max_deviation_percent"),
                f"{loft_quality_max_deviation_percent_default:g}",
            )
            quality_limit_input.tooltip = _t(
                "ui.loft_quality_max_deviation_percent_tooltip"
            )

            wave_angle_input = operations_inputs.addStringValueInput(
                "loftQualityMaxWaveAngleDeg",
                _t("ui.loft_quality_max_wave_angle_deg"),
                f"{loft_quality_max_wave_angle_deg_default:g}",
            )
            wave_angle_input.tooltip = _t(
                "ui.loft_quality_max_wave_angle_deg_tooltip"
            )

            post_fairing_margin_input = operations_inputs.addStringValueInput(
                "loftQualityPostFairingMarginMultiplier",
                _t("ui.loft_quality_post_fairing_margin_multiplier"),
                f"{loft_quality_post_fairing_margin_multiplier_default:g}",
            )
            post_fairing_margin_input.tooltip = _t(
                "ui.loft_quality_post_fairing_margin_multiplier_tooltip"
            )

            finalization_method_input = (
                operations_inputs.addDropDownCommandInput(
                    "finalizationMethod",
                    _t("ui.finalization_method"),
                    adsk.core.DropDownStyles.TextListDropDownStyle,
                )
            )
            for option in (
                FINALIZATION_BOUNDARY_FILL,
                FINALIZATION_LEGACY,
            ):
                finalization_method_input.listItems.add(
                    option,
                    option == finalization_method_default,
                )
            finalization_method_input.tooltip = _t(
                "ui.finalization_method_tooltip"
            )

            overlap_input = operations_inputs.addValueInput(
                "boundaryOverlapDiameter",
                _t("ui.boundary_overlap_diameter"),
                "mm",
                adsk.core.ValueInput.createByString(
                    f"{boundary_overlap_diameter_default_mm:.9g} mm"
                ),
            )
            overlap_input.minimumValue = 1e-10
            overlap_input.tooltip = _t(
                "ui.boundary_overlap_diameter_tooltip"
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
            _update_loft_inputs(inputs)
            _update_finalization_inputs(inputs)

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
    global _sample_catalog
    global _sample_discovery_errors

    try:
        _pending_timeline_run = None
        _sample_catalog = {}
        _sample_discovery_errors = []
        _set_dialog_config_base(None)

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
    global _sample_catalog
    global _sample_discovery_errors

    try:
        _pending_timeline_run = None
        _sample_catalog = {}
        _sample_discovery_errors = []
        _set_dialog_config_base(None)
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
