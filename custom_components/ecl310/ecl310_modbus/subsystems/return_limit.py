"""Return-limit settings shared by heating and hot-water circuits.

These domains are common to every supported profile containing the settings.
They are not offered for an unknown application: its domains are not known.
"""

from modbus_connection.model import NumberField

from ..data_model import parameter_number


def return_limit_setting(pnu: int) -> NumberField[float]:
    """Model one verified 1x031–1x037 setting, at its circuit's PNU."""
    function = pnu % 1000
    if function in (31, 33):
        minimum, maximum, scale, unit = -60, 20, 1.0, "°C"
    elif function in (32, 34):
        minimum, maximum, scale, unit = 10, 150, 1.0, "°C"
    elif function in (35, 36):
        minimum, maximum, scale, unit = -99, 99, 0.1, None
    elif function == 37:
        minimum, maximum, scale, unit = 0, 50, 1.0, "s"
    else:
        raise ValueError(f"Unsupported return-limit PNU {pnu}")
    return parameter_number(
        pnu,
        scale,
        signed=minimum < 0,
        min_value=minimum * scale,
        max_value=maximum * scale,
        raw_min=minimum,
        raw_max=maximum,
        step=scale,
        digits=1 if scale < 1 else 0,
        unit=unit,
        writable=True,
        maker_category="circuit",
    )
