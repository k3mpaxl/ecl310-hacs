"""Number platform - the setpoints that are not a thermostat setting.

Each entity takes its range, step and unit from the library's datapoint
metadata, so the bounds shown in the UI are the ones the controller accepts.
A setting with an "off" value outside that range - the disinfection
temperature - shows the value it had while it is off; the switch platform
turns it on and off.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, replace

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, Platform, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import COMPONENT_HEATING, COMPONENT_HOT_WATER, PARALLEL_FULL_ON
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus.subsystems.heating_circuit import CURVE_POINTS
from .entity import Ecl310Entity, per_circuit, supported
from .memory import start_value

PARALLEL_UPDATES = 1

INSTALLATION_NUMBERS = (
    ("pump_frost_threshold", UnitOfTemperature.CELSIUS, NumberDeviceClass.TEMPERATURE),
    ("pump_heat_threshold", UnitOfTemperature.CELSIUS, NumberDeviceClass.TEMPERATURE),
    ("valve_motor_protection", UnitOfTime.MINUTES, NumberDeviceClass.DURATION),
    ("valve_proportional_band", UnitOfTemperature.KELVIN, None),
    ("valve_integral_time", UnitOfTime.SECONDS, NumberDeviceClass.DURATION),
    ("valve_running_time", UnitOfTime.SECONDS, NumberDeviceClass.DURATION),
    ("valve_neutral_zone", UnitOfTemperature.KELVIN, None),
    ("valve_minimum_pulse", None, None),
)
SEASONAL_NUMBERS = (
    ("summer_start_month", None, None),
    ("summer_start_day", None, None),
    ("summer_filter", None, None),
    ("winter_start_month", None, None),
    ("winter_start_day", None, None),
    ("winter_cut_off", UnitOfTemperature.CELSIUS, NumberDeviceClass.TEMPERATURE),
    ("winter_filter", None, None),
)
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
    *(
        replace(
            _setting(
                component, name, key=f"{prefix}{name}", unit=unit, device_class=kind
            ),
            entity_registry_enabled_default=False,
        )
        for component, prefix, values in (
            (
                COMPONENT_HEATING,
                "",
                (*INSTALLATION_NUMBERS, *SEASONAL_NUMBERS),
            ),
            (COMPONENT_HOT_WATER, "hot_water_", INSTALLATION_NUMBERS),
        )
        for name, unit, kind in values
    ),
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
    replace(
        _setting(
            COMPONENT_HEATING, "parallel_operation", unit=UnitOfTemperature.KELVIN
        ),
        entity_registry_enabled_default=False,
    ),
    replace(
        _setting(COMPONENT_HEATING, "building_factor"),
        entity_registry_enabled_default=False,
    ),
    replace(
        _temperature_setting(COMPONENT_HEATING, "auto_saving"),
        entity_registry_enabled_default=False,
    ),
    replace(
        _setting(COMPONENT_HEATING, "heat_up_boost", unit="%"),
        entity_registry_enabled_default=False,
    ),
    replace(
        _setting(
            COMPONENT_HEATING,
            "ramp_time",
            unit=UnitOfTime.MINUTES,
            device_class=NumberDeviceClass.DURATION,
        ),
        entity_registry_enabled_default=False,
    ),
    *(
        replace(
            _setting(
                COMPONENT_HEATING,
                f"return_limit_{point}",
                unit=UnitOfTemperature.CELSIUS,
                device_class=NumberDeviceClass.TEMPERATURE,
            ),
            entity_registry_enabled_default=False,
        )
        for point in ("x1", "y1", "x2", "y2")
    ),
    *(
        replace(
            _setting(
                component,
                attribute,
                key=f"{prefix}{attribute}",
                unit=UnitOfTime.SECONDS
                if attribute.endswith("adaptation_time")
                else None,
                device_class=(
                    NumberDeviceClass.DURATION
                    if attribute.endswith("adaptation_time")
                    else None
                ),
            ),
            entity_registry_enabled_default=False,
        )
        for component, prefix in (
            (COMPONENT_HEATING, ""),
            (COMPONENT_HOT_WATER, "hot_water_"),
        )
        for attribute in (
            "return_limit_influence_max",
            "return_limit_influence_min",
            "return_limit_adaptation_time",
        )
    ),
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
    hass: HomeAssistant,
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ECL setpoint numbers."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        supported(
            hass,
            Platform.NUMBER,
            (
                Ecl310Number(coordinator, description)
                for description in per_circuit(coordinator.device, NUMBERS)
            ),
        )
    )


class Ecl310Number(Ecl310Entity, NumberEntity, RestoreEntity):
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
        self._off_value: float | None = None
        self._start_value: float | None = None

        number = self._metadata(description.attribute).number
        if number is not None:
            if number.off_value is not None:
                self._off_value = float(number.off_value)
            if number.min_value is not None:
                self._attr_native_min_value = float(number.min_value)
            if number.max_value is not None:
                self._attr_native_max_value = float(number.max_value)
            if number.step is not None:
                self._attr_native_step = float(number.step)
            self._start_value = start_value(number)
        if description.attribute == "parallel_operation":
            self._attr_native_min_value = 1
            self._attr_native_max_value = 99
            self._start_value = None
        #: Whether the controller can hold the setting at a value that is no setpoint.
        self._can_be_off = (
            self._off_value is not None or description.attribute == "parallel_operation"
        )

    def _is_off(self, value: float) -> bool:
        """Return whether the controller holds the setting at an off value."""
        if self.entity_description.attribute == "parallel_operation":
            return value in (0, PARALLEL_FULL_ON)
        return value == self._off_value

    def _remember(self) -> None:
        """Keep the setpoint for the time the setting is off."""
        if not self._can_be_off:
            return
        attribute = self.entity_description.attribute
        value = getattr(self._subsystem, attribute)
        if value is not None and not self._is_off(value):
            self.coordinator.memory.remember(self._component, attribute, value)

    async def async_added_to_hass(self) -> None:
        """Pick up the setpoint the setting had before the restart."""
        await super().async_added_to_hass()
        if not self._can_be_off:
            return
        attribute = self.entity_description.attribute
        memory = self.coordinator.memory
        if (
            memory.get(self._component, attribute) is None
            and (last := await self.async_get_last_state()) is not None
        ):
            with contextlib.suppress(ValueError):  # unknown or unavailable
                memory.remember(self._component, attribute, float(last.state))
        self._remember()

    def _handle_coordinator_update(self) -> None:
        self._remember()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float | None:
        """Return the setpoint stored in the controller, or its last one when off.

        The controller holds a setting that is switched off at a value of its
        own, which is no setpoint. The number then shows the value the setting
        had, or gets when it is switched on again; the switch says whether it
        is on. Setting the number writes the value, which switches it on.
        """
        attribute = self.entity_description.attribute
        value = getattr(self._subsystem, attribute)
        if value is None or not self._can_be_off or not self._is_off(value):
            return value
        remembered = self.coordinator.memory.get(self._component, attribute)
        if remembered is not None:
            return remembered
        if self._start_value is not None:
            return self._start_value
        return self.native_min_value

    async def async_set_native_value(self, value: float) -> None:
        """Write a new setpoint."""
        await self._async_write(
            self._subsystem.write(self.entity_description.attribute, value)
        )
        await self.coordinator.async_request_refresh()
