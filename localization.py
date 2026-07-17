"""
Localization loader for Elliptical NACA Propeller Generator.

Fusion exposes the user's language as an API enum whose representation has
varied across releases. Detection therefore uses three layers:

1. direct comparison with known UserLanguages enum attributes;
2. Windows LCID integer mapping;
3. normalized enum-name text matching.

The optional Interface_Language value is read from the first available
configuration source: user configuration, legacy configuration, then factory
defaults. English is the fallback language, and every locale JSON must contain
exactly the same key set.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

SUPPORTED_LOCALES = ("pt-BR", "en", "es", "fr", "de", "ru")
DEFAULT_LOCALE = "en"

_LOCALE_ALIASES = {
    "auto": "auto",
    "": "auto",
    "pt": "pt-BR",
    "pt-br": "pt-BR",
    "pt_br": "pt-BR",
    "portuguese": "pt-BR",
    "brazilian portuguese": "pt-BR",
    "português": "pt-BR",
    "português do brasil": "pt-BR",
    "en": "en",
    "en-us": "en",
    "english": "en",
    "es": "es",
    "es-es": "es",
    "spanish": "es",
    "español": "es",
    "fr": "fr",
    "fr-fr": "fr",
    "french": "fr",
    "français": "fr",
    "de": "de",
    "de-de": "de",
    "german": "de",
    "deutsch": "de",
    "ru": "ru",
    "ru-ru": "ru",
    "russian": "ru",
    "русский": "ru",
}

_LCID_MAP = {
    1046: "pt-BR",
    1033: "en",
    1034: "es",
    1036: "fr",
    1031: "de",
    1049: "ru",
}

_ENUM_ATTRIBUTE_MAP = {
    "pt-BR": (
        "BrazilianPortugueseLanguage",
        "PortugueseBrazilLanguage",
        "PortugueseBrazilianLanguage",
    ),
    "en": ("EnglishLanguage",),
    "es": ("SpanishLanguage",),
    "fr": ("FrenchLanguage",),
    "de": ("GermanLanguage",),
    "ru": ("RussianLanguage",),
}

_NAME_MARKERS = {
    "pt-BR": ("brazilianportuguese", "portuguesebrazil", "portuguesebrazilian"),
    "en": ("english",),
    "es": ("spanish",),
    "fr": ("french",),
    "de": ("german",),
    "ru": ("russian",),
}


def _normalize_override(value: object) -> str:
    normalized = str(value or "auto").strip().lower()
    return _LOCALE_ALIASES.get(normalized, normalized if normalized in SUPPORTED_LOCALES else "auto")


def _read_override(config_paths) -> str:
    """Read the first valid Interface_Language value from ordered paths."""
    if isinstance(config_paths, (str, os.PathLike)):
        config_paths = (config_paths,)

    for config_path in config_paths:
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if (
                isinstance(data, dict)
                and "Interface_Language" in data
            ):
                return _normalize_override(
                    data.get("Interface_Language", "auto")
                )
        except Exception:
            continue

    return "auto"


def _detect_fusion_locale(app) -> str:
    try:
        value = app.preferences.generalPreferences.userLanguage
    except Exception:
        return DEFAULT_LOCALE

    # Prefer direct enum comparisons when the current Fusion Python package
    # exposes the UserLanguages enum names.
    try:
        import adsk.core
        enum_type = getattr(adsk.core, "UserLanguages", None)
        if enum_type is not None:
            for locale_code, attribute_names in _ENUM_ATTRIBUTE_MAP.items():
                for attribute_name in attribute_names:
                    candidate = getattr(enum_type, attribute_name, None)
                    if candidate is not None and value == candidate:
                        return locale_code
    except Exception:
        pass

    # Some API enum wrappers convert to the Windows language identifier.
    try:
        numeric_value = int(value)
        if numeric_value in _LCID_MAP:
            return _LCID_MAP[numeric_value]
    except Exception:
        pass

    # Final robust fallback for enum representations such as
    # "UserLanguages.EnglishLanguage".
    representation = (getattr(value, "name", "") or str(value)).lower()
    compact = "".join(character for character in representation if character.isalnum())
    for locale_code, markers in _NAME_MARKERS.items():
        if any(marker in compact for marker in markers):
            return locale_code

    return DEFAULT_LOCALE


def _load_json(path: str) -> dict[str, str]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid localization file: {path}")
    return {str(key): str(value) for key, value in data.items()}


@dataclass(frozen=True)
class Localizer:
    locale_code: str
    strings: dict[str, str]
    fallback: dict[str, str]

    def text(self, key: str, **values) -> str:
        template = self.strings.get(key, self.fallback.get(key, key))
        try:
            return template.format(**values)
        except Exception:
            return template


def create_localizer(
    app,
    base_directory: str,
    config_paths,
) -> Localizer:
    override = _read_override(config_paths)
    locale_code = override if override != "auto" else _detect_fusion_locale(app)
    if locale_code not in SUPPORTED_LOCALES:
        locale_code = DEFAULT_LOCALE

    locales_directory = os.path.join(base_directory, "locales")
    fallback = _load_json(os.path.join(locales_directory, f"{DEFAULT_LOCALE}.json"))
    strings = _load_json(os.path.join(locales_directory, f"{locale_code}.json"))
    return Localizer(locale_code=locale_code, strings=strings, fallback=fallback)
