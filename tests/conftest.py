"""Test fixtures.

The tests run the integration inside a real Home Assistant, provided by
``pytest-homeassistant-custom-component``. Home Assistant looks for custom
integrations under its configuration directory, which in these tests is the one
that ships with that plugin, so the integration is installed there for the
duration of the session and removed again afterwards.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_homeassistant_custom_component
from modbus_connection.mock import MockModbusConnection

pytest_plugins = "pytest_homeassistant_custom_component"

DOMAIN = "ecl310"

# A register image captured read-only from a live ECL Comfort 310
# (087H3040, application key A237.1 V04, software 1.56) on unit 1.
HOLDING: dict[int, int] = {
    3999: 0,
    4000: 1,
    4001: 0,
    4002: 1,
    4003: 0,
    4004: 0,
    4005: 0,
    4006: 0,
    4007: 0,
    4008: 0,
    4009: 0,
    4010: 0,
    4025: 0,
    4026: 0,
    4027: 0,
    4028: 0,
    4029: 0,
    4030: 0,
    4065: 0,
    4066: 0,
    4067: 0,
    4068: 0,
    4069: 0,
    4070: 0,
    4200: 4,
    4201: 1,
    4210: 0,
    4211: 2,
    10200: 3022,
    10201: 19200,
    10202: 5536,
    10203: 19200,
    10204: 6052,
    10205: 4536,
    11020: 1,
    11176: 15,
    11177: 15,
    11178: 12,
    11179: 220,
    11180: 180,
    12124: 60,
    12189: 400,
    # Heating: return limit, pump post-run, hot water priority, frost, curve
    11027: 70,
    11039: 90,
    11051: 0,
    11092: 10,
    11174: 15,
    11399: 100,
    11400: 77,
    11401: 62,
    11402: 55,
    11403: 47,
    11404: 32,
    # Hot water: return limit, frost limits, charging thresholds, setback
    12029: 70,
    12075: 2,
    12092: 10,
    12121: 0b0100000,  # anti-bacteria on Saturday
    12122: 10,  # 05:00
    12123: 45,
    12151: 80,
    12190: 100,
    12192: 20,
    12193: 2,
    12194: -3 & 0xFFFF,
    # The two weekly programs, as this controller was running them
    **{
        3109 + 10 * day + offset: value
        for day in range(7)
        for offset, value in enumerate(
            (600, 2000, 2330, 2330, 2330, 2330)
            if day < 4
            else (700, 2030, 2330, 2330, 2330, 2330)
        )
    },
    **{
        3209 + 10 * day + offset: value
        for day in range(7)
        for offset, value in enumerate((500, 2100, 2100, 2100, 2330, 2330))
    },
}

#: Relay 1..6 state registers - read only on the real controller.
RELAY_STATE = 4005

#: Relay 1..6 override registers - the writable ones.
RELAY_OVERRIDE = 4065

ENTRY_DATA = {
    "host": "192.168.1.100",
    "port": 502,
    "unit_id": 1,
    "framer": "socket",
}


@pytest.fixture(autouse=True, scope="session")
def install_integration() -> None:
    """Put the integration where Home Assistant looks for custom components."""
    source = Path(__file__).parent.parent / "custom_components" / DOMAIN
    config = Path(pytest_homeassistant_custom_component.__file__).parent
    target = config / "testing_config" / "custom_components" / DOMAIN

    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
    try:
        yield
    finally:
        shutil.rmtree(target, ignore_errors=True)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations it did not ship with."""
    return


@pytest.fixture
def connections() -> list[MockModbusConnection]:
    """Hand out a freshly seeded controller for every connection opened.

    Each construction is its own object, as in production: the config flow
    closes the connection it probed over, and a closed connection stays closed.
    """
    created: list[MockModbusConnection] = []

    def _factory(*args: object, **kwargs: object) -> MockModbusConnection:
        connection = MockModbusConnection()
        unit = connection.for_unit(ENTRY_DATA["unit_id"])
        for address, value in HOLDING.items():
            unit.holding[address] = value

        def follow_the_override(event: object) -> None:
            """Mirror what the real controller does with an override.

            Writing 2 to a relay's override register puts the output on within
            a couple of seconds; writing 1 puts it off; writing 0 hands it back
            to the regulation, which on a mock means off.
            """
            address = event.address  # type: ignore[attr-defined]
            if RELAY_OVERRIDE <= address < RELAY_OVERRIDE + 6:
                relay = address - RELAY_OVERRIDE
                value = event.values[0]  # type: ignore[attr-defined]
                unit.holding[RELAY_STATE + relay] = 1 if value == 2 else 0

        unit.on_write(follow_the_override)
        created.append(connection)
        return connection

    # Patch where the integration bound the name. A ``from ... import`` in a
    # module an earlier test already loaded keeps its own reference, so patching
    # the source module would miss it.
    import custom_components.ecl310 as integration
    from custom_components.ecl310 import config_flow

    with (
        patch.object(integration, "ModbusConnection", side_effect=_factory),
        patch.object(config_flow, "ModbusConnection", side_effect=_factory),
    ):
        yield created
