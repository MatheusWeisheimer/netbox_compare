"""Discovery of pluggable modules through entry points.

Entry points are listed at startup; a module's code is only imported when it is first used.
Concrete modules are never imported by name.
"""

from __future__ import annotations

import logging
import threading
from importlib.metadata import EntryPoint, entry_points

from netbox.plugins import get_plugin_config

from netbox_compare_core import CredentialsProvider, entrypoints

logger = logging.getLogger(__name__)

GROUPS = (entrypoints.CONNECTIONS, entrypoints.CREDENTIALS, entrypoints.NOTIFICATIONS)

_available: dict[str, dict[str, EntryPoint]] = {}
_credentials_providers: list[tuple[str, CredentialsProvider]] | None = None
_lock = threading.Lock()


def discover() -> dict[str, dict[str, EntryPoint]]:
    """List installed modules per group without importing them."""
    _available.clear()
    for group in GROUPS:
        _available[group] = {ep.name: ep for ep in entry_points(group=group)}
        logger.debug("netbox_compare %s: %s", group, sorted(_available[group]))
    return _available


def available(group: str) -> dict[str, EntryPoint]:
    if not _available:
        discover()
    return _available.get(group, {})


def get_credentials_providers() -> list[tuple[str, CredentialsProvider]]:
    """Instantiate the configured credentials modules once per process, in config order."""
    global _credentials_providers
    if _credentials_providers is not None:
        return _credentials_providers
    with _lock:
        if _credentials_providers is not None:
            return _credentials_providers
        installed = available(entrypoints.CREDENTIALS)
        providers: list[tuple[str, CredentialsProvider]] = []
        for entry in get_plugin_config("netbox_compare", "credentials") or []:
            name = entry.get("module")
            ep = installed.get(name)
            if ep is None:
                logger.error(
                    "Credentials module %r is configured but not installed (installed: %s)",
                    name,
                    sorted(installed),
                )
                continue
            try:
                cls = ep.load()
                if not (isinstance(cls, type) and issubclass(cls, CredentialsProvider)):
                    raise TypeError(f"{ep.value} is not a CredentialsProvider subclass")
                providers.append((name, cls(entry.get("config") or {})))
            except Exception as exc:
                logger.error("Could not load credentials module %r: %s", name, exc)
        _credentials_providers = providers
        return providers
