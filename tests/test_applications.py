"""Applications: profiles, detection, and entities only for what exists.

The simulated controllers refuse the parameters their application lacks, the
way the real ones do: A237.1 V04 is the captured controller, A337.2 V02 the
one from issue 13.
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from modbus_connection import IllegalDataAddressError
from modbus_connection.mock import MockModbusConnection
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ecl310.ecl310_modbus import PROFILES, Ecl310
from custom_components.ecl310.ecl310_modbus.subsystems import Outputs

from .conftest import DOMAIN, ENTRY_DATA, HOLDING
from .test_integration import entity_ids, setup_entry

A237 = "a237_1_v04"
A337 = "a337_2_v02"
DISINFECTION = 12124  # parameter 12125, the disinfection temperature


def _unit(connections: list[MockModbusConnection]) -> MockModbusConnection:
    return connections[-1].for_unit(ENTRY_DATA["unit_id"])


async def _flow_to_application_step(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(ENTRY_DATA)
    )


# -- the profiles -------------------------------------------------------------


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_the_library_stays_inside_each_profile(key: str) -> None:
    """Every modelled parameter the application has fits its report.

    The library may be narrower - a 150 °C hot water setpoint is not an
    everyday adjustment - but never wider, never differently scaled, and
    never writable where the controller is not.
    """
    profile = PROFILES[key]
    device = Ecl310(None, application=profile)  # type: ignore[arg-type]
    checked = 0
    for name in ("heating", "hot_water"):
        component = getattr(device, name)
        for field in component.resolved_fields:
            metadata = component.metadata_for(field)
            if metadata is None or metadata.parameter_id is None:
                continue
            parameter = profile.parameters[metadata.parameter_id]
            number = metadata.number
            if number is not None and number.raw_min is not None:
                assert parameter.minimum <= number.raw_min, field
                assert number.raw_max <= parameter.maximum, field
            assert parameter.writable or not metadata.writable, field
            checked += 1
    assert checked > 20


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_disinfection_off_is_in_every_profile(key: str) -> None:
    """9 is how the controller stores "off", and the library knows it."""
    parameter = PROFILES[key].parameters[12125]
    assert parameter.off == parameter.minimum == parameter.default == 9
    metadata = Ecl310(None).hot_water.metadata_for("disinfection_temperature")  # type: ignore[arg-type]
    assert metadata.number.off_value == 9


# -- detection ----------------------------------------------------------------


@pytest.mark.parametrize(("application", "expected"), [(A237, A237), (A337, A337)])
async def test_detection_tells_the_applications_apart(
    connections: list[MockModbusConnection], application: str, expected: str
) -> None:
    """The refused parameters single out the application."""
    from custom_components.ecl310 import ModbusConnection

    connection = ModbusConnection(None)
    detection = await Ecl310.async_detect_application(connection.for_unit(1))
    assert detection.application is PROFILES[expected]
    assert 11027 + 1 in (detection.answered if expected == A237 else detection.refused)


async def test_a_controller_answering_everything_is_not_guessed(
    connections: list[MockModbusConnection],
) -> None:
    """No profile fits a controller that refuses nothing better than another."""
    from custom_components.ecl310 import ModbusConnection

    detection = await Ecl310.async_detect_application(
        ModbusConnection(None).for_unit(1)
    )
    assert detection.application is None


# -- setup --------------------------------------------------------------------


@pytest.mark.parametrize("application", [A337])
async def test_the_flow_suggests_the_detected_application(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The A337.2 controller is recognised, and set up without what it lacks."""
    result = await _flow_to_application_step(hass)
    assert result["step_id"] == "application"
    assert result["description_placeholders"] == {"detected": "A337.2 V02"}
    schema = result["data_schema"].schema
    assert next(iter(schema)).default() == A337

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"application": A337}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.data["application"] == A337

    ids = entity_ids(hass, entry)
    assert "heating_return_limit" not in ids
    assert hass.states.get(ids["heating_frost_protection_temperature"]).state == "10"
    controller = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert controller.model_id == "A337.2 V02"
    # Nothing is refused at runtime: the profile left the parameter out.
    unit = _unit(connections)
    assert not [e for e in unit.read_events if e.address == 11027]


