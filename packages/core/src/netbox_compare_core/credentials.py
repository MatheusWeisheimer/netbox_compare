"""Contract for credentials modules.

A credentials module resolves a device into exactly (host, username, password). It knows
where secrets live; the plugin and connection modules never do.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DeviceIdentity:
    """What the plugin tells a credentials module about a device. Never an ORM object."""

    name: str
    host: str | None
    platform: str | None = None


@dataclass(frozen=True)
class Credentials:
    host: str
    username: str
    password: str = field(repr=False)


class CredentialsError(Exception):
    """The credentials backend failed (unreachable, bad auth, undecryptable data, ...).

    Messages must never contain secret material.
    """


class AmbiguousCredentials(CredentialsError):
    """More than one secret matched the device."""


class CredentialsProvider(ABC):
    """Base class for credentials modules, registered under the
    ``netbox_compare.credentials`` entry point group."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config

    @abstractmethod
    def resolve(self, device: DeviceIdentity) -> Credentials | None:
        """Return credentials for ``device``, or ``None`` if this module has none for it.

        Raise :class:`CredentialsError` when the backend itself fails.
        """
