"""Physical sensor inputs.

The controller reports every Pt1000 input in hundredths of a degree. Which
input carries which measurement is decided by the installed application key,
so a field here is a measurement on a given input, and the device keeps the
ones its application's profile assigns (``ApplicationProfile.sensors``). Two
fields may read the same input under different applications - ``S6`` is the
storage temperature on A237/A337 and the hot water return on A266.10.
"""

from __future__ import annotations

from ..data_model import Ecl310Component, sensor_temperature


class Sensors(Ecl310Component):
    """The measured temperatures, named after what the input carries."""

    outdoor_temperature = sensor_temperature(1, description="Außentemperatur (S1)")
    """Outdoor temperature, the input the heating curve is driven from."""

    flow_temperature = sensor_temperature(
        3, description="Vorlauftemperatur Heizkreis (S3)"
    )
    """Heating circuit flow temperature."""

    return_temperature = sensor_temperature(
        5, description="Rücklauftemperatur Heizkreis (S5)"
    )
    """Heating circuit return temperature."""

    storage_temperature = sensor_temperature(
        6, description="Speichertemperatur Warmwasser (S6)"
    )
    """Domestic hot water storage temperature."""

    secondary_return_temperature = sensor_temperature(
        2, description="Rücklauftemperatur Heizkreis, Sekundärseite (S2)"
    )
    """Heating return on the secondary side (A266.9, A266.10)."""

    hot_water_flow_temperature = sensor_temperature(
        4, description="Vorlauftemperatur Warmwasser (S4)"
    )
    """Domestic hot water flow temperature (A266)."""

    hot_water_return_temperature = sensor_temperature(
        6, description="Rücklauftemperatur Warmwasser (S6)"
    )
    """Domestic hot water return temperature (A266.9, A266.10)."""

    @property
    def connected_sensor_names(self) -> tuple[str, ...]:
        """Return the inputs that currently report a reading."""
        return self.present_field_names
