"""Sensor platform - measured temperatures and circuit status.

The setpoints live on the climate and water-heater entities; what remains here
is what the controller measures and the state it derives from its schedule.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, Platform, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .boost import HotWaterBoost
from .const import COMPONENT_HEATING, COMPONENT_HOT_WATER, COMPONENT_SENSORS
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import CircuitState, Ecl310, OperatingMode
from .entity import Ecl310Entity, supported

PARALLEL_UPDATES = 0

_MODE_OPTIONS = [mode.name.lower() for mode in OperatingMode]
_STATE_OPTIONS = [state.name.lower() for state in CircuitState]


@dataclass(frozen=True, kw_only=True)
class Ecl310SensorDescription(SensorEntityDescription):
    """Describes a sensor reading one attribute of one sub-system."""

    component: str
    field: str
    value_fn: Callable[[Ecl310], float | IntEnum | None]


def _temperature(
    key: str,
    component: str,
    value_fn: Callable[[Ecl310], float | IntEnum | None],
    *,
    diagnostic: bool = False,
) -> Ecl310SensorDescription:
    """Describe a measured temperature, read from the field its key names."""
    return Ecl310SensorDescription(
        key=key,
        translation_key=key,
        component=component,
        field=key,
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
    field: str,
    options: list[str],
    value_fn: Callable[[Ecl310], float | IntEnum | None],
) -> Ecl310SensorDescription:
    """Describe a discrete controller state."""
    return Ecl310SensorDescription(
        key=key,
        translation_key=key,
        component=component,
        field=field,
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
        "mode",
        _MODE_OPTIONS,
        lambda device: device.heating.mode,
    ),
    _enum(
        "heating_state",
        COMPONENT_HEATING,
        "state",
        _STATE_OPTIONS,
        lambda device: device.heating.state,
    ),
    _enum(
        "hot_water_mode",
        COMPONENT_HOT_WATER,
        "mode",
        _MODE_OPTIONS,
        lambda device: device.hot_water.mode,
    ),
    _enum(
        "hot_water_state",
        COMPONENT_HOT_WATER,
        "state",
        _STATE_OPTIONS,
        lambda device: device.hot_water.state,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ECL sensors."""
    coordinator = entry.runtime_data.coordinator
    boost = entry.runtime_data.boost
    async_add_entities(
        supported(
            hass,
            Platform.SENSOR,
            [
                *(Ecl310Sensor(coordinator, description) for description in SENSORS),
                *(
                    Ecl310BoostSensor(coordinator, boost, description)
                    for description in BOOST_SENSORS
                ),
            ],
        )
    )


@dataclass(frozen=True, kw_only=True)
class Ecl310BoostSensorDescription(SensorEntityDescription):
    """Describes one detail of the running hot water boost."""

    value_fn: Callable[[HotWaterBoost], Any]


BOOST_SENSORS: tuple[Ecl310BoostSensorDescription, ...] = (
    Ecl310BoostSensorDescription(
        key="hot_water_boost_start_temperature",
        translation_key="hot_water_boost_start_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda boost: (
            boost.session.start_temperature if boost.session else None
        ),
    ),
    Ecl310BoostSensorDescription(
        key="hot_water_boost_duration",
        translation_key="hot_water_boost_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda boost: (
            round(boost.elapsed.total_seconds() / 60, 1)
            if boost.elapsed is not None
            else None
        ),
    ),
    Ecl310BoostSensorDescription(
        key="hot_water_boost_estimated_end",
        translation_key="hot_water_boost_estimated_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda boost: boost.estimated_end,
    ),
)


class Ecl310BoostSensor(Ecl310Entity, SensorEntity):
    """A detail of the running boost; unknown while none runs."""

    entity_description: Ecl310BoostSensorDescription

    def __init__(
        self,
        coordinator: Ecl310Coordinator,
        boost: HotWaterBoost,
        description: Ecl310BoostSensorDescription,
    ) -> None:
        """Initialize the sensor on the hot water device."""
        super().__init__(coordinator, description.key, COMPONENT_HOT_WATER, ("mode",))
        self.entity_description = description
        self._boost = boost

    async def async_added_to_hass(self) -> None:
        """Follow the boost as well as the polls."""
        await super().async_added_to_hass()
        self.async_on_remove(self._boost.async_add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> Any:
        """Return the detail, or None while no boost runs."""
        return self.entity_description.value_fn(self._boost)


class Ecl310Sensor(Ecl310Entity, SensorEntity):
    """A single value read from the device."""

    entity_description: Ecl310SensorDescription

    def __init__(
        self, coordinator: Ecl310Coordinator, description: Ecl310SensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator, description.key, description.component, (description.field,)
        )
        self.entity_description = description

    @property
    def native_value(self) -> float | str | None:
        """Return the current value, mapping enums to their lowercase name."""
        value = self.entity_description.value_fn(self.coordinator.device)
        if isinstance(value, IntEnum):
            return value.name.lower()
        return value
