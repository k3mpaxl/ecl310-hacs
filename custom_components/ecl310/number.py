"""Number platform - the setpoints that are not a thermostat setting.

Each entity takes its range, step and unit from the library's datapoint
metadata, so the bounds shown in the UI are the ones the controller accepts.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COMPONENT_HEATING, COMPONENT_HOT_WATER
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import Ecl310
from .ecl310_modbus.subsystems.heating_circuit import CURVE_POINTS
from .entity import Ecl310Entity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class Ecl310NumberDescription(NumberEntityDescription):
    """Describes a writable numeric datapoint."""

    component: str
    attribute: str
    set_fn: Callable[[Ecl310, float], Awaitable[None]]


def _setting(  # noqa: PLR0913 one argument per column of the table below
    component: str,
    attribute: str,
    set_fn: Callable[[Ecl310, float], Awaitable[None]],
    *,
    key: str | None = None,
    unit: str | None = None,
    device_class: NumberDeviceClass | None = None,
) -> Ecl310NumberDescription:
    """Describe a writable numeric setting.

    ``key`` overrides the attribute name where two circuits carry the same
    setting: the key is what the entity's unique id is built from, so it has
    to be unique across the whole integration even where the attribute is not.
    """
    key = key or attribute
    return Ecl310NumberDescription(
        key=key,
        translation_key=key,
        component=component,
        attribute=attribute,
        set_fn=set_fn,
        device_class=device_class,
        native_unit_of_measurement=unit,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    )


def _temperature_setting(
    component: str,
    attribute: str,
    set_fn: Callable[[Ecl310, float], Awaitable[None]],
    *,
    key: str | None = None,
) -> Ecl310NumberDescription:
    """Describe a writable temperature setting."""
    return _setting(
        component,
        attribute,
        set_fn,
        key=key,
        unit=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
    )


def _curve_point(outdoor: int) -> Ecl310NumberDescription:
    """Describe one point of the heat curve."""
    attribute = f"curve_at_{str(outdoor).replace('-', 'minus_')}"
    return _temperature_setting(
        COMPONENT_HEATING,
        attribute,
        lambda device, value, at=outdoor: device.heating.async_set_curve_point(
            at, value
        ),
    )


NUMBERS: tuple[Ecl310NumberDescription, ...] = (
    _temperature_setting(
        COMPONENT_HEATING,
        "setback_setpoint",
        lambda device, value: device.heating.async_set_setback_setpoint(value),
    ),
    _temperature_setting(
        COMPONENT_HEATING,
        "summer_cut_off",
        lambda device, value: device.heating.async_set_summer_cut_off(value),
    ),
    _temperature_setting(
        COMPONENT_HEATING,
        "min_flow_temperature",
        lambda device, value: device.heating.async_set_min_flow_temperature(value),
    ),
    _temperature_setting(
        COMPONENT_HEATING,
        "max_flow_temperature",
        lambda device, value: device.heating.async_set_max_flow_temperature(value),
    ),
    _temperature_setting(
        COMPONENT_HOT_WATER,
        "disinfection_temperature",
        lambda device, value: device.hot_water.async_set_disinfection_temperature(
            value
        ),
    ),
    # --- the heat curve and its six points ---------------------------------
    _setting(
        COMPONENT_HEATING,
        "heat_curve",
        lambda device, value: device.heating.async_set_heat_curve(value),
    ),
    *(_curve_point(outdoor) for outdoor in CURVE_POINTS),
    # --- the remaining heating settings ------------------------------------
    _temperature_setting(
        COMPONENT_HEATING,
        "return_limit",
        lambda device, value: device.heating.async_set_return_limit(value),
        key="heating_return_limit",
    ),
    _temperature_setting(
        COMPONENT_HEATING,
        "frost_protection_temperature",
        lambda device, value: device.heating.async_set_frost_protection_temperature(
            value
        ),
        key="heating_frost_protection_temperature",
    ),
    _setting(
        COMPONENT_HEATING,
        "pump_post_run",
        lambda device, value: device.heating.async_set_pump_post_run(value),
        unit=UnitOfTime.MINUTES,
        device_class=NumberDeviceClass.DURATION,
    ),
    # --- hot water ---------------------------------------------------------
    _temperature_setting(
        COMPONENT_HOT_WATER,
        "setback_setpoint",
        lambda device, value: device.hot_water.async_set_setback_setpoint(value),
        key="hot_water_setback_setpoint",
    ),
    _temperature_setting(
        COMPONENT_HOT_WATER,
        "return_limit",
        lambda device, value: device.hot_water.async_set_return_limit(value),
        key="hot_water_return_limit",
    ),
    _temperature_setting(
        COMPONENT_HOT_WATER,
        "max_charge_temperature",
        lambda device, value: device.hot_water.async_set_max_charge_temperature(value),
    ),
    _setting(
        COMPONENT_HOT_WATER,
        "charge_difference",
        lambda device, value: device.hot_water.async_set_charge_difference(value),
        unit=UnitOfTemperature.KELVIN,
    ),
    _setting(
        COMPONENT_HOT_WATER,
        "start_difference",
        lambda device, value: device.hot_water.async_set_start_difference(value),
        unit=UnitOfTemperature.KELVIN,
    ),
    _setting(
        COMPONENT_HOT_WATER,
        "stop_difference",
        lambda device, value: device.hot_water.async_set_stop_difference(value),
        unit=UnitOfTemperature.KELVIN,
    ),
    _setting(
        COMPONENT_HOT_WATER,
        "disinfection_duration",
        lambda device, value: device.hot_water.async_set_disinfection_duration(value),
        unit=UnitOfTime.MINUTES,
        device_class=NumberDeviceClass.DURATION,
    ),
    _temperature_setting(
        COMPONENT_HOT_WATER,
        "circulation_frost_temperature",
        lambda device, value: device.hot_water.async_set_circulation_frost_temperature(
            value
        ),
    ),
    _temperature_setting(
        COMPONENT_HOT_WATER,
        "frost_protection_temperature",
        lambda device, value: device.hot_water.async_set_frost_protection_temperature(
            value
        ),
        key="hot_water_frost_protection_temperature",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 Unused function argument: `hass`
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ECL setpoint numbers."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        Ecl310Number(coordinator, description) for description in NUMBERS
    )


class Ecl310Number(Ecl310Entity, NumberEntity):
    """One writable setpoint, bounded by the controller's own domain."""

    entity_description: Ecl310NumberDescription

    def __init__(
        self, coordinator: Ecl310Coordinator, description: Ecl310NumberDescription
    ) -> None:
        """Initialize the number entity from the datapoint metadata."""
        super().__init__(coordinator, description.key, description.component)
        self.entity_description = description

        number = self._subsystem.require_metadata_for(description.attribute).number
        if number is not None:
            if number.min_value is not None:
                self._attr_native_min_value = float(number.min_value)
            if number.max_value is not None:
                self._attr_native_max_value = float(number.max_value)
            if number.step is not None:
                self._attr_native_step = float(number.step)

    @property
    def native_value(self) -> float | None:
        """Return the setpoint currently stored in the controller."""
        return getattr(self._subsystem, self.entity_description.attribute)

    async def async_set_native_value(self, value: float) -> None:
        """Write a new setpoint."""
        await self.entity_description.set_fn(self.coordinator.device, value)
        await self.coordinator.async_request_refresh()