@pytest.mark.parametrize("application", [A337])
async def test_an_existing_entry_detects_its_application_once(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """An entry from before 0.9 is detected, stored, and tidied up."""
    entry = MockConfigEntry(
        domain=DOMAIN, data=ENTRY_DATA, unique_id="192.168.1.100:502:1"
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "number",
        DOMAIN,
        f"{entry.entry_id}_heating_return_limit",
        config_entry=entry,
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data["application"] == A337
    assert registry.async_get(stale.entity_id) is None

    # Stored, so the next start does not probe again.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    probes = [e for e in _unit(connections).read_events if e.address == 11100]
    assert not probes


@pytest.mark.parametrize("application", [A337])
async def test_the_options_change_the_application(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Choosing "other" reads every parameter again and reloads."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**ENTRY_DATA, "application": A337},
        unique_id="192.168.1.100:502:1",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert "heating_return_limit" not in entity_ids(hass, entry)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"application": "generic"}
    )
    await hass.async_block_till_done()
    assert entry.options["application"] == "generic"

    ids = entity_ids(hass, entry)
    assert hass.states.get(ids["heating_return_limit"]).state == STATE_UNAVAILABLE
    controller = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert controller.model_id is None


# -- the disinfection's off value -------------------------------------------------


@pytest.mark.parametrize("application", [A337])
async def test_the_disinfection_can_be_switched_off_and_on(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """9 reads as off, not as 9 °C, and Home Assistant can write it back."""
    monkeypatch.setitem(HOLDING, DISINFECTION, 9)
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    unit = _unit(connections)

    assert hass.states.get(ids["disinfection"]).state == "off"
    temperature = hass.states.get(ids["disinfection_temperature"])
    assert temperature.state == STATE_UNKNOWN
    assert temperature.attributes["min"] == 10
    assert temperature.attributes["max"] == 110

    async def call(domain: str, service: str, entity: str, **data: object) -> None:
        await hass.services.async_call(
            domain, service, {"entity_id": ids[entity], **data}, blocking=True
        )
        # The refresh a write requests is debounced; take it now.
        await entry.runtime_data.coordinator.async_refresh()
        await hass.async_block_till_done()

    await call("switch", "turn_on", "disinfection")
    assert unit.holding[DISINFECTION] == 70
    await call("number", "set_value", "disinfection_temperature", value=65)
    assert unit.holding[DISINFECTION] == 65
    await call("switch", "turn_off", "disinfection")
    assert unit.holding[DISINFECTION] == 9
    assert hass.states.get(ids["disinfection_temperature"]).state == STATE_UNKNOWN
    await call("switch", "turn_on", "disinfection")
    assert unit.holding[DISINFECTION] == 65


# -- reading around registers the controller does not serve --------------------

GAP = set(range(4011, 4025))  # between the output states and the manual values


@pytest.mark.parametrize("application", [A337])
@pytest.mark.parametrize("refused_registers", [GAP])
async def test_the_outputs_are_read_around_the_gap(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """Issue 13: the states and manual values are two blocks, not one."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    assert hass.states.get(ids["circulation_pump"]).state == "off"
    assert hass.states.get(ids["circulation_pump_override"]).state == "auto"
    assert "outputs" not in entry.runtime_data.coordinator.data.failed


@pytest.mark.parametrize("refused_registers", [GAP])
async def test_a_block_failing_as_a_whole_is_split(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every field answering on its own means: read them in smaller blocks.

    With the outputs declared as one block again - as before 0.9 - the read
    across the gap fails, no field is refused, and the values are kept.
    """
    monkeypatch.setattr(Outputs, "register_ranges", ((3999, 4030), (4065, 4070)))
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)

    assert hass.states.get(ids["circulation_pump"]).state == "off"
    assert hass.states.get(ids["circulation_pump_override"]).state == "auto"
    assert "reading them as 3999-4010, 4025-4030" in caplog.text

    unit = _unit(connections)
    unit.read_events.clear()
    await entry.runtime_data.coordinator.async_refresh()
    blocks = {(e.address, e.count) for e in unit.read_events if e.address < 4065}
    assert blocks == {(3999, 12), (4025, 6)}


@pytest.mark.parametrize("refused_registers", [{4011}])
async def test_a_register_refused_on_its_own_still_drops_the_field(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Splitting is only for blocks whose fields all answer."""
    monkeypatch.setattr(Outputs, "register_ranges", ((3999, 4030), (4065, 4070)))
    unit_failure = IllegalDataAddressError()
    entry = await setup_entry(hass, connections)
    _unit(connections).fail_read(4005, unit_failure)  # relay 1, from now on
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    ids = entity_ids(hass, entry)
    assert hass.states.get(ids["heating_pump"]).state == STATE_UNAVAILABLE
    assert hass.states.get(ids["circulation_pump"]).state == "off"
