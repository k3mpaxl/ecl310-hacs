"""Sensor platform - measured temperatures and circuit status.

The setpoints live on the climate and water-heater entities; what remains here
is what the controller measures and the state it derives from its schedule.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .boost import HotWaterBoost
from .const import COMPONENT_HEATING, COMPONENT_HOT_WATER, COMPONENT_SENSORS
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import CircuitState, Ecl310, OperatingMode
from .ecl310_modbus.subsystems.alarms import active_alarm_ids
from .ecl310_modbus.subsystems.limiter import decode_limiter
from .entity import (
    Ecl310Entity,
    device_identifiers,
    per_circuit,
    role_name,
    supported,
)

PARALLEL_UPDATES = 0

_MODE_OPTIONS = [mode.name.lower() for mode in OperatingMode]
_STATE_OPTIONS = [state.name.lower() for state in CircuitState]


@dataclass(frozen=True, kw_only=True)
class Ecl310SensorDescription(SensorEntityDescription):
    """Describes a sensor reading one attribute of one sub-system."""

    component: str
    field: str


def _temperature(
    key: str,
    component: str,
    *,
    diagnostic: bool = False,
    field: str | None = None,
) -> Ecl310SensorDescription:
    """Describe a temperature, read from ``field`` - by default its key."""
    return Ecl310SensorDescription(
        key=key,
        translation_key=key,
        component=component,
        field=field or key,
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
) -> Ecl310SensorDescription:
    """Describe a discrete controller state."""
    return Ecl310SensorDescription(
        key=key,
        translation_key=key,
        component=component,
        field=field,
        device_class=SensorDeviceClass.ENUM,
        options=options,
        entity_category=EntityCategory.DIAGNOSTIC,
    )


#: The sensor roles shown, as the library derives them from the application;
#: those marked are diagnostic. A role the application has on two circuits
#: comes suffixed with its circuit and is named "... circuit n".
SENSOR_ROLES: dict[str, bool] = {
    "outdoor_temperature": False,
    "flow_temperature": False,
    "return_temperature": False,
    "storage_temperature": True,
    "secondary_return_temperature": False,
    "hot_water_flow_temperature": False,
    "hot_water_return_temperature": False,
}


def role_sensors(device: Ecl310) -> tuple[Ecl310SensorDescription, ...]:
    """Describe a temperature for each input the application assigns a role."""
    descriptions = []
    for role in device.sensor_assignment.values():
        translation_key, placeholders = role_name(role)
        base = translation_key.removesuffix("_circuit")
        if base not in SENSOR_ROLES:
            continue
        descriptions.append(
            replace(
                _temperature(role, COMPONENT_SENSORS, diagnostic=SENSOR_ROLES[base]),
                translation_key=translation_key,
                translation_placeholders=placeholders,
            )
        )
    return tuple(descriptions)


#: Per circuit: what the controller is working with, and its mode and status.
CIRCUIT_SENSORS: tuple[Ecl310SensorDescription, ...] = (
    _temperature("desired_flow_temperature", COMPONENT_HEATING),
    _temperature("filtered_outdoor_temperature", COMPONENT_HEATING),
    _temperature("return_limit_in_force", COMPONENT_HEATING, diagnostic=True),
    _temperature("desired_tank_temperature", COMPONENT_HOT_WATER),
    _temperature(
        "desired_hot_water_flow_temperature",
        COMPONENT_HOT_WATER,
        field="desired_flow_temperature",
    ),
    _enum("heating_mode", COMPONENT_HEATING, "mode", _MODE_OPTIONS),
    _enum("heating_state", COMPONENT_HEATING, "state", _STATE_OPTIONS),
    _enum("hot_water_mode", COMPONENT_HOT_WATER, "mode", _MODE_OPTIONS),
    _enum("hot_water_state", COMPONENT_HOT_WATER, "state", _STATE_OPTIONS),
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
                *(
                    Ecl310Sensor(coordinator, description)
                    for description in (
                        *role_sensors(coordinator.device),
                        *per_circuit(coordinator.device, CIRCUIT_SENSORS),
                    )
                ),
                *(
                    [Ecl310AlarmSensor(coordinator)]
                    if coordinator.device.application is not None
                    else []
                ),
                *(
                    Ecl310LimiterSensor(coordinator, circuit)
                    for circuit in coordinator.device.circuits
                    if coordinator.device.application is not None
                ),
                *(
                    Ecl310BoostSensor(coordinator, boost, description)
                    for description in BOOST_SENSORS
                    if boost.available
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

    _shows_datapoints = False

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
        value = getattr(self._subsystem, self.entity_description.field)
        if isinstance(value, IntEnum):
            return value.name.lower()
        return value


class Ecl310AlarmSensor(Ecl310Entity, SensorEntity):
    """The number of active alarms and their raw, application-specific contexts."""

    _attr_translation_key = "active_alarms"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: Ecl310Coordinator) -> None:
        """Initialize the controller-wide diagnostic."""
        super().__init__(
            coordinator, "active_alarms", "alarms", ("mask_low", "mask_high")
        )

    @property
    def native_value(self) -> int | None:
        """Count the active alarm IDs when both masks are known."""
        ids = active_alarm_ids(self._subsystem.mask_low, self._subsystem.mask_high)
        return len(ids) if ids is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Include active IDs and available raw contexts."""
        attrs = super().extra_state_attributes or {}
        ids = active_alarm_ids(self._subsystem.mask_low, self._subsystem.mask_high)
        if ids is not None and self.available:
            refused = self.coordinator.refused("alarms")
            attrs["alarm_ids"] = ids
            attrs["contexts"] = {
                str(n): getattr(self._subsystem, f"context_{n}")
                for n in ids
                if f"context_{n}" not in refused
                and getattr(self._subsystem, f"context_{n}") is not None
            }
        return attrs


