"""The domestic hot water circuit (ECL circuit 2).

The tank's two setpoints, the charging thresholds that decide when it is
loaded, the anti-bacteria run and the frost limits. Bounds are the
controller's own, from the application report for A237.1.

The anti-bacteria day is a bit mask over the week and its start time is
counted in half hours, both of which the ECL display hides behind a friendlier
editor. They are modelled as the controller stores them, with helpers that
turn them into weekdays and a clock time.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..data_model import (
    Ecl310Component,
    parameter_number,
    parameter_temperature,
    register_enum,
)
from ..enums import CircuitState, OperatingMode
from ..exceptions import Ecl310ValueValidationError

#: Register carrying the hot water circuit's operating mode.
MODE_REGISTER = 4201

#: Register carrying the hot water circuit's schedule status.
STATE_REGISTER = 4211


class HotWater(Ecl310Component):
    """Domestic hot water preparation and its disinfection function."""

    mode = register_enum(
        MODE_REGISTER,
        OperatingMode,
        writable=True,
        maker_key="Betriebsart",
        maker_category="circuit",
        description="Betriebsart der Warmwasserbereitung",
    )
    """The mode hot water preparation has been put into, and can be put into."""

    state = register_enum(
        STATE_REGISTER,
        CircuitState,
        maker_key="Kreislauf",
        maker_category="circuit",
        description="Aktueller Status der Warmwasserbereitung im Wochenprogramm",
    )
    """Where hot water preparation sits within its weekly program."""

    setpoint = parameter_temperature(
        12190,
        0.1,
        min_value=40,
        max_value=65,
        raw_min=400,
        raw_max=650,
        writable=True,
        maker_key="Gew. Temp.",
        description="Gewünschte Warmwassertemperatur",
    )
    """Desired hot water temperature."""

    disinfection_temperature = parameter_temperature(
        12125,
        1,
        min_value=55,
        max_value=75,
        raw_min=55,
        raw_max=75,
        writable=True,
        maker_key="Gew. Temp. (Desinfektion)",
        description="Warmwassertemperatur während der Legionellenschaltung",
    )
    """Temperature the tank is raised to by the disinfection function."""

    setback_setpoint = parameter_temperature(
        12191,
        0.1,
        min_value=10,
        max_value=65,
        raw_min=100,
        raw_max=650,
        writable=True,
        maker_key="Sparen Temp. / Saving DHW T",
        description="Gewünschte Warmwassertemperatur im Absenkbetrieb",
    )
    """Desired hot water temperature during setback periods."""

    return_limit = parameter_temperature(
        12030,
        1,
        min_value=10,
        max_value=110,
        raw_min=10,
        raw_max=110,
        writable=True,
        maker_key="Grenze / Limit",
        description="Rücklauftemperatur, ab der die Ladung zurückgenommen wird",
    )
    """Return temperature above which the controller throttles charging."""

    max_charge_temperature = parameter_temperature(
        12152,
        1,
        min_value=10,
        max_value=110,
        raw_min=10,
        raw_max=110,
        writable=True,
        maker_key="Max. Ladetemp. / Max. charge T",
        description="Obere Grenze der Ladetemperatur des Speichers",
    )
    """Upper limit for the temperature the tank is charged with."""

    charge_difference = parameter_number(
        12193,
        1,
        min_value=1,
        max_value=50,
        raw_min=1,
        raw_max=50,
        step=1,
        digits=0,
        unit="K",
        writable=True,
        maker_key="Ladedifferenz / Charge difference",
        maker_category="circuit",
        description=(
            "Wie weit die Ladetemperatur über der gewünschten "
            "Warmwassertemperatur liegt"
        ),
    )
    """How far above the setpoint the tank is charged."""

    start_difference = parameter_number(
        12195,
        1,
        min_value=-50,
        max_value=-1,
        raw_min=-50,
        raw_max=-1,
        step=1,
        digits=0,
        unit="K",
        writable=True,
        maker_key="Startdifferenz / Start difference",
        maker_category="circuit",
        description=(
            "Wie weit der Speicher unter den Sollwert fallen darf, bevor "
            "geladen wird; immer negativ"
        ),
    )
    """How far the tank may drop below the setpoint before charging starts."""

    stop_difference = parameter_number(
        12194,
        1,
        min_value=-50,
        max_value=50,
        raw_min=-50,
        raw_max=50,
        step=1,
        digits=0,
        unit="K",
        writable=True,
        maker_key="Stoppdifferenz / Stop difference",
        maker_category="circuit",
        description="Wie weit über den Sollwert geladen wird, bevor gestoppt wird",
    )
    """How far past the setpoint charging continues before it stops."""

    disinfection_days = parameter_number(
        12122,
        1,
        min_value=0,
        max_value=127,
        raw_min=0,
        raw_max=127,
        step=1,
        digits=0,
        writable=True,
        maker_key="Tag / Day",
        maker_category="circuit",
        description=(
            "Wochentage der Legionellenschaltung als Bitmaske, Bit 0 = Montag; 0 = aus"
        ),
    )
    """Weekdays the disinfection run happens on, as a bit mask."""

    disinfection_start = parameter_number(
        12123,
        1,
        min_value=0,
        max_value=47,
        raw_min=0,
        raw_max=47,
        step=1,
        digits=0,
        writable=True,
        maker_key="Startzeit / Start time",
        maker_category="circuit",
        description="Startzeit der Legionellenschaltung in halben Stunden ab 00:00",
    )
    """When the disinfection run starts, counted in half hours from midnight."""

    disinfection_duration = parameter_number(
        12124,
        1,
        min_value=10,
        max_value=600,
        raw_min=10,
        raw_max=600,
        step=10,
        digits=0,
        unit="min",
        writable=True,
        maker_key="Dauer / Duration",
        maker_category="circuit",
        description="Dauer der Legionellenschaltung",
    )
    """How long the disinfection run holds the tank at its temperature."""

    circulation_frost_temperature = parameter_temperature(
        12076,
        1,
        min_value=-11,
        max_value=20,
        raw_min=-11,
        raw_max=20,
        writable=True,
        maker_key="Zirk. P Frost T / Circ. P frost T",
        description=(
            "Außentemperatur, unter der die Zirkulationspumpe zum Frostschutz läuft"
        ),
    )
    """Outdoor temperature below which the circulation pump runs for frost."""

    frost_protection_temperature = parameter_temperature(
        12093,
        1,
        min_value=5,
        max_value=40,
        raw_min=5,
        raw_max=40,
        writable=True,
        maker_key="Frostschutztemp. / Frost pr. T",
        description="Temperatur, die der Frostschutz im Warmwasserkreis hält",
    )
    """Temperature frost protection holds in the hot water circuit."""

    @property
    def disinfection_weekdays(self) -> tuple[int, ...] | None:
        """The weekdays disinfection runs on, ``0`` Monday .. ``6`` Sunday."""
        mask = self.disinfection_days
        if mask is None:
            return None
        return tuple(day for day in range(7) if int(mask) & (1 << day))

    @property
    def disinfection_start_time(self) -> tuple[int, int] | None:
        """The disinfection start as ``(hour, minute)``."""
        slots = self.disinfection_start
        if slots is None:
            return None
        return (int(slots) // 2, 30 * (int(slots) % 2))

    async def async_set_disinfection_weekdays(self, days: Iterable[int]) -> None:
        """Write the disinfection weekdays, ``0`` Monday .. ``6`` Sunday."""
        mask = 0
        for day in days:
            if not 0 <= day <= 6:
                raise Ecl310ValueValidationError(f"Expected a weekday 0..6, got {day}")
            mask |= 1 << day
        await self.write("disinfection_days", mask)

    async def async_set_disinfection_start_time(
        self, hour: int, minute: int = 0
    ) -> None:
        """Write the disinfection start time, on a half-hour boundary."""
        if not 0 <= hour <= 23 or minute not in (0, 30):
            raise Ecl310ValueValidationError(
                f"Expected a half hour of the day, got {hour:02d}:{minute:02d}"
            )
        await self.write("disinfection_start", hour * 2 + (1 if minute else 0))

    @property
    def charging(self) -> bool | None:
        """Whether the tank is in one of its charging states."""
        if self.state is None:
            return None
        return self.state in (CircuitState.PRE_COMFORT, CircuitState.COMFORT)

    async def async_set_mode(self, mode: OperatingMode) -> None:
        """Write the hot water operating mode."""
        await self.write("mode", mode)

    async def async_set_setpoint(self, value: float) -> None:
        """Write the hot water setpoint."""
        await self.write("setpoint", value)

    async def async_set_disinfection_temperature(self, value: float) -> None:
        """Write the disinfection temperature."""
        await self.write("disinfection_temperature", value)

    async def async_set_setback_setpoint(self, value: float) -> None:
        """Write the setback hot water setpoint."""
        await self.write("setback_setpoint", value)

    async def async_set_return_limit(self, value: float) -> None:
        """Write the return temperature limit."""
        await self.write("return_limit", value)

    async def async_set_max_charge_temperature(self, value: float) -> None:
        """Write the upper charging temperature."""
        await self.write("max_charge_temperature", value)

    async def async_set_charge_difference(self, value: float) -> None:
        """Write how far above the setpoint the tank is charged."""
        await self.write("charge_difference", value)

    async def async_set_start_difference(self, value: float) -> None:
        """Write how far the tank may drop before charging starts."""
        await self.write("start_difference", value)

    async def async_set_stop_difference(self, value: float) -> None:
        """Write how far past the setpoint charging continues."""
        await self.write("stop_difference", value)

    async def async_set_disinfection_duration(self, value: float) -> None:
        """Write the disinfection duration."""
        await self.write("disinfection_duration", value)

    async def async_set_circulation_frost_temperature(self, value: float) -> None:
        """Write the circulation pump's frost protection temperature."""
        await self.write("circulation_frost_temperature", value)

    async def async_set_frost_protection_temperature(self, value: float) -> None:
        """Write the hot water frost protection temperature."""
        await self.write("frost_protection_temperature", value)
