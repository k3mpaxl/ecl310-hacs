"""The controller's switching outputs.

An ECL Comfort 310 drives its pumps and actuators through six triacs and six
relays. Which pump sits on which output is decided by the installed application
key and the wiring, so the registers are modelled by terminal number and the
pumps are named through
:mod:`ecl310_modbus.configurations.output_assignments`.

Three registers describe every output, and only the last one can be written:

=========================  ===============  ============================
Registers                  Access           Meaning
=========================  ===============  ============================
3999..4004, 4005..4010     read only        what the output is doing now
4025..4030                 read only        what the ECL display forced
4065..4070                 **read/write**   what Modbus asks for
=========================  ===============  ============================

Writing the state register is refused by the controller - it answers a write
to 4005..4010 with a Modbus exception - because the state is a result, not a
setting. Control goes through the override register, which takes
:class:`~ecl310_modbus.enums.OutputControl`: ``AUTO`` hands the output back to
the controller's regulation, ``OFF`` holds it off, ``ON`` holds it on. The
controller applies it within a couple of seconds.

The manual register is what an operator set at the ECL's own display, and it
outranks the override. It cannot be written over Modbus at all, which is why
it is modelled read-only: when it is non-zero the override register no longer
describes the output.
"""

from __future__ import annotations

from enum import IntEnum

from modbus_connection.model import NumberField

from ..configurations.output_assignments import (
    RELAY_ASSIGNMENTS,
    RELAY_ASSIGNMENTS_BY_NUMBER,
)
from ..data_model import Ecl310Component, register_enum, register_integer
from ..enums import OutputControl
from ..exceptions import Ecl310ValueValidationError

#: Address of the first triac state register; the six triacs are consecutive.
TRIAC_BASE_REGISTER = 3999

#: Address of the first relay state register; the six relays are consecutive.
RELAY_BASE_REGISTER = 4005

#: Address of the first relay manual register, set at the controller's display.
RELAY_MANUAL_BASE_REGISTER = 4025

#: Address of the first relay override register - the writable one.
RELAY_OVERRIDE_BASE_REGISTER = 4065

TRIAC_COUNT = 6
RELAY_COUNT = 6

#: The values a state register takes: off and on.
OUTPUT_OFF = 0
OUTPUT_ON = 1


def _state(address: int, key: str, description: str) -> NumberField[int]:
    """Declare one output's state register."""
    return register_integer(
        address,
        signed=True,
        min_value=OUTPUT_OFF,
        max_value=OUTPUT_ON,
        digits=0,
        writable=False,
        maker_key=key,
        maker_category="output",
        description=description,
    )


def _control(
    address: int, key: str, description: str, *, writable: bool
) -> NumberField[IntEnum]:
    """Declare one output's manual or override register."""
    return register_enum(
        address,
        OutputControl,
        maker_key=key,
        maker_category="output",
        description=description,
        writable=writable,
    )


def _relay_description(number: int) -> str:
    """Name what relay ``number`` drives, where the application key says so."""
    assignment = RELAY_ASSIGNMENTS_BY_NUMBER.get(number)
    return f" ({assignment.description})" if assignment else ""


def _relay_state(number: int) -> NumberField[int]:
    return _state(
        RELAY_BASE_REGISTER + number - 1,
        f"Relais {number}",
        f"Zustand Relais-Ausgang {number}{_relay_description(number)}",
    )


def _relay_manual(number: int) -> NumberField[IntEnum]:
    return _control(
        RELAY_MANUAL_BASE_REGISTER + number - 1,
        f"Relais {number} Handbetrieb",
        f"Handbetrieb Relais-Ausgang {number}{_relay_description(number)}",
        writable=False,
    )


def _relay_override(number: int) -> NumberField[IntEnum]:
    return _control(
        RELAY_OVERRIDE_BASE_REGISTER + number - 1,
        f"Relais {number} Override",
        f"Übersteuerung Relais-Ausgang {number}{_relay_description(number)}",
        writable=True,
    )


