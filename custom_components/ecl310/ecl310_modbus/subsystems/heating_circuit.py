"""The space heating circuit (ECL circuit 1).

Everything the circuit is told to do - its mode, its two room setpoints, the
heat curve, the summer cut-off, the flow and return temperature limits and the
pump settings - together with the status the controller derives from its
weekly program.

The bounds on each field are the controller's own, from the application
report for A237.1: it refuses anything outside them, whatever a user interface
offers. Where a narrower bound is deliberate rather than the controller's, the
field says so.
"""

from __future__ import annotations

from modbus_connection.model import NumberField

from ..data_model import (
    Ecl310Component,
    parameter_number,
    parameter_switch,
    parameter_temperature,
    register_enum,
)
from ..enums import CircuitState, OperatingMode
from ..exceptions import Ecl310ValueValidationError

#: Register carrying the heating circuit's operating mode.
MODE_REGISTER = 4200

#: Register carrying the heating circuit's schedule status.
STATE_REGISTER = 4210

#: The outdoor temperature each heat curve point Y1..Y6 stands for, and the
#: field that carries it. The ECL names them Y1..Y6 and prints the outdoor
#: temperatures only in the manual's curve diagram.
CURVE_POINTS: dict[int, str] = {
    -30: "curve_at_minus_30",
    -15: "curve_at_minus_15",
    -5: "curve_at_minus_5",
    0: "curve_at_0",
    5: "curve_at_5",
    15: "curve_at_15",
}


def _curve_point(parameter_id: int, outdoor: int) -> NumberField[float]:
    """Declare one heat curve point."""
    return parameter_temperature(
        parameter_id,
        1,
        min_value=10,
        max_value=110,
        raw_min=10,
        raw_max=250,
        writable=True,
        maker_key=f"Y{[-30, -15, -5, 0, 5, 15].index(outdoor) + 1}",
        description=(
            f"Vorlauftemperatur der Heizkurve bei {outdoor} °C Außentemperatur"
        ),
    )


