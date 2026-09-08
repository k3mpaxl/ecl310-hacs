"""Sensor platform - measured temperatures and circuit status.

The setpoints live on the climate and water-heater entities; what remains here
is what the controller measures and the state it derives from its schedule.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COMPONENT_HEATING, COMPONENT_HOT_WATER, COMPONENT_SENSORS
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import CircuitState, Ecl310, OperatingMode
from .entity import Ecl310Entity

PARALLEL_UPDATES = 0

_MODE_OPTIONS = [mode.name.lower() for mode in OperatingMode]
_STATE_OPTIONS = [state.name.lower() for state in CircuitState]


@dataclass(frozen=True, kw_only=True)
class Ecl310SensorDescription(SensorEntityDescription):
    """Describes a sensor reading one attribute of one sub-system."""

    component: str
    value_fn: Callable[[Ecl310], float | IntEnum | None]


def _temperature(
    key: str,
    component: str,
    value_fn: Callable[[Ecl310], float | IntEnum | None],
    *,
    diagnostic: bool = False,
) -> Ecl310SensorDescription:
    """Describe a measured temperature."""
    return Ecl310SensorDescription(
        key=key,
        translation_key=key,
        component=component,
        value_fn=value_fn,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC if diagnostic else None,
    )


def _enum(
    key: str,
    component: str,
    options: list[str],
    value_fn: Callable[[Ecl310], float | IntEnum | None],
) -> Ecl310SensorDescription:
    """Describe a discrete controller state."""
    return Ecl310SensorDescription(
        key=key,
        translation_key=key,
        component=component,
        value_fn=value_fn,
        device_class=SensorDeviceClass.ENUM,
        options=options,
        entity_category=EntityCategory.DIAGNOSTIC,
    )


SENSORS: tuple[Ecl310SensorDescription, ...] = (
    _temperature(
        "outdoor_temperature",
        COMPONENT_SENSORS,
        lambda device: device.sensors.outdoor_temperature,
    ),
    _temperature(
        "flow_temperature",
        COMPONENT_SENSORS,
        lambda device: device.sensors.flow_temperature,
    ),
    _temperature(
        "return_temperature",
        COMPONENT_SENSORS,
        lambda device: device.sensors.return_temperature,
    ),
    _temperature(
        "storage_temperature",
        COMPONENT_SENSORS,
        lambda device: device.sensors.storage_temperature,
        diagnostic=True,
    ),
    _enum(
        "heating_mode",
        COMPONENT_HEATING,
        _MODE_OPTIONS,
        lambda device: device.heating.mode,
    ),
    _enum(
        "heating_state",
        COMPONENT_HEATING,
        _STATE_OPTIONS,
        lambda device: device.heating.state,
    ),
    _enum(
        "hot_water_mode",
        COMPONENT_HOT_WATER,
        _MODE_OPTIONS,
        lambda device: device.hot_water.mode,
    ),
    _enum(
        "hot_water_state",
        COMPONENT_HOT_WATER,
        _STATE_OPTIONS,
        lambda device: device.hot_water.state,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ECL sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        Ecl310Sensor(coordinator, description) for description in SENSORS
    )


class Ecl310Sensor(Ecl310Entity, SensorEntity):
    """A single value read from the device."""

    entity_description: Ecl310SensorDescription

    def __init__(
        self, coordinator: Ecl310Coordinator, description: Ecl310SensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key, description.component)
        self.entity_description = description

    @property
    def native_value(self) -> float | str | None:
        """Return the current value, mapping enums to their lowercase name."""
        value = self.entity_description.value_fn(self.coordinator.device)
        if isinstance(value, IntEnum):
            return value.name.lower()
        return value
