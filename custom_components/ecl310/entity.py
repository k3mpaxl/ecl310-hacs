"""Base entity for the ECL Comfort 310.

The heating circuit and the hot water tank are their own sub-devices of the
controller; the measurements and the switching outputs belong to the controller
itself.

Setup creates all three devices, and an entity only points at the one it
belongs to. A sub-device has to name its parent by the parent's registry id,
which is only known once the parent exists, so the entities cannot describe
that relationship themselves.
"""

import dataclasses
import re
from collections.abc import Awaitable, Iterable, Iterator
from functools import cached_property
from typing import Any, Protocol, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from modbus_connection import ModbusError

from .const import (
    COMPONENT_HEATING,
    COMPONENT_HEATING_SCHEDULE,
    COMPONENT_HOT_WATER,
    COMPONENT_HOT_WATER_SCHEDULE,
    DOMAIN,
)
from .coordinator import Ecl310Coordinator
from .ecl310_modbus import (
    Circuit,
    DatapointMetadata,
    DeviceInformation,
    Ecl310,
    Ecl310Component,
)

#: The state attributes naming where an entity's values live on the controller.
ATTR_PNU = "pnu"
ATTR_TERMINAL = "terminal"
ATTR_ECL_NAME = "ecl_name"

#: A key or role that carries its circuit: ``flow_temperature_circuit_2``. The
#: library suffixes a role this way where the application has it on two
#: circuits; everything else goes without.
CIRCUIT_SUFFIX = re.compile(r"_circuit_(?P<circuit>\d+)")

#: A switching output's fields: ``relay_2``, ``relay_2_override``, ``triac_1``.
OUTPUT_FIELD = re.compile(r"^(?P<kind>triac|relay)_(?P<number>\d+)(?:_\w+)?$")

#: The key a circuit's device name is translated under, by circuit kind: as
#: is, and with the circuit number where the application has two of the kind.
CIRCUIT_DEVICE_NAMES: dict[str, tuple[str, str]] = {
    COMPONENT_HEATING: ("heating_circuit", "heating_circuit_numbered"),
    COMPONENT_HOT_WATER: ("hot_water", "hot_water_numbered"),
}

#: The descriptions declared for the default layout's circuit sub-systems, and
#: the circuit kind and part (the circuit or its weekly program) each stands for.
CIRCUIT_COMPONENTS: dict[str, tuple[str, bool]] = {
    COMPONENT_HEATING: (COMPONENT_HEATING, False),
    COMPONENT_HOT_WATER: (COMPONENT_HOT_WATER, False),
    COMPONENT_HEATING_SCHEDULE: (COMPONENT_HEATING, True),
    COMPONENT_HOT_WATER_SCHEDULE: (COMPONENT_HOT_WATER, True),
}


class _CircuitDescription(Protocol):
    key: str
    component: str


def circuit_key(key: str, circuit: Circuit) -> str:
    """Return an entity key, unique where the application has two such circuits.

    The default layout's keys stay as they are, so existing entities keep
    their unique IDs.
    """
    return f"{key}_circuit_{circuit.number}" if circuit.numbered else key


def per_circuit[DescriptionT: _CircuitDescription](
    device: Ecl310, descriptions: Iterable[DescriptionT]
) -> Iterator[DescriptionT]:
    """Each circuit description once for every circuit of its kind.

    A description declared for ``heating`` describes every heating circuit the
    application has; one for another sub-system is passed on as it is.
    """
    for description in descriptions:
        kind = CIRCUIT_COMPONENTS.get(description.component)
        if kind is None:
            yield description
            continue
        for circuit in device.circuits:
            if circuit.kind == kind[0]:
                yield dataclasses.replace(  # type: ignore[type-var]
                    description,
                    key=circuit_key(description.key, circuit),
                    component=circuit.schedule if kind[1] else circuit.component,
                )


def role_name(key: str) -> tuple[str, dict[str, str]]:
    """Return the translation key and placeholders of a role-named entity.

    ``flow_temperature`` is translated as it is; ``flow_temperature_circuit_2``
    as ``flow_temperature_circuit`` with the circuit as a placeholder.
    """
    match = CIRCUIT_SUFFIX.search(key)
    if match is None:
        return key, {}
    return f"{CIRCUIT_SUFFIX.sub('', key)}_circuit", {"circuit": match["circuit"]}


def role_circuit(key: str) -> int | None:
    """Return the circuit a role key names, if it names one."""
    match = CIRCUIT_SUFFIX.search(key)
    return int(match["circuit"]) if match else None


def datapoint_pnu(device: Ecl310, component: str, field: str) -> int | None:
    """Return the Danfoss parameter number (PNU) behind a sub-system field.

    Danfoss numbers every register by its PNU, one above the zero-based Modbus
    address - parameters, modes, outputs and sensors alike (communication
    description VI.LG.V5.02: "The register address is PNU-1").
    """
    subsystem = getattr(device, component, None)
    if subsystem is None:
        return None
    descriptor = type(subsystem).declared_fields.get(field)
    address = getattr(descriptor, "address", None)
    return None if address is None else address + 1


def datapoint_terminal(device: Ecl310, component: str, field: str) -> str | None:
    """Return the terminal a field is wired to: ``S3``, ``relay 2``, ``triac 1``."""
    if (output := OUTPUT_FIELD.match(field)) is not None:
        return f"{output['kind']} {output['number']}"
    subsystem = getattr(device, component, None)
    metadata = subsystem.metadata_for(field) if subsystem is not None else None
    if metadata is None or metadata.sensor_number is None:
        return None
    return f"S{metadata.sensor_number}"


