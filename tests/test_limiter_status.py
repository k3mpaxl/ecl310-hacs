"""Limiter decoding and circuit mapping from the Danfoss protocol."""

import pytest
from homeassistant.core import HomeAssistant
from modbus_connection.mock import MockModbusConnection

from custom_components.ecl310.ecl310_modbus.subsystems.limiter import (
    decode_limiter,
    limiter_component,
)

from .conftest import ENTRY_DATA
from .test_integration import entity_ids, setup_entry


def test_limiter_bit_pairs_and_versions() -> None:
    """Each pair has its own direction, and later flags need the right version."""
    data = decode_limiter((1 | (2 << 2) | (3 << 4), 0, 0, 0), "1.56", 8500)
    assert data["return_limit"] == "higher"
    assert data["room_limit"] == "lower"
    assert data["wind"] == "changed"
    assert data["timeout_override"] == "none"
    assert data["low_flow"] is None
    assert decode_limiter((0, 0, 0, 0), "1.58", 8388)["low_flow"] is None
    assert decode_limiter((0, 0, 0, 0), "1.58", 8389)["low_flow"] == "none"
    assert decode_limiter((0, 0, 0, 0), "1.31", 9000) is None
    assert decode_limiter((0, 0, 0, 0), None, None) is None
    assert decode_limiter((0, 0, 0, 0), "1.32", 9000)["timeout_override"] is None
    assert decode_limiter((0, 0, 0, 0), "1.54", 9000)["output_temperature_stop"] is None


def test_limiter_register_mapping() -> None:
    """Circuit numbers map to the four documented consecutive PNUs."""
    for n, pnu in [(1, 4220), (2, 4224), (3, 4228), (5, 4246), (6, 4250)]:
        cls = limiter_component(n)
        assert [
            cls.declared_fields[f"word_{i}"].address + 1 for i in range(1, 5)
        ] == list(range(pnu, pnu + 4))


@pytest.mark.parametrize("application", ["a367_1_v04"])
async def test_circuit_diagnostics_are_independent(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """The second heating circuit and hot water circuit use their own words."""
    entry = await setup_entry(hass, connections)
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    unit.holding[4219] = 1
    unit.holding[4223] = 2
    unit.holding[4227] = 3
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    ids = entity_ids(hass, entry)
    for key, expected in [
        ("limiter_status_circuit_1", "higher"),
        ("limiter_status_circuit_2", "lower"),
        ("limiter_status_circuit_3", "changed"),
    ]:
        state = hass.states.get(ids[key])
        assert state.attributes["influences"]["return_limit"] == expected


@pytest.mark.parametrize("application", ["a266_10_v03"])
@pytest.mark.parametrize("refused_registers", [{4220}])
async def test_partial_limiter_read_is_unavailable(
    hass: HomeAssistant, connections: list[MockModbusConnection]
) -> None:
    """A refused word cannot create a false no-influence status."""
    entry = await setup_entry(hass, connections)
    ids = entity_ids(hass, entry)
    assert hass.states.get(ids["limiter_status_circuit_1"]).state == "unavailable"
    assert hass.states.get(ids["thermostat"]).state not in ("unavailable", "unknown")


@pytest.mark.parametrize("application", ["a266_10_v03"])
@pytest.mark.parametrize(("word_index", "reserved_bit"), [(0, 10), (3, 8), (3, 15)])
async def test_reserved_limiter_bits_do_not_claim_no_influence(
    hass: HomeAssistant,
    connections: list[MockModbusConnection],
    word_index: int,
    reserved_bit: int,
) -> None:
    """A reserved bit set cannot be decoded as a definite all-clear."""
    from dataclasses import replace

    entry = await setup_entry(hass, connections)
    device = entry.runtime_data.coordinator.device
    device.system = replace(device.system, software="1.60", build=9000)
    unit = connections[-1].for_unit(ENTRY_DATA["unit_id"])
    unit.holding[4219 + word_index] = 1 << reserved_bit
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(entity_ids(hass, entry)["limiter_status_circuit_1"])
    assert state.state == "partial"
    assert state.attributes["raw_words"][word_index] == 1 << reserved_bit
