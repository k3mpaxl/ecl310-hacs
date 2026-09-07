"""Water heater platform - the domestic hot water circuit.

The operation list is the controller's own five ECL modes rather than Home
Assistant's generic ones, because that is what the controller's display, its
weekly program and its documentation all use.
"""

from __future__ import annotations

from typing import Any, cast

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .climate import SETTABLE
from .const import COMPONENT_HOT_WATER, DOMAIN
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import HotWater, OperatingMode
from .entity import Ecl310Entity

PARALLEL_UPDATES = 1

OPERATIONS: dict[str, OperatingMode] = {
    mode.name.lower(): mode for mode in OperatingMode
}

#: The modes that may be chosen. Manual is left out for the reasons the
#: climate platform sets out: it disables every control loop and the frost
#: protection, and it takes all circuits with it.
SETTABLE_OPERATIONS: list[str] = [mode.name.lower() for mode in SETTABLE]


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the hot water entity."""
    async_add_entities([Ecl310WaterHeater(entry.runtime_data.coordinator)])


class Ecl310WaterHeater(Ecl310Entity, WaterHeaterEntity):
    """Domestic hot water preparation as a water heater."""

    _attr_name = None  # primary entity -> takes the sub-device's name
    _attr_translation_key = "hot_water"  # names the operating modes, not the entity
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )

    _attr_min_temp = 40
    _attr_max_temp = 65
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator: Ecl310Coordinator) -> None:
        """Initialize the water heater."""
        super().__init__(coordinator, key="water_heater", component=COMPONENT_HOT_WATER)

    @property
    def _hot_water(self) -> HotWater:
        return cast(HotWater, self._subsystem)

    @property
    def current_temperature(self) -> float | None:
        """Return the storage temperature measured on S6."""
        return self.coordinator.device.sensors.storage_temperature

    @property
    def target_temperature(self) -> float | None:
        """Return the hot water setpoint."""
        return self._hot_water.setpoint

    @property
    def operation_list(self) -> list[str]:
        """Return the modes that may be chosen.

        Manual joins the list only while the controller is already in it.
        """
        if self._hot_water.mode is OperatingMode.MANUAL:
            return [*SETTABLE_OPERATIONS, OperatingMode.MANUAL.name.lower()]
        return SETTABLE_OPERATIONS

    @property
    def current_operation(self) -> str | None:
        """Return the controller's operating mode."""
        mode = self._hot_water.mode
        return None if mode is None else mode.name.lower()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write a new hot water setpoint."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self._hot_water.async_set_setpoint(temperature)
            await self.coordinator.async_request_refresh()

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Write the hot water operating mode."""
        mode = OPERATIONS[operation_mode]
        if mode not in SETTABLE:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="manual_mode_not_settable",
            )
        await self._hot_water.async_set_mode(mode)
        await self.coordinator.async_request_refresh()
