"""Check the shipped translations against the code and against each other.

Home Assistant resolves nothing at runtime: whatever stands in a translation
file is what the frontend shows. So these tests pin down the three ways a
translation goes wrong without anyone noticing - a stale ``en.json``, a
language that has drifted from it, and a state the code can produce that no
language has a word for.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.ecl310.climate import PRESETS
from custom_components.ecl310.water_heater import OPERATIONS

COMPONENT = Path(__file__).parent.parent / "custom_components" / "ecl310"
TRANSLATIONS = COMPONENT / "translations"
LANGUAGES = sorted(path.stem for path in TRANSLATIONS.glob("*.json"))


def load(language: str) -> dict:
    """Read one shipped translation file."""
    return json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8"))


def leaves(value: object, prefix: str = "") -> set[str]:
    """Every leaf path in a translation tree."""
    if not isinstance(value, dict):
        return {prefix}
    return {
        leaf
        for name, item in value.items()
        for leaf in leaves(item, f"{prefix}.{name}")
    }


def strings(value: object) -> list[str]:
    """Every translated string in a tree."""
    if isinstance(value, dict):
        return [text for item in value.values() for text in strings(item)]
    return [value] if isinstance(value, str) else []


def test_english_is_built_from_strings_json() -> None:
    """``en.json`` must be the expansion of ``strings.json``, not a stale copy."""
    source = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
    assert leaves(source) == leaves(load("en"))


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_unresolved_references(language: str) -> None:
    """A ``[%key:...%]`` reference reaches the frontend verbatim. None may survive."""
    unresolved = [text for text in strings(load(language)) if text.startswith("[%key:")]
    assert not unresolved


@pytest.mark.parametrize("language", [lang for lang in LANGUAGES if lang != "en"])
def test_every_language_covers_the_same_keys(language: str) -> None:
    """No key missing, none left over from something that was renamed."""
    assert leaves(load(language)) == leaves(load("en"))


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_operating_mode_has_a_word(language: str) -> None:
    """The modes the entities offer are exactly the ones the language names."""
    entity = load(language)["entity"]
    presets = entity["climate"]["heating_circuit"]["state_attributes"]["preset_mode"]
    assert set(presets["state"]) == set(PRESETS)
    assert set(entity["water_heater"]["hot_water"]["state"]) == set(OPERATIONS)
    for sensor in ("heating_mode", "hot_water_mode"):
        assert set(entity["sensor"][sensor]["state"]) == set(PRESETS)
