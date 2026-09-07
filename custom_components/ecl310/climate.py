"""Climate platform - the space heating circuit as a thermostat.

The controller is weather-compensated: the setpoint the operator changes is the
desired room temperature, and the controller derives the flow temperature from
it and the outdoor temperature.

The circuit has five ECL operating modes, which do not map onto three HVAC
modes without losing something. The HVAC mode carries the coarse choice - off,
follow the weekly program, heat now - and the preset carries the exact ECL mode,
so nothing the controller can be in is unrepresentable.
"""

from __future__ import annotations

from typing import Any, cast

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COMPONENT_HEATING, DOMAIN
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import HeatingCircuit, OperatingMode
from .entity import Ecl310Entity

PARALLEL_UPDATES = 1

TO_HVAC_MODE: dict[OperatingMode, HVACMode] = {
    OperatingMode.FROST_PROTECTION: HVACMode.OFF,
    OperatingMode.SCHEDULED: HVACMode.AUTO,
    OperatingMode.MANUAL: HVACMode.HEAT,
    OperatingMode.COMFORT: HVACMode.HEAT,
    OperatingMode.SETBACK: HVACMode.HEAT,
}
FROM_HVAC_MODE: dict[HVACMode, OperatingMode] = {
    HVACMode.OFF: OperatingMode.FROST_PROTECTION,
    HVACMode.AUTO: OperatingMode.SCHEDULED,
    HVACMode.HEAT: OperatingMode.COMFORT,
}
#: Manual is not one of these. Selecting it at the controller deactivates
#: every control loop, turns the frost protection off and refuses the output
#: override this integration writes - and it puts *all* circuits into manual,
#: not the one it was chosen for. It stays readable: a controller someone put
#: into manual at its own display says so, and the preset list grows to
#: include it for exactly as long as that is true.
SETTABLE: tuple[OperatingMode, ...] = (
    OperatingMode.SCHEDULED,
    OperatingMode.COMFORT,
    OperatingMode.SETBACK,
    OperatingMode.FROST_PROTECTION,
)

PRESETS: dict[str, OperatingMode] = {mode.name.lower(): mode for mode in OperatingMode}
SETTABLE_PRESETS: list[str] = [mode.name.lower() for mode in SETTABLE]


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the heating circuit thermostat."""
    async_add_entities([Ecl310Thermostat(entry.runtime_data.coordinator)])


class Ecl310Thermostat(Ecl310Entity, ClimateEntity):
    """The space heating circuit as a thermostat."""

    _attr_name = None  # primary entity -> takes the sub-device's name
    _attr_translation_key = "heating_circuit"  # names the presets, not the entity
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = 5
    _attr_max_temp = 40
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator: Ecl310Coordinator) -> None:
        """Initialize the thermostat."""
        super().__init__(coordinator, key="thermostat", component=COMPONENT_HEATING)

    @property
    def _circuit(self) -> HeatingCircuit:
        return cast(HeatingCircuit, self._subsystem)

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the coarse mode the circuit is in."""
        mode = self._circuit.mode
        return None if mode is None else TO_HVAC_MODE[mode]

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return whether the circuit is currently heating."""
        if self._circuit.mode is OperatingMode.FROST_PROTECTION:
            return HVACAction.OFF
        heating = self._circuit.heating
        if heating is None:
            return None
        return HVACAction.HEATING if heating else HVACAction.IDLE

    @property
    def preset_modes(self) -> list[str]:
        """Return the modes that may be chosen.

        Manual is only in the list while the controller is already in it, so
        that the entity can report it without offering it.
        """
        if self._circuit.mode is OperatingMode.MANUAL:
            return [*SETTABLE_PRESETS, OperatingMode.MANUAL.name.lower()]
        return SETTABLE_PRESETS

    @property
    def preset_mode(self) -> str | None:
        """Return the exact ECL operating mode."""
        mode = self._circuit.mode
        return None if mode is None else mode.name.lower()

    @property
    def target_temperature(self) -> float | None:
        """Return the comfort room setpoint."""
        return self._circuit.comfort_setpoint

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write a new comfort room setpoint."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self._circuit.async_set_comfort_setpoint(temperature)
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Write the ECL mode this HVAC mode stands for."""
        await self._circuit.async_set_mode(FROM_HVAC_MODE[hvac_mode])
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Write an exact ECL operating mode."""
        mode = PRESETS[preset_mode]
        if mode not in SETTABLE:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="manual_mode_not_settable",
            )
        await self._circuit.async_set_mode(mode)
        await self.coordinator.async_request_refresh()
