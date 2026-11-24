"""Contract for connection modules.

A connection module is the only thing that talks to network devices. It declares, per platform,
what it can read, write and execute; the plugin reads these declarations before any request.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from netbox_compare_core.canonical import Snapshot
from netbox_compare_core.credentials import Credentials


@dataclass(frozen=True)
class PlatformCapabilities:
    """What a module can do on one platform. Field names are canonical paths
    (see :data:`netbox_compare_core.canonical.FIELDS`)."""

    readable: frozenset[str]
    writable: frozenset[str] = frozenset()
    exec_commands: bool = False


class ConnectionModuleError(Exception):
    """The device could not be reached, refused the login, or returned unusable output.

    Messages must never contain secret material.
    """


class Session(ABC):
    """An open connection to one device. Use as a context manager."""

    @abstractmethod
    def read(self, fields: Collection[str]) -> Snapshot:
        """Return a snapshot with exactly ``fields`` filled in, in canonical form.

        Fields not requested, or that the device did not yield in this run, are left
        ``NOT_OBSERVED``. A collection (interfaces, IP addresses) is set whenever one of its
        fields is requested, and left ``None`` otherwise.
        """

    def execute(self, command: str) -> str:
        """Run an arbitrary command and return its raw output, unparsed."""
        raise NotImplementedError

    def close(self) -> None:  # noqa: B027 - optional hook
        """Release the connection."""

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class ConnectionModule(ABC):
    """Base class for connection modules, registered under the
    ``netbox_compare.connections`` entry point group."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self.config = config

    @abstractmethod
    def capabilities(self) -> Mapping[str, PlatformCapabilities]:
        """Declared capabilities, keyed by NetBox platform slug."""

    @abstractmethod
    def open(self, platform: str, credentials: Credentials) -> Session:
        """Open a session to the device. Raise :class:`ConnectionModuleError` on failure.

        ``credentials`` are given per session; the module must not know where they came from.
        """
