"""Switch platform - the settings that really are two-valued.

Forcing a pump looks like a switch but is not one: the controller's override
register has three positions, the third being "hand it back to the
regulation", so the pumps are on the select platform instead.

The anti-bacteria weekdays are one register holding a seven-bit mask, which is
seven switches here. Changing one is a read-modify-write of that register, so
the coordinator's mask lock serialises them and each re-reads the mask from the
controller first: a scene that sets several days at once loses none of them.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .boost import HotWaterBoost
from .const import COMPONENT_HEATING, COMPONENT_HOT_WATER
from .coordinator import Ecl310ConfigEntry, Ecl310Coordinator
from .ecl310_modbus import Circuit, Ecl310Component, HeatingCircuit, HotWater
from .ecl310_modbus.enums import Weekday
from .entity import Ecl310Entity, circuit_key, per_circuit, supported

PARALLEL_UPDATES = 1

#: Where the disinfection switch keeps the temperature turning it on sets.
ATTR_TEMPERATURE_WHEN_ON = "temperature_when_on"
OPTIONAL_HEATING_SETTINGS = (
    ("building_factor", 9, 10),
    ("auto_saving", -30, -29),
    ("heat_up_boost", 0, 1),
    ("ramp_time", 0, 1),
)

#: The attribute-name fragment each weekday is exposed under.
WEEKDAY_KEYS: tuple[str, ...] = tuple(day.name.lower() for day in Weekday)


@dataclass(frozen=True, kw_only=True)
class Ecl310SwitchDescription(SwitchEntityDescription):
    """Describes a switch reading and writing one datapoint."""

    component: str
    field: str
    value_fn: Callable[[Ecl310Component], bool | None]
    set_fn: Callable[[Ecl310Coordinator, Ecl310Component, bool], Awaitable[None]]


def _disinfection_day(day: int) -> Ecl310SwitchDescription:
    """Describe one weekday of the anti-bacteria run."""
    name = WEEKDAY_KEYS[day]
    return Ecl310SwitchDescription(
        key=f"disinfection_{name}",
        translation_key=f"disinfection_{name}",
        component=COMPONENT_HOT_WATER,
        field="disinfection_days",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda water, index=day: _day_is_set(water, index),
        set_fn=lambda coordinator, water, on, index=day: _set_day(
            coordinator, water, index, on=on
        ),
    )


def _day_is_set(water: Ecl310Component, day: int) -> bool | None:
    """Return whether the anti-bacteria run covers one weekday."""
    days = cast(HotWater, water).disinfection_weekdays
    return None if days is None else day in days


async def _set_day(
    coordinator: Ecl310Coordinator, water: Ecl310Component, day: int, *, on: bool
) -> None:
    """Add or remove one weekday from the anti-bacteria run.

    The other six days come from a fresh read of the mask rather than from the
    last poll, under a lock, so concurrent changes to different days all land.
    """
    water = cast(HotWater, water)
    async with coordinator.mask_lock:
        await water.async_update(notify=False)
        days = set(water.disinfection_weekdays or ())
        days.add(day) if on else days.discard(day)
        await water.async_set_disinfection_weekdays(sorted(days))


SWITCHES: tuple[Ecl310SwitchDescription, ...] = (
    Ecl310SwitchDescription(
        key="optimised_stop",
        translation_key="optimised_stop",
        component=COMPONENT_HEATING,
        field="optimised_stop",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        value_fn=lambda circuit: cast(HeatingCircuit, circuit).optimised_stop,
        set_fn=lambda _coordinator, circuit, on: circuit.write("optimised_stop", on),
    ),
    Ecl310SwitchDescription(
        key="return_limit_priority",
        translation_key="return_limit_priority",
        component=COMPONENT_HEATING,
        field="return_limit_priority",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        value_fn=lambda circuit: cast(HeatingCircuit, circuit).return_limit_priority,
        set_fn=lambda _coordinator, circuit, on: circuit.write(
            "return_limit_priority", on
        ),
    ),
    Ecl310SwitchDescription(
        key="pump_off_in_setback",
        translation_key="pump_off_in_setback",
        component=COMPONENT_HEATING,
        field="pump_off_in_setback",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda circuit: cast(HeatingCircuit, circuit).pump_off_in_setback,
        set_fn=lambda _coordinator, circuit, on: cast(
            HeatingCircuit, circuit
        ).async_set_pump_off_in_setback(on),
    ),
    Ecl310SwitchDescription(
        key="hot_water_priority",
        translation_key="hot_water_priority",
        component=COMPONENT_HEATING,
        field="hot_water_priority",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda circuit: cast(HeatingCircuit, circuit).hot_water_priority,
        set_fn=lambda _coordinator, circuit, on: cast(
            HeatingCircuit, circuit
        ).async_set_hot_water_priority(on),
    ),
    *(_disinfection_day(day) for day in range(7)),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Ecl310ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ECL switches."""
    coordinator = entry.runtime_data.coordinator
    boost = entry.runtime_data.boost
    async_add_entities(
        supported(
            hass,
            Platform.SWITCH,
            [
                *(
                    Ecl310Switch(coordinator, description)
                    for description in per_circuit(coordinator.device, SWITCHES)
                ),
                *(
                    Ecl310DisinfectionSwitch(coordinator, circuit)
                    for circuit in coordinator.device.circuits
                    if circuit.kind == COMPONENT_HOT_WATER
                ),
                *(
                    Ecl310OptionalSettingSwitch(
                        coordinator, circuit, setting, off, default
                    )
                    for circuit in coordinator.device.circuits
                    if circuit.kind == COMPONENT_HEATING
                    for setting, off, default in OPTIONAL_HEATING_SETTINGS
                ),
                *(
                    [
                        Ecl310BoostSwitch(coordinator, boost),
                        Ecl310BoostOnRaiseSwitch(coordinator, boost),
                    ]
                    if boost.available
                    else []
                ),
            ],
        )
    )


