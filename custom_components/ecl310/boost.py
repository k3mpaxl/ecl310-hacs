"""One-off hot water boost: comfort until the tank reaches its setpoint.

Raising the hot water setpoint outside a comfort period of the weekly program
does nothing until the next one begins: the controller only charges the tank
in comfort. A boost puts hot water into constant comfort, watches the storage
temperature on S6, and puts the previous mode back once the tank reached the
setpoint - so "I want a hot shower now" is one tap, and the weekly program
carries on afterwards as if nothing happened.

A boost ends in one of four ways, each reported as an
``ecl310_hot_water_boost_finished`` event:

* ``reached``      the tank reached the setpoint; the previous mode is back
* ``timeout``      it did not within three hours; the previous mode is back
* ``cancelled``    the boost switch was turned off; the previous mode is back
* ``mode_changed`` someone chose another mode meanwhile; that choice stays

A running boost survives a restart of Home Assistant: it is stored, and picked
up again as long as the controller is still in comfort.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from modbus_connection import ModbusError

from .const import COMPONENT_HOT_WATER, DOMAIN, LOGGER
from .ecl310_modbus import OperatingMode

if TYPE_CHECKING:
    from collections.abc import Callable

    from .coordinator import Ecl310Coordinator

EVENT_BOOST_FINISHED = f"{DOMAIN}_hot_water_boost_finished"

RESULT_REACHED = "reached"
RESULT_TIMEOUT = "timeout"
RESULT_CANCELLED = "cancelled"
RESULT_MODE_CHANGED = "mode_changed"

#: Give up and put the previous mode back after this long.
BOOST_TIMEOUT = timedelta(hours=3)
#: With "boost on raise", a new setpoint starts a boost only when it is at
#: least this far above the tank - a raise the tank already meets needs none.
RAISE_MARGIN = 1.0
#: A written mode shows up in the controller's report within a poll or two;
#: only after this long does a mode other than comfort mean someone chose it.
MODE_SETTLE = timedelta(seconds=90)
#: The heating rate is too noisy to extrapolate from before this.
RATE_AFTER = timedelta(minutes=3)

STORAGE_VERSION = 1

#: The modes a boost may start from. Manual is the operator's, not ours.
BOOSTABLE_MODES = (
    OperatingMode.SCHEDULED,
    OperatingMode.SETBACK,
    OperatingMode.FROST_PROTECTION,
    OperatingMode.COMFORT,
)

#: The modes "boost on raise" may leave on its own. Frost protection is a
#: deliberate "off" - absence, holidays - and is only left by hand.
RAISE_BOOST_MODES = (OperatingMode.SCHEDULED, OperatingMode.SETBACK)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


@dataclass(slots=True)
class BoostSession:
    """A running boost."""

    started_at: datetime
    start_temperature: float | None
    target: float
    previous_mode: OperatingMode
    user_id: str | None
    mode_written_at: datetime

    def as_dict(self) -> dict[str, Any]:
        """Serialise for the store."""
        return {
            "started_at": self.started_at.isoformat(),
            "start_temperature": self.start_temperature,
            "target": self.target,
            "previous_mode": int(self.previous_mode),
            "user_id": self.user_id,
            "mode_written_at": self.mode_written_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BoostSession | None:
        """Read back from the store; None if the data is unusable."""
        try:
            return cls(
                started_at=dt_util.parse_datetime(data["started_at"]),
                start_temperature=data.get("start_temperature"),
                target=float(data["target"]),
                previous_mode=OperatingMode(int(data["previous_mode"])),
                user_id=data.get("user_id"),
                mode_written_at=dt_util.parse_datetime(data["mode_written_at"]),
            )
        except KeyError, TypeError, ValueError:
            return None


class HotWaterBoost:
    """Run one boost at a time for one controller."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: Ecl310Coordinator,
        store: Store | None = None,
    ) -> None:
        """Initialize; call ``async_load`` before use."""
        self.hass = hass
        self.coordinator = coordinator
        self.store = store
        self.session: BoostSession | None = None
        #: Start a boost when the setpoint is raised above the tank. Set by the
        #: configuration switch, which keeps the choice across restarts.
        self.on_raise = False
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []

    # -- Readings -------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Whether the controller has a hot water circuit to boost."""
        return hasattr(self.coordinator.device, COMPONENT_HOT_WATER)

    @property
    def storage_temperature(self) -> float | None:
        """The tank temperature on S6."""
        return getattr(self.coordinator.device.sensors, "storage_temperature", None)

    @property
    def mode(self) -> OperatingMode | None:
        """The hot water circuit's current operating mode."""
        return self.coordinator.device.hot_water.mode

    @property
    def elapsed(self) -> timedelta | None:
        """How long the running boost has been going."""
        if self.session is None:
            return None
        return dt_util.utcnow() - self.session.started_at

    @property
    def rate(self) -> float | None:
        """Heating rate of the tank since the boost began, in K per minute."""
        session, storage, elapsed = (
            self.session,
            self.storage_temperature,
            self.elapsed,
        )
        if (
            session is None
            or storage is None
            or session.start_temperature is None
            or elapsed is None
            or elapsed < RATE_AFTER
        ):
            return None
        rate = (storage - session.start_temperature) / (elapsed.total_seconds() / 60)
        return rate if rate > 0 else None

    @property
    def estimated_end(self) -> datetime | None:
        """When the tank should reach the setpoint at the current rate."""
        session, storage, rate = self.session, self.storage_temperature, self.rate
        if session is None or storage is None or rate is None:
            return None
        remaining = max(0.0, session.target - storage)
        return dt_util.utcnow() + timedelta(minutes=remaining / rate)

    # -- Listeners --------------------------------------------------------------

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        """Call ``update`` whenever a boost starts, progresses or ends."""
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def _notify(self) -> None:
        for update in tuple(self._listeners):
            update()

    # -- Lifecycle --------------------------------------------------------------

    async def async_load(self) -> None:
        """Pick a boost back up that was running before a restart."""
        if self.store is None:
            return
        data = await self.store.async_load() or {}
        stored = data.get("session")
        session = BoostSession.from_dict(stored) if stored else None
        if session is not None and self.mode is OperatingMode.COMFORT:
            self.session = session
            LOGGER.debug("Hot water boost resumed, target %.1f °C", session.target)
        elif session is not None:
            await self._async_save()

    async def _async_save(self) -> None:
        if self.store is not None:
            await self.store.async_save(
                {"session": self.session.as_dict() if self.session else None}
            )

    @callback
    def async_coordinator_updated(self) -> None:
        """Check the running boost after every poll."""
        if self.session is not None:
            self.hass.async_create_task(self.async_check())

    # -- Control ----------------------------------------------------------------

    async def async_start(self, user_id: str | None = None) -> None:
        """Put hot water into comfort until the tank reaches the setpoint."""
        async with self._lock:
            if self.session is not None:
                return
            mode = self.mode
            target = self.coordinator.device.hot_water.setpoint
            if mode not in BOOSTABLE_MODES or target is None:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="boost_not_possible",
                )
            now = dt_util.utcnow()
            self.session = BoostSession(
                started_at=now,
                start_temperature=_round(self.storage_temperature),
                target=target,
                previous_mode=mode,
                user_id=user_id,
                mode_written_at=now,
            )
            if mode is not OperatingMode.COMFORT:
                await self._async_write_mode(OperatingMode.COMFORT)
            await self._async_save()
        self._notify()
        await self.async_check()

    async def async_cancel(self) -> None:
        """Stop the running boost and put the previous mode back."""
        async with self._lock:
            if self.session is not None:
                await self._async_finish(RESULT_CANCELLED, restore=True)
        self._notify()

    async def async_setpoint_changed(
        self,
        setpoint: float,
        user_id: str | None,
        previous: float | None = None,
    ) -> None:
        """Follow a new setpoint, and start a boost on a raise if wanted.

        A raise is a setpoint higher than ``previous``: writing the value it
        already had - an automation lowering to where it already is - starts
        nothing, however far the tank has cooled meanwhile.
        """
        if self.session is not None:
            self.session.target = setpoint
            await self._async_save()
            await self.async_check()
            return
        storage = self.storage_temperature
        if (
            self.on_raise
            and previous is not None
            and setpoint > previous
            and storage is not None
            and setpoint >= storage + RAISE_MARGIN
            and self.mode in RAISE_BOOST_MODES
        ):
            await self.async_start(user_id)

    async def async_check(self) -> None:
        """End the boost when the tank is there, the time is up or the mode moved."""
        async with self._lock:
            session = self.session
            if session is None:
                return
            now = dt_util.utcnow()
            storage = self.storage_temperature
            if (
                self.mode is not OperatingMode.COMFORT
                and now - session.mode_written_at >= MODE_SETTLE
            ):
                await self._async_finish(RESULT_MODE_CHANGED, restore=False)
            elif storage is not None and storage >= session.target:
                await self._async_finish(RESULT_REACHED, restore=True)
            elif now - session.started_at >= BOOST_TIMEOUT:
                await self._async_finish(RESULT_TIMEOUT, restore=True)
        self._notify()

    async def _async_finish(self, result: str, *, restore: bool) -> None:
        """End the session, put the mode back if asked, and report it."""
        session = self.session
        if session is None:
            return
        self.session = None
        # The boost wrote comfort itself unless it started from comfort; the
        # polled mode may still lag behind that write, so it is not consulted.
        if restore and session.previous_mode is not OperatingMode.COMFORT:
            try:
                await self._async_write_mode(session.previous_mode)
            except HomeAssistantError as err:
                LOGGER.warning(
                    "Could not put hot water back to %s: %s",
                    session.previous_mode.name,
                    err,
                )
        await self._async_save()
        duration = dt_util.utcnow() - session.started_at
        self.hass.bus.async_fire(
            EVENT_BOOST_FINISHED,
            {
                "entry_id": self.coordinator.config_entry.entry_id,
                "result": result,
                "started_at": session.started_at.isoformat(),
                "duration_minutes": round(duration.total_seconds() / 60, 1),
                "start_temperature": session.start_temperature,
                "end_temperature": _round(self.storage_temperature),
                "target": session.target,
                "previous_mode": session.previous_mode.name.lower(),
                "user_id": session.user_id,
            },
        )
        LOGGER.debug("Hot water boost ended: %s after %s", result, duration)

    async def _async_write_mode(self, mode: OperatingMode) -> None:
        try:
            await self.coordinator.device.hot_water.async_set_mode(mode)
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="boost_write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_request_refresh()
