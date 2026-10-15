"""Tell which application a controller runs from the registers it refuses.

Neither the application nor its version can be read over Modbus. What can be
observed is which parameters the controller serves: it refuses a register its
application does not have. So a handful of parameters that some of the known
applications have and others lack are read one by one, and each profile is
scored by how many of those answers it predicts wrongly.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from modbus_connection import (
    IllegalDataAddressError,
    IllegalFunctionError,
    ModbusConnectionError,
    ModbusError,
)

from ..addresses import parameter_address

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit

    from .profile import ApplicationProfile

#: How many parameters a detection reads at most.
MAX_PROBES = 8

#: What a controller answers for a register its application does not serve.
REFUSED_ERRORS = (IllegalDataAddressError, IllegalFunctionError)


@dataclass(frozen=True)
class Detection:
    """The outcome of probing a controller against the known profiles."""

    answered: frozenset[int]
    """Probed parameters the controller served."""

    refused: frozenset[int]
    """Probed parameters the controller refused."""

    ranking: tuple[tuple[ApplicationProfile, int], ...]
    """Every profile with its number of wrong predictions, best first."""

    @property
    def application(self) -> ApplicationProfile | None:
        """The profile that fits clearly better than every other, if one does.

        It may mispredict a quarter of the probes at most - a parameter the
        report lists need not be served over Modbus - and must beat the
        runner-up.
        """
        if not self.ranking:
            return None
        best, misses = self.ranking[0]
        if misses > (len(self.answered) + len(self.refused)) // 4:
            return None
        if len(self.ranking) > 1 and self.ranking[1][1] <= misses:
            return None
        return best


def distinguishing_parameters(
    profiles: Iterable[ApplicationProfile],
    preferred: Iterable[int] = (),
    limit: int = MAX_PROBES,
) -> tuple[int, ...]:
    """Pick parameters that some of ``profiles`` have and others lack.

    Parameters in ``preferred`` come first - the ones the library reads
    anyway, which are known to be served over Modbus where they exist. The
    pick alternates between the groups of profiles that have a parameter, so
    each group gets a say.
    """
    profiles = list(profiles)
    if len(profiles) < 2:
        return ()
    preferred = frozenset(preferred)
    known = [set(profile.parameters) for profile in profiles]
    everywhere = set.intersection(*known)
    anywhere = set.union(*known)

    def order(pnu: int) -> tuple[bool, int]:
        return (pnu not in preferred, pnu)

    groups: dict[frozenset[str], list[int]] = {}
    for pnu in sorted(anywhere - everywhere, key=order):
        owners = frozenset(profile.key for profile in profiles if profile.has(pnu))
        groups.setdefault(owners, []).append(pnu)
    queues = sorted(groups.values(), key=lambda queue: order(queue[0]))

    probes: list[int] = []
    while len(probes) < limit and any(queues):
        for queue in queues:
            if queue and len(probes) < limit:
                probes.append(queue.pop(0))
    return tuple(probes)


async def async_detect(
    unit: ModbusUnit,
    profiles: Iterable[ApplicationProfile],
    preferred: Iterable[int] = (),
) -> Detection:
    """Probe the controller on ``unit`` and rank ``profiles`` against it.

    A parameter that neither answers nor is refused - a timeout, say - is left
    out of the scoring. A link that is down raises.
    """
    profiles = list(profiles)
    answered: set[int] = set()
    refused: set[int] = set()
    for pnu in distinguishing_parameters(profiles, preferred):
        try:
            await unit.read_holding_registers(parameter_address(pnu), 1)
        except REFUSED_ERRORS:
            refused.add(pnu)
        except ModbusConnectionError:
            raise
        except ModbusError:
            continue
        else:
            answered.add(pnu)

    def misses(profile: ApplicationProfile) -> int:
        return sum(not profile.has(pnu) for pnu in answered) + sum(
            profile.has(pnu) for pnu in refused
        )

    ranking = sorted(
        ((profile, misses(profile)) for profile in profiles),
        key=lambda item: (item[1], item[0].key),
    )
    return Detection(frozenset(answered), frozenset(refused), tuple(ranking))