class Ecl310LimiterSensor(Ecl310Entity, SensorEntity):
    """Show the ECL's per-circuit limiter directions and raw words."""

    _attr_translation_key = "limiter_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chart-bell-curve-cumulative"

    def __init__(self, coordinator: Ecl310Coordinator, circuit: Any) -> None:
        """Attach the diagnostic to its circuit device."""
        super().__init__(
            coordinator,
            f"limiter_status_circuit_{circuit.number}",
            f"limiter_{circuit.number}",
            tuple(f"word_{i}" for i in range(1, 5)),
        )
        self._attr_device_info = DeviceInfo(
            identifiers=device_identifiers(coordinator.config_entry, circuit.component)
        )
        self._circuit_number = circuit.number

    def _decoded(self) -> dict[str, str | None] | None:
        system = self.coordinator.device.system
        words = tuple(getattr(self._subsystem, f"word_{i}") for i in range(1, 5))
        if system is None or any(value is None for value in words):
            return None
        if self._circuit_number >= 5:  # noqa: PLR2004
            try:
                version = tuple(int(p) for p in (system.software or "").split("."))
                if len(version) != 2 or version < (1, 60):  # noqa: PLR2004
                    return None
            except ValueError:
                return None
        return decode_limiter(words, system.software, system.build)

    @property
    def native_value(self) -> str | None:
        """Report partial when some influences are unknown for the firmware."""
        decoded = self._decoded()
        if decoded is None:
            return None
        if any(value is None for value in decoded.values()):
            return "partial"
        return (
            "active" if any(value != "none" for value in decoded.values()) else "none"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Include decoded directions and the unchanged source words."""
        attrs = super().extra_state_attributes or {}
        if self.available and (decoded := self._decoded()) is not None:
            attrs["influences"] = decoded
            attrs["raw_words"] = [
                getattr(self._subsystem, f"word_{i}") for i in range(1, 5)
            ]
        return attrs
