"""Config flow for the Danfoss ECL Comfort 310 custom integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from modbus_connection import ModbusError
from modbus_connection.tmodbus import ModbusConnection

from .const import (
    CONF_FRAMER,
    CONF_UNIT_ID,
    DEFAULT_FRAMER,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    DOMAIN,
    FRAMERS,
)
from .ecl310_modbus import Ecl310

#: What probing an unreachable controller raises. Named rather than written
#: inline so the formatter leaves the tuple alone on a Python 3.14 target.
PROBE_ERRORS = (ModbusError, OSError)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
            NumberSelectorConfig(min=1, max=65535, step=1, mode=NumberSelectorMode.BOX)
        ),
        vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): NumberSelector(
            NumberSelectorConfig(min=1, max=247, step=1, mode=NumberSelectorMode.BOX)
        ),
        vol.Required(CONF_FRAMER, default=DEFAULT_FRAMER): SelectSelector(
            SelectSelectorConfig(options=FRAMERS, mode=SelectSelectorMode.DROPDOWN)
        ),
    }
)


class Ecl310ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the ECL Comfort 310."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Collect the link details and confirm the controller answers."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = int(user_input[CONF_PORT])
            unit_id = int(user_input[CONF_UNIT_ID])
            framer = user_input[CONF_FRAMER]

            await self.async_set_unique_id(f"{host}:{port}:{unit_id}")
            self._abort_if_unique_id_configured()

            title = await self._async_probe(host, port, unit_id, framer)
            if title is None:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_UNIT_ID: unit_id,
                        CONF_FRAMER: framer,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def _async_probe(
        self, host: str, port: int, unit_id: int, framer: str
    ) -> str | None:
        """Read the controller over a throwaway link, or None if unreachable."""
        # Imported here so the flow builds the same parameters async_setup_entry
        # does, without importing the platform module at class definition time.
        from . import connection_params  # noqa: PLC0415

        connection = ModbusConnection(
            connection_params(
                {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_FRAMER: framer,
                }
            )
        )
        try:
            info = await Ecl310.async_probe(connection.for_unit(unit_id))
        except PROBE_ERRORS:
            return None
        else:
            return info.name
        finally:
            await connection.close()