def device_identifiers(entry: ConfigEntry, component: str) -> set[tuple[str, str]]:
    """Identify the device an entity of this sub-system belongs to.

    A circuit is a device of its own - ``<entry>_heating``, ``<entry>_heating_2``
    - and its weekly program belongs to it; the rest belongs to the controller.
    """
    circuit = component.removesuffix("_schedule")
    if not circuit.startswith((COMPONENT_HEATING, COMPONENT_HOT_WATER)):
        return {(DOMAIN, entry.entry_id)}
    return {(DOMAIN, f"{entry.entry_id}_{circuit}")}


def circuit_device_name(circuit: Circuit) -> tuple[str, dict[str, str]]:
    """Return the translation key and placeholders naming a circuit's device."""
    plain, numbered = CIRCUIT_DEVICE_NAMES[circuit.kind]
    if circuit.numbered:
        return numbered, {"circuit": str(circuit.number)}
    return plain, {}


def controller_device_info(entry: ConfigEntry, info: DeviceInformation) -> DeviceInfo:
    """Describe the controller itself, for setup to register."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=info.manufacturer,
        model=info.model,
        name=info.model,
        model_id=info.application,
        sw_version=info.firmware_version,
        hw_version=info.hardware_version,
        serial_number=info.serial_number,
    )


def supported[EntityT: Ecl310Entity](
    hass: HomeAssistant, platform: str, entities: Iterable[EntityT]
) -> list[EntityT]:
    """Keep the entities whose datapoints the controller's application has.

    One that an earlier version created for a datapoint the application does
    not have is removed from the entity registry, rather than lingering there
    as unavailable.
    """
    registry = er.async_get(hass)
    kept: list[EntityT] = []
    for entity in entities:
        if entity.supported_by(entity.coordinator.device):
            kept.append(entity)
        elif entity.unique_id and (
            entity_id := registry.async_get_entity_id(
                platform, DOMAIN, entity.unique_id
            )
        ):
            registry.async_remove(entity_id)
    return kept


class Ecl310Entity(CoordinatorEntity[Ecl310Coordinator]):
    """Common identity, device info and availability for every ECL entity."""

    _attr_has_entity_name = True

    #: Whether the entity shows controller datapoints, and so their PNUs. One the
    #: integration computes itself - the boost - names none.
    _shows_datapoints = True

    #: Datapoints shown besides the fields, as ``(sub-system, field)``.
    _extra_datapoints: tuple[tuple[str, str], ...] = ()

    def __init__(
        self,
        coordinator: Ecl310Coordinator,
        key: str,
        component: str,
        fields: tuple[str, ...] = (),
    ) -> None:
        """Initialize the entity.

        ``fields`` names the sub-system fields the entity reads. It stays
        unavailable if the controller does not serve any of them.
        """
        super().__init__(coordinator)
        self._component = component
        self._fields = frozenset(fields)
        self._field_order = fields
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"

        self._attr_device_info = DeviceInfo(
            identifiers=device_identifiers(entry, component)
        )

    @property
    def available(self) -> bool:
        """Return whether the sub-system and the fields behind this entity answered."""
        return (
            super().available
            and self.coordinator.answered(self._component)
            and self._fields.isdisjoint(self.coordinator.refused(self._component))
        )

    @cached_property
    def _datapoint_attributes(self) -> dict[str, Any]:
        """``pnu`` and ``terminal`` of the datapoints behind this entity.

        One datapoint gives plain values; several give the PNUs by field, so the
        thermostat shows its mode, setpoint and status apart.
        """
        if not self._shows_datapoints:
            return {}
        device = self.coordinator.device
        datapoints = [
            (component, field)
            for component, field in (
                *((self._component, field) for field in self._field_order),
                *self._extra_datapoints,
            )
            if device.supports(component, field)
        ]
        pnus = {
            field: pnu
            for component, field in datapoints
            if (pnu := datapoint_pnu(device, component, field)) is not None
        }
        terminals = list(
            dict.fromkeys(
                terminal
                for component, field in datapoints
                if (terminal := datapoint_terminal(device, component, field))
            )
        )
        attributes: dict[str, Any] = {}
        if pnus:
            attributes[ATTR_PNU] = next(iter(pnus.values())) if len(pnus) == 1 else pnus
        if (application := device.application) is not None:
            language = self.coordinator.hass.config.language
            names = {
                field: name
                for field, pnu in pnus.items()
                if (name := application.menu_name(pnu, language)) is not None
            }
            if names:
                attributes[ATTR_ECL_NAME] = (
                    next(iter(names.values())) if len(names) == 1 else names
                )
        if terminals:
            attributes[ATTR_TERMINAL] = (
                terminals[0] if len(terminals) == 1 else terminals
            )
        return attributes

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Where the entity's values live on the controller."""
        return dict(self._datapoint_attributes) or None

    def supported_by(self, device: Ecl310) -> bool:
        """Return whether the controller's application has this entity's data."""
        return all(device.supports(self._component, field) for field in self._fields)

    @property
    def _subsystem(self) -> Ecl310Component:
        """The library sub-system object this entity reads from."""
        subsystem = getattr(self.coordinator.device, self._component)
        return cast(Ecl310Component, subsystem)

    def _metadata(self, attribute: str) -> DatapointMetadata:
        """Return the library's metadata for one of this sub-system's datapoints."""
        return self._subsystem.require_metadata_for(attribute)

    async def _async_write(self, write: Awaitable[None]) -> None:
        """Await a write, turning what it raises into a Home Assistant error.

        A value outside the controller's domain is the caller's mistake and
        becomes a ``ServiceValidationError``; a controller that refuses or does
        not answer becomes a ``HomeAssistantError``. Both carry a translated
        message instead of a traceback.
        """
        try:
            await write
        except ValueError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
                translation_placeholders={"error": str(err)},
            ) from err
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
