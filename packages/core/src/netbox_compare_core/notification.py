"""Contract for notification modules.

A notification module delivers the result of a scheduled run to a channel the team watches.
It receives the whole run as a :class:`RunReport` and decides itself how to split it up (one
event per device, one digest per run, ...). Notifications only report: they never apply fixes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

#: Divergence severities, lowest first. Matches the plugin's policy severities.
SEVERITIES: tuple[str, ...] = ("low", "medium", "high", "critical")


def severity_rank(severity: str | None) -> int:
    """0 for no severity, then 1 (low) to 4 (critical). Unknown severities count as 0."""
    try:
        return SEVERITIES.index(severity) + 1  # type: ignore[arg-type]
    except ValueError:
        return 0


class DeviceStatus(StrEnum):
    COMPLETED = "completed"  # compared; ``divergences`` holds what was found (maybe nothing)
    FAILED = "failed"  # the comparison was attempted and failed; see ``error``
    SKIPPED = "skipped"  # selected but not compared; see ``skip_reason``


class SkipReason(StrEnum):
    NO_CONNECTION_MODULE = "no_connection_module"  # setup gap: platform not supported
    NO_CREDENTIALS = "no_credentials"  # setup gap: no secret for the device
    CREDENTIALS_ERROR = "credentials_error"  # the credentials backend failed


@dataclass(frozen=True)
class DivergenceItem:
    object_type: str  # "device", "interface", "ip_address"
    object_key: str  # interface name, IP address; "" for the device itself
    kind: str  # "field", "undocumented", "missing_on_device"
    field: str  # canonical field path, e.g. "interface.mtu"
    severity: str  # one of SEVERITIES
    documented: Any = None
    observed: Any = None


@dataclass(frozen=True)
class DeviceResult:
    name: str  # the NetBox device name
    status: DeviceStatus
    divergences: tuple[DivergenceItem, ...] = ()
    error: str = ""
    skip_reason: SkipReason | None = None
    completed: datetime | None = None
    url: str | None = None  # the device's comparison report, when the plugin knows its base URL

    @property
    def max_severity(self) -> str | None:
        """The highest severity among the divergences; None when there are none."""
        if not self.divergences:
            return None
        return max((d.severity for d in self.divergences), key=severity_rank)


@dataclass(frozen=True)
class RunReport:
    run_id: int
    schedule_name: str
    policy_name: str | None
    started: datetime
    completed: datetime
    devices: tuple[DeviceResult, ...]
    url: str | None = None  # the run's report, when the plugin knows its base URL


class NotificationError(Exception):
    """The notification could not be delivered. Messages must never contain secret material."""


class NotificationModule(ABC):
    """Base class for notification modules, registered under the
    ``netbox_compare.notifications`` entry point group."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config

    @abstractmethod
    def notify(self, report: RunReport) -> str:
        """Deliver ``report``. Return a short human-readable summary of what was delivered
        (shown on the run page, may include partial problems such as unknown hosts).

        Raise :class:`NotificationError` when nothing could be delivered.
        """