class Outputs(Ecl310Component):
    """Every triac and relay output: its state, its manual value, its override.

    Only the override registers are writable, and writing one overrides the
    controller's own logic rather than asking it to want something. Use the
    circuit's operating mode to tell the controller what to do, and these to
    take an output out of its hands.
    """

    triac_1 = _state(TRIAC_BASE_REGISTER + 0, "Triac 1", "Zustand Triac-Ausgang 1")
    """State of triac output 1."""

    triac_2 = _state(TRIAC_BASE_REGISTER + 1, "Triac 2", "Zustand Triac-Ausgang 2")
    """State of triac output 2."""

    triac_3 = _state(TRIAC_BASE_REGISTER + 2, "Triac 3", "Zustand Triac-Ausgang 3")
    """State of triac output 3."""

    triac_4 = _state(TRIAC_BASE_REGISTER + 3, "Triac 4", "Zustand Triac-Ausgang 4")
    """State of triac output 4."""

    triac_5 = _state(TRIAC_BASE_REGISTER + 4, "Triac 5", "Zustand Triac-Ausgang 5")
    """State of triac output 5."""

    triac_6 = _state(TRIAC_BASE_REGISTER + 5, "Triac 6", "Zustand Triac-Ausgang 6")
    """State of triac output 6."""

    relay_1 = _relay_state(1)
    """State of relay output 1 - the heating circuit pump."""

    relay_2 = _relay_state(2)
    """State of relay output 2 - the storage charge pump."""

    relay_3 = _relay_state(3)
    """State of relay output 3 - the circulation pump."""

    relay_4 = _relay_state(4)
    """State of relay output 4."""

    relay_5 = _relay_state(5)
    """State of relay output 5."""

    relay_6 = _relay_state(6)
    """State of relay output 6."""

    relay_1_manual = _relay_manual(1)
    """What the controller's display forced relay 1 to, if anything."""

    relay_2_manual = _relay_manual(2)
    """What the controller's display forced relay 2 to, if anything."""

    relay_3_manual = _relay_manual(3)
    """What the controller's display forced relay 3 to, if anything."""

    relay_4_manual = _relay_manual(4)
    """What the controller's display forced relay 4 to, if anything."""

    relay_5_manual = _relay_manual(5)
    """What the controller's display forced relay 5 to, if anything."""

    relay_6_manual = _relay_manual(6)
    """What the controller's display forced relay 6 to, if anything."""

    relay_1_override = _relay_override(1)
    """What relay 1 has been overridden to over Modbus."""

    relay_2_override = _relay_override(2)
    """What relay 2 has been overridden to over Modbus."""

    relay_3_override = _relay_override(3)
    """What relay 3 has been overridden to over Modbus."""

    relay_4_override = _relay_override(4)
    """What relay 4 has been overridden to over Modbus."""

    relay_5_override = _relay_override(5)
    """What relay 5 has been overridden to over Modbus."""

    relay_6_override = _relay_override(6)
    """What relay 6 has been overridden to over Modbus."""

    @staticmethod
    def _check(number: int) -> int:
        """Return ``number`` if it names a relay, else raise."""
        if not 1 <= number <= RELAY_COUNT:
            raise Ecl310ValueValidationError(
                f"Expected a relay 1..{RELAY_COUNT}, got {number}"
            )
        return number

    @property
    def triacs(self) -> tuple[int | None, ...]:
        """The six triac states, in terminal order."""
        return tuple(
            getattr(self, f"triac_{number}") for number in range(1, TRIAC_COUNT + 1)
        )

    @property
    def relays(self) -> tuple[int | None, ...]:
        """The six relay states, in terminal order."""
        return tuple(
            getattr(self, f"relay_{number}") for number in range(1, RELAY_COUNT + 1)
        )

    def relay(self, number: int) -> bool | None:
        """Return whether relay ``number`` is switched on right now."""
        value = getattr(self, f"relay_{self._check(number)}")
        return None if value is None else value != OUTPUT_OFF

    def relay_override(self, number: int) -> OutputControl | None:
        """Return what relay ``number`` has been overridden to over Modbus."""
        value = getattr(self, f"relay_{self._check(number)}_override")
        return None if value is None else OutputControl(value)

    def relay_manual(self, number: int) -> OutputControl | None:
        """Return what the controller's display forced relay ``number`` to.

        A value other than :attr:`~ecl310_modbus.enums.OutputControl.AUTO`
        outranks the override, and cannot be cleared over Modbus - only at the
        controller itself.
        """
        value = getattr(self, f"relay_{self._check(number)}_manual")
        return None if value is None else OutputControl(value)

    def relay_is_manual(self, number: int) -> bool | None:
        """Return whether the display is holding relay ``number``."""
        manual = self.relay_manual(number)
        return None if manual is None else manual is not OutputControl.AUTO

    async def async_set_relay_override(
        self, number: int, control: OutputControl
    ) -> None:
        """Hold relay ``number`` on or off, or hand it back to the controller.

        Writes the relay's override register. The state register is not
        writable: the controller answers a write to it with an exception.
        """
        await self.write(f"relay_{self._check(number)}_override", control)

    @property
    def named_relays(self) -> dict[str, bool | None]:
        """The state of the relays this application key names, by key."""
        return {
            assignment.key: self.relay(assignment.number)
            for assignment in RELAY_ASSIGNMENTS
        }

    @property
    def named_relay_overrides(self) -> dict[str, OutputControl | None]:
        """The override of the relays this application key names, by key."""
        return {
            assignment.key: self.relay_override(assignment.number)
            for assignment in RELAY_ASSIGNMENTS
        }

    @property
    def heating_pump(self) -> bool | None:
        """Whether the heating circuit pump is running (relay 1)."""
        return self.relay(1)

    @property
    def storage_charge_pump(self) -> bool | None:
        """Whether the storage charge pump is running (relay 2)."""
        return self.relay(2)

    @property
    def circulation_pump(self) -> bool | None:
        """Whether the circulation pump is running (relay 3)."""
        return self.relay(3)

    @property
    def heating_pump_override(self) -> OutputControl | None:
        """What the heating circuit pump has been overridden to."""
        return self.relay_override(1)

    @property
    def storage_charge_pump_override(self) -> OutputControl | None:
        """What the storage charge pump has been overridden to."""
        return self.relay_override(2)

    @property
    def circulation_pump_override(self) -> OutputControl | None:
        """What the circulation pump has been overridden to."""
        return self.relay_override(3)

    async def async_set_heating_pump(self, control: OutputControl) -> None:
        """Hold the heating circuit pump, or hand it back to the controller."""
        await self.async_set_relay_override(1, control)

    async def async_set_storage_charge_pump(self, control: OutputControl) -> None:
        """Hold the storage charge pump, or hand it back to the controller."""
        await self.async_set_relay_override(2, control)

    async def async_set_circulation_pump(self, control: OutputControl) -> None:
        """Hold the circulation pump, or hand it back to the controller."""
        await self.async_set_relay_override(3, control)