class Ecl310OptionalSettingSwitch(Ecl310Entity, SwitchEntity, RestoreEntity):
    """Enable a setting using its last active numeric value."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: Ecl310Coordinator,
        circuit: Circuit,
        setting: str,
        off: int,
        default: int,
    ) -> None:
        """Attach the switch to its heating circuit and setting."""
        key = f"{setting}_enabled"
        super().__init__(
            coordinator,
            circuit_key(key, circuit),
            circuit.component,
            (setting,),
        )
        self._attr_translation_key = key
        self._setting, self._off, self._default = setting, off, default
        self._last_value: float | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last active value after a restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._last_value = last.attributes.get("last_value")
        self._remember()

    def _remember(self) -> None:
        value = getattr(self._subsystem, self._setting)
        if value is not None and value != self._off:
            self._last_value = value

    def _handle_coordinator_update(self) -> None:
        self._remember()
        super()._handle_coordinator_update()

    @property
    def is_on(self) -> bool | None:
        """Report whether the setting is active."""
        value = getattr(self._subsystem, self._setting)
        return None if value is None else value != self._off

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the value to restore and the register identity."""
        return {
            **(super().extra_state_attributes or {}),
            "last_value": self._last_value,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Restore the most recently active value."""
        await self._async_write(
            self._subsystem.write(
                self._setting,
                self._last_value if self._last_value is not None else self._default,
            )
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Store the value and switch the setting off."""
        self._remember()
        await self._async_write(self._subsystem.write(self._setting, self._off))
        await self.coordinator.async_request_refresh()


class Ecl310DisinfectionSwitch(Ecl310Entity, SwitchEntity, RestoreEntity):
    """Whether the disinfection function has a temperature to run at.

    The controller switches the disinfection off by storing its "off" value
    in place of the temperature, so turning it back on needs a temperature:
    the one it last had, or the library's default.
    """

    _attr_translation_key = "disinfection"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bacteria-outline"

    def __init__(self, coordinator: Ecl310Coordinator, circuit: Circuit) -> None:
        """Initialize the switch on the hot water device."""
        super().__init__(
            coordinator,
            circuit_key("disinfection", circuit),
            circuit.component,
            ("disinfection_temperature",),
        )
        self._temperature: float | None = None

    @property
    def _water(self) -> HotWater:
        return cast(HotWater, self._subsystem)

    async def async_added_to_hass(self) -> None:
        """Pick up the temperature it ran at before the restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._temperature = last.attributes.get(ATTR_TEMPERATURE_WHEN_ON)
        self._remember()

    def _remember(self) -> None:
        setpoint = self._water.disinfection_setpoint
        if setpoint is not None:
            self._temperature = setpoint

    def _handle_coordinator_update(self) -> None:
        self._remember()
        super()._handle_coordinator_update()

    @property
    def is_on(self) -> bool | None:
        """Return whether the disinfection is switched on."""
        return self._water.disinfection_enabled

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The temperature turning it on will set, and where it lives."""
        return {
            **(super().extra_state_attributes or {}),
            ATTR_TEMPERATURE_WHEN_ON: self._temperature,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Switch it on at the temperature it last had."""
        await self._async_write(
            self._water.async_set_disinfection_enabled(
                enabled=True, temperature=self._temperature
            )
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Switch it off."""
        await self._async_write(
            self._water.async_set_disinfection_enabled(enabled=False)
        )
        await self.coordinator.async_request_refresh()


class Ecl310BoostSwitch(Ecl310Entity, SwitchEntity):
    """Heat the tank to its setpoint once, then go back to the previous mode."""

    _shows_datapoints = False

    _attr_translation_key = "hot_water_boost"
    _attr_icon = "mdi:water-boiler-alert"

    def __init__(self, coordinator: Ecl310Coordinator, boost: HotWaterBoost) -> None:
        """Initialize the switch on the hot water device."""
        super().__init__(
            coordinator, "hot_water_boost", COMPONENT_HOT_WATER, ("mode", "setpoint")
        )
        self._boost = boost

    async def async_added_to_hass(self) -> None:
        """Follow the boost as it starts, progresses and ends."""
        await super().async_added_to_hass()
        self.async_on_remove(self._boost.async_add_listener(self.async_write_ha_state))

    @property
    def is_on(self) -> bool:
        """Return whether a boost is running."""
        return self._boost.session is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Describe the running boost."""
        session = self._boost.session
        if session is None:
            return {}
        rate = self._boost.rate
        end = self._boost.estimated_end
        return {
            "started_at": session.started_at.isoformat(),
            "start_temperature": session.start_temperature,
            "target_temperature": session.target,
            "previous_mode": session.previous_mode.name.lower(),
            "rate": None if rate is None else round(rate, 2),
            "estimated_end": None if end is None else end.isoformat(),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Start a boost, remembering who asked."""
        context = self._context
        await self._boost.async_start(context.user_id if context else None)

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Stop the boost and put the previous mode back."""
        await self._boost.async_cancel()


class Ecl310BoostOnRaiseSwitch(Ecl310Entity, SwitchEntity, RestoreEntity):
    """Start a boost whenever the hot water setpoint is raised above the tank."""

    _shows_datapoints = False

    _attr_translation_key = "hot_water_boost_on_raise"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:thermometer-chevron-up"

    def __init__(self, coordinator: Ecl310Coordinator, boost: HotWaterBoost) -> None:
        """Initialize the setting on the hot water device."""
        super().__init__(coordinator, "hot_water_boost_on_raise", COMPONENT_HOT_WATER)
        self._boost = boost

    async def async_added_to_hass(self) -> None:
        """Restore the choice made before the restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._boost.on_raise = last.state == "on"

    @property
    def available(self) -> bool:
        """A setting of this integration, so always available."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether raising the setpoint starts a boost."""
        return self._boost.on_raise

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Start boosts on a raised setpoint."""
        self._boost.on_raise = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Leave a raised setpoint to the weekly program."""
        self._boost.on_raise = False
        self.async_write_ha_state()


class Ecl310Switch(Ecl310Entity, SwitchEntity):
    """One on/off datapoint."""

    entity_description: Ecl310SwitchDescription

    def __init__(
        self, coordinator: Ecl310Coordinator, description: Ecl310SwitchDescription
    ) -> None:
        """Initialize the switch."""
        super().__init__(
            coordinator, description.key, description.component, (description.field,)
        )
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return whether the datapoint is on."""
        return self.entity_description.value_fn(self._subsystem)

    async def async_turn_on(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Switch it on."""
        await self._async_set(on=True)

    async def async_turn_off(self, **kwargs: Any) -> None:  # noqa: ARG002
        """Switch it off."""
        await self._async_set(on=False)

    async def _async_set(self, *, on: bool) -> None:
        """Write the value and refresh so the state reflects the controller."""
        await self._async_write(
            self.entity_description.set_fn(self.coordinator, self._subsystem, on)
        )
        await self.coordinator.async_request_refresh()
