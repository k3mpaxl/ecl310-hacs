"""Physical sensor inputs.

The controller reports every Pt1000 input in hundredths of a degree. Which
input carries which measurement is decided by the installed application key;
the assignments modelled here are documented in
:mod:`ecl310_modbus.configurations.sensor_assignments`.
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

    @property
    def connected_sensor_names(self) -> tuple[str, ...]:
        """Return the inputs that currently report a reading."""
        return self.present_field_names
