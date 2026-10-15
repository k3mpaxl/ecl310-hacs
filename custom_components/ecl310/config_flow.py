"""Config flow for the Danfoss ECL Comfort 310 custom integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from modbus_connection import IllegalDataAddressError, ModbusError
from modbus_connection.tmodbus import ModbusConnection

from .const import (
    APPLICATION_GENERIC,
    CONF_APPLICATION,
    CONF_FRAMER,
    CONF_UNIT_ID,
    DEFAULT_FRAMER,
    DEFAULT_PORT,
    DEFAULT_UNIT_ID,
    DOMAIN,
    FRAMERS,
)
from .ecl310_modbus import PROFILES, DeviceInformation, Ecl310

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


def application_schema(default: str) -> vol.Schema:
    """Ask which application the controller runs, suggesting ``default``."""
    options = [
        SelectOptionDict(value=profile.key, label=profile.title)
        for profile in sorted(PROFILES.values(), key=lambda p: p.title)
    ]
    options.append(SelectOptionDict(value=APPLICATION_GENERIC, label="Other"))
    return vol.Schema(
        {
            vol.Required(CONF_APPLICATION, default=default): SelectSelector(
                SelectSelectorConfig(
                    options=options,
                    mode=SelectSelectorMode.LIST,
                    translation_key=CONF_APPLICATION,
                )
            ),
        }
    )


class Ecl310ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the ECL Comfort 310."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, Any] = {}
        self._title = DeviceInformation().name
        self._detected: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:  # noqa: ARG004
        """Let the application be changed later."""
        return Ecl310OptionsFlow()

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

            if await self._async_probe(host, port, unit_id, framer):
                self._data = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_UNIT_ID: unit_id,
                    CONF_FRAMER: framer,
                }
                return await self.async_step_application()
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_application(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Confirm the application, with the detected one suggested."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._title,
                data={**self._data, CONF_APPLICATION: user_input[CONF_APPLICATION]},
            )
        detected = PROFILES.get(self._detected) if self._detected else None
        return self.async_show_form(
            step_id="application",
            data_schema=application_schema(self._detected or APPLICATION_GENERIC),
            description_placeholders={
                "detected": detected.title if detected else "-",
            },
        )

    async def _async_probe(
        self, host: str, port: int, unit_id: int, framer: str
    ) -> bool:
        """Read the controller over a throwaway link and detect its application.

        Returns whether it answered.
        """
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
        unit = connection.for_unit(unit_id)
        try:
            try:
                info = await Ecl310.async_probe(unit)
            except IllegalDataAddressError:
                # The controller answered, it just does not serve one of the
                # registers probed. That is an application detail the
                # coordinator handles register by register, not a failed
                # connection.
                pass
            else:
                self._title = info.name
            detection = await Ecl310.async_detect_application(unit)
        except PROBE_ERRORS:
            return False
        else:
            self._detected = (
                detection.application.key if detection.application else None
            )
            return True
        finally:
            await connection.close()


class Ecl310OptionsFlow(OptionsFlow):
    """Change the application the controller runs."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Choose the application; the entry reloads with it."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        entry = self.config_entry
        current = entry.options.get(
            CONF_APPLICATION, entry.data.get(CONF_APPLICATION, APPLICATION_GENERIC)
        )
        return self.async_show_form(
            step_id="init", data_schema=application_schema(current)
        )