class HeatingCircuit(Ecl310Component):
    """The weather-compensated space heating circuit."""

    mode = register_enum(
        MODE_REGISTER,
        OperatingMode,
        writable=True,
        maker_key="Betriebsart",
        maker_category="circuit",
        description="Betriebsart des Heizkreises",
    )
    """The mode the circuit has been put into, and can be put into."""

    state = register_enum(
        STATE_REGISTER,
        CircuitState,
        maker_key="Kreislauf",
        maker_category="circuit",
        description="Aktueller Status des Heizkreises im Wochenprogramm",
    )
    """Where the circuit sits within its weekly program."""

    comfort_setpoint = parameter_temperature(
        11180,
        0.1,
        min_value=5,
        max_value=40,
        raw_min=50,
        raw_max=400,
        writable=True,
        maker_key="Komforttemperatur",
        description="Gewünschte Raumtemperatur im Komfortbetrieb",
    )
    """Desired room temperature during comfort periods."""

    setback_setpoint = parameter_temperature(
        11181,
        0.1,
        min_value=5,
        max_value=40,
        raw_min=50,
        raw_max=400,
        writable=True,
        maker_key="Absenktemperatur",
        description="Gewünschte Raumtemperatur im Absenkbetrieb",
    )
    """Desired room temperature during setback periods."""

    summer_cut_off = parameter_temperature(
        11179,
        1,
        min_value=0,
        max_value=50,
        raw_min=0,
        raw_max=50,
        writable=True,
        maker_key="Sommer-Aus / Summer, cut-out",
        description=("Außentemperatur, ab der die Heizung abgeschaltet wird; 0 = AUS"),
    )
    """Outdoor temperature above which the circuit stops heating.

    ``0`` is the controller's ``OFF`` setting. The upper bound is 50 °C: the
    controller rejects anything above it, whatever a user interface offers.
    """

    min_flow_temperature = parameter_temperature(
        11177,
        1,
        min_value=10,
        max_value=80,
        raw_min=10,
        raw_max=80,
        writable=True,
        maker_key="Min. Temperatur",
        description="Untere Begrenzung der Vorlauftemperatur",
    )
    """Lower limit the flow temperature is held at."""

    max_flow_temperature = parameter_temperature(
        11178,
        1,
        min_value=10,
        max_value=80,
        raw_min=10,
        raw_max=80,
        writable=True,
        maker_key="Max. Temperatur",
        description="Obere Begrenzung der Vorlauftemperatur",
    )
    """Upper limit the flow temperature is held at."""

    pump_off_in_setback = parameter_switch(
        11021,
        writable=True,
        maker_key="Pumpe HK Aus / Total stop",
        maker_category="circuit",
        description="Zirkulationspumpe im Absenkbetrieb automatisch abschalten",
    )
    """Whether the circulation pump is switched off during setback."""

    heat_curve = parameter_number(
        11175,
        0.1,
        min_value=0.1,
        max_value=4.0,
        raw_min=1,
        raw_max=40,
        step=0.1,
        digits=1,
        writable=True,
        maker_key="Heizkurve / Heat curve",
        maker_category="circuit",
        description=(
            "Steilheit der Heizkurve; die sechs Stützpunkte Y1..Y6 verschieben "
            "sie punktweise"
        ),
    )
    """Slope of the weather compensation curve."""

    curve_at_minus_30 = _curve_point(11400, -30)
    """Flow temperature the curve asks for at -30 °C outdoor."""

    curve_at_minus_15 = _curve_point(11401, -15)
    """Flow temperature the curve asks for at -15 °C outdoor."""

    curve_at_minus_5 = _curve_point(11402, -5)
    """Flow temperature the curve asks for at -5 °C outdoor."""

    curve_at_0 = _curve_point(11403, 0)
    """Flow temperature the curve asks for at 0 °C outdoor."""

    curve_at_5 = _curve_point(11404, 5)
    """Flow temperature the curve asks for at 5 °C outdoor."""

    curve_at_15 = _curve_point(11405, 15)
    """Flow temperature the curve asks for at 15 °C outdoor."""

    return_limit = parameter_temperature(
        11028,
        1,
        min_value=10,
        max_value=110,
        raw_min=10,
        raw_max=110,
        writable=True,
        maker_key="Grenze / Con. T, ret. T lim.",
        description=("Rücklauftemperatur, ab der die Regelung den Vorlauf zurücknimmt"),
    )
    """Return temperature above which the controller throttles the flow."""

    frost_protection_temperature = parameter_temperature(
        11093,
        1,
        min_value=5,
        max_value=40,
        raw_min=5,
        raw_max=40,
        writable=True,
        maker_key="Frostschutztemp. / Frost pr. T",
        description="Vorlauftemperatur, die der Frostschutz hält",
    )
    """Flow temperature frost protection holds."""

    pump_post_run = parameter_number(
        11040,
        1,
        min_value=0,
        max_value=99,
        raw_min=0,
        raw_max=99,
        step=1,
        digits=0,
        unit="min",
        writable=True,
        maker_key="P Nachlauf / P post-run",
        maker_category="circuit",
        description="Nachlaufzeit der Umwälzpumpe nach dem Abschalten",
    )
    """How long the circulation pump keeps running after the circuit stops."""

    hot_water_priority = parameter_switch(
        11052,
        writable=True,
        maker_key="WW-Vorrang / DHW priority",
        maker_category="circuit",
        description=(
            "Heizkreis während der Warmwasserbereitung schließen "
            "(Vorrang für das Warmwasser)"
        ),
    )
    """Whether hot water preparation closes the heating circuit."""

    @property
    def heating(self) -> bool | None:
        """Whether the circuit is in one of its heating states."""
        if self.state is None:
            return None
        return self.state in (CircuitState.PRE_COMFORT, CircuitState.COMFORT)

    @property
    def active_setpoint(self) -> float | None:
        """The room setpoint the current circuit status applies."""
        if self.state is None:
            return None
        if self.state in (CircuitState.PRE_COMFORT, CircuitState.COMFORT):
            return self.comfort_setpoint
        return self.setback_setpoint

    async def async_set_mode(self, mode: OperatingMode) -> None:
        """Write the circuit's operating mode."""
        await self.write("mode", mode)

    async def async_set_comfort_setpoint(self, value: float) -> None:
        """Write the comfort room setpoint."""
        await self.write("comfort_setpoint", value)

    async def async_set_setback_setpoint(self, value: float) -> None:
        """Write the setback room setpoint."""
        await self.write("setback_setpoint", value)

    async def async_set_summer_cut_off(self, value: float) -> None:
        """Write the summer cut-off temperature."""
        await self.write("summer_cut_off", value)

    async def async_set_min_flow_temperature(self, value: float) -> None:
        """Write the lower flow temperature limit."""
        await self.write("min_flow_temperature", value)

    async def async_set_max_flow_temperature(self, value: float) -> None:
        """Write the upper flow temperature limit."""
        await self.write("max_flow_temperature", value)

    async def async_set_pump_off_in_setback(self, value: bool) -> None:
        """Write the automatic pump shutdown setting."""
        await self.write("pump_off_in_setback", value)

    async def async_set_heat_curve(self, value: float) -> None:
        """Write the heat curve slope."""
        await self.write("heat_curve", value)

    async def async_set_curve_point(self, outdoor: int, value: float) -> None:
        """Write one heat curve point, named by its outdoor temperature."""
        if outdoor not in CURVE_POINTS:
            raise Ecl310ValueValidationError(
                f"Expected one of {sorted(CURVE_POINTS)} °C, got {outdoor}"
            )
        await self.write(CURVE_POINTS[outdoor], value)

    async def async_set_return_limit(self, value: float) -> None:
        """Write the return temperature limit."""
        await self.write("return_limit", value)

    async def async_set_frost_protection_temperature(self, value: float) -> None:
        """Write the frost protection flow temperature."""
        await self.write("frost_protection_temperature", value)

    async def async_set_pump_post_run(self, value: float) -> None:
        """Write the pump post-run time."""
        await self.write("pump_post_run", value)

    async def async_set_hot_water_priority(self, value: bool) -> None:
        """Write whether hot water preparation closes this circuit."""
        await self.write("hot_water_priority", value)

    @property
    def curve_points(self) -> dict[int, float | None]:
        """The six curve points, keyed by their outdoor temperature."""
        return {outdoor: getattr(self, name) for outdoor, name in CURVE_POINTS.items()}
