"""Number platform - the setpoints that are not a thermostat setting.

Each entity takes its range, step and unit from the library's datapoint
metadata, so the bounds shown in the UI are the ones the controller accepts.
"""

from __future__ import annotations

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
from .ecl310_modbus.subsystems.heating_circuit import CURVE_POINTS
from .entity import Ecl310Entity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class Ecl310NumberDescription(NumberEntityDescription):
    """Describes a writable numeric datapoint.

    The entity writes ``attribute`` on its sub-system directly: the library
    validates the value against the datapoint's own domain, so there is no
    setter to name here.
    """

    component: str
    attribute: str


def _setting(
    component: str,
    attribute: str,
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
        device_class=device_class,
        native_unit_of_measurement=unit,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    )


def _temperature_setting(
    component: str, attribute: str, *, key: str | None = None
) -> Ecl310NumberDescription:
    """Describe a writable temperature setting."""
    return _setting(
        component,
        attribute,
        key=key,
        unit=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
    )


NUMBERS: tuple[Ecl310NumberDescription, ...] = (
    _temperature_setting(COMPONENT_HEATING, "setback_setpoint"),
    _temperature_setting(COMPONENT_HEATING, "summer_cut_off"),
    _temperature_setting(COMPONENT_HEATING, "min_flow_temperature"),
    _temperature_setting(COMPONENT_HEATING, "max_flow_temperature"),
    _temperature_setting(COMPONENT_HOT_WATER, "disinfection_temperature"),
    # --- the heat curve and its six points ---------------------------------
    _setting(COMPONENT_HEATING, "heat_curve"),
    *(
        _temperature_setting(COMPONENT_HEATING, attribute)
        for attribute in CURVE_POINTS.values()
    ),
    # --- the remaining heating settings ------------------------------------
    _temperature_setting(COMPONENT_HEATING, "return_limit", key="heating_return_limit"),
    _temperature_setting(
        COMPONENT_HEATING,
        "frost_protection_temperature",
        key="heating_frost_protection_temperature",
    ),
    _setting(
        COMPONENT_HEATING,
        "pump_post_run",
        unit=UnitOfTime.MINUTES,
        device_class=NumberDeviceClass.DURATION,
    ),
    # --- hot water ---------------------------------------------------------
    _temperature_setting(
        COMPONENT_HOT_WATER, "setback_setpoint", key="hot_water_setback_setpoint"
    ),
    _temperature_setting(
        COMPONENT_HOT_WATER, "return_limit", key="hot_water_return_limit"
    ),
    _temperature_setting(COMPONENT_HOT_WATER, "max_charge_temperature"),
    _setting(COMPONENT_HOT_WATER, "charge_difference", unit=UnitOfTemperature.KELVIN),
    _setting(COMPONENT_HOT_WATER, "start_difference", unit=UnitOfTemperature.KELVIN),
    _setting(COMPONENT_HOT_WATER, "stop_difference", unit=UnitOfTemperature.KELVIN),
    _setting(
        COMPONENT_HOT_WATER,
        "disinfection_duration",
        unit=UnitOfTime.MINUTES,
        device_class=NumberDeviceClass.DURATION,
    ),
    _temperature_setting(COMPONENT_HOT_WATER, "circulation_frost_temperature"),
    _temperature_setting(
        COMPONENT_HOT_WATER,
        "frost_protection_temperature",
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
        super().__init__(
            coordinator,
            description.key,
            description.component,
            (description.attribute,),
        )
        self.entity_description = description

        number = self._metadata(description.attribute).number
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
        await self._async_write(
            self._subsystem.write(self.entity_description.attribute, value)
        )
        await self.coordinator.async_request_refresh()
