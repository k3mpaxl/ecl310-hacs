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
from modbus_connection import IllegalDataAddressError
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
    # What the controller reports about itself (Danfoss VI.LG.V5.02, section
    # 6.12): build 8575, code number 087H3040, hardware H.3, software 1.56,
    # application A237.1 V04, produced in week 12 of 2017. The serial number is
    # the manual's example (1, 0x0215 = 66069), not the captured controller's.
    7: 8575,
    18: 3040,
    33: 0x4803,
    34: 0x0138,
    35: 1,
    36: 0x0215,
    2059: 65,
    2060: 237,
    2061: 1,
    2062: 0x0400,
    2098: 0x110C,
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
def refused_registers() -> set[int]:
    """Return the registers the controller answers with "illegal data address".

    Empty by default; a test parametrizes it to model an application that does
    not serve a parameter the integration reads.
    """
    return set()


@pytest.fixture
def application() -> str | None:
    """Return the application the simulated controller runs.

    ``None`` answers every register, as the captured image alone would. A
    profile key makes the controller refuse every parameter of the other
    profiles that this application lacks - as the real ones do - and seeds
    the parameters it has but the capture lacks with their factory defaults.
    """
    return None


@pytest.fixture
def register_image() -> dict[int, int]:
    """Return the register image the simulated controller starts from.

    The captured A237.1 controller by default; a test parametrizes it with
    another real controller's image from ``register_images``.
    """
    return HOLDING


#: Where the controller reports its application: prefix, type, sub, version.
APPLICATION_REGISTERS = (2059, 2060, 2061, 2062)


def reported_application(profile: object) -> dict[int, int]:
    """Return the registers a controller running ``profile`` reports it in."""
    number, _, sub = profile.application[1:].partition(".")  # type: ignore[attr-defined]
    return dict(
        zip(
            APPLICATION_REGISTERS,
            (ord("A"), int(number), int(sub or 0), profile.version << 8),  # type: ignore[attr-defined]
            strict=True,
        )
    )


def simulate(
    application: str, image: dict[int, int] | None = None
) -> tuple[dict[int, int], set[int]]:
    """Return the registers to seed and to refuse for an application.

    The controller also reports the application, as real ones do; a test
    refusing ``APPLICATION_REGISTERS`` models one that does not.
    """
    from custom_components.ecl310.ecl310_modbus import PROFILES

    image = HOLDING if image is None else image
    profile = PROFILES[application]
    known = set().union(*(other.parameters for other in PROFILES.values()))
    seed = {
        pnu - 1: parameter.default & 0xFFFF
        for pnu, parameter in profile.parameters.items()
        if parameter.default is not None and pnu - 1 not in image
    }
    seed |= reported_application(profile)
    return seed, {pnu - 1 for pnu in known - set(profile.parameters)}


@pytest.fixture
def connections(
    refused_registers: set[int],
    application: str | None,
    register_image: dict[int, int],
) -> list[MockModbusConnection]:
    """Hand out a freshly seeded controller for every connection opened.

    Each construction is its own object, as in production: the config flow
    closes the connection it probed over, and a closed connection stays closed.
    """
    created: list[MockModbusConnection] = []
    seed, lacking = (
        simulate(application, register_image) if application else ({}, set())
    )

    def _factory(*args: object, **kwargs: object) -> MockModbusConnection:
        connection = MockModbusConnection()
        unit = connection.for_unit(ENTRY_DATA["unit_id"])
        for address, value in {**register_image, **seed}.items():
            unit.holding[address] = value
        for address in refused_registers | lacking:
            unit.fail_read(address, IllegalDataAddressError())

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
