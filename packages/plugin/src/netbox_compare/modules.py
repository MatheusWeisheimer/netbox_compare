"""Discovery of pluggable modules through entry points.

Entry points are listed at startup; a module's code is only imported when it is first used.
Concrete modules are never imported by name.
"""

from __future__ import annotations

import logging
import threading
from importlib.metadata import EntryPoint, entry_points

from netbox.plugins import get_plugin_config

from netbox_compare_core import (
    ConnectionModule,
    CredentialsProvider,
    NotificationModule,
    PlatformCapabilities,
    entrypoints,
)

logger = logging.getLogger(__name__)

GROUPS = (entrypoints.CONNECTIONS, entrypoints.CREDENTIALS, entrypoints.NOTIFICATIONS)

_available: dict[str, dict[str, EntryPoint]] = {}
_loaded: dict[str, list[tuple[str, object]]] = {}
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


def _configured(group: str, setting: str, base: type) -> list[tuple[str, object]]:
    """Instantiate the modules listed in plugin setting ``setting``, once per process, in
    config order. Misconfigured modules are logged and skipped."""
    if group in _loaded:
        return _loaded[group]
    with _lock:
        if group in _loaded:
            return _loaded[group]
        installed = available(group)
        instances: list[tuple[str, object]] = []
        for entry in get_plugin_config("netbox_compare", setting) or []:
            name = entry.get("module")
            ep = installed.get(name)
            if ep is None:
                logger.error(
                    "%s module %r is configured but not installed (installed: %s)",
                    setting,
                    name,
                    sorted(installed),
                )
                continue
            try:
                cls = ep.load()
                if not (isinstance(cls, type) and issubclass(cls, base)):
                    raise TypeError(f"{ep.value} is not a {base.__name__} subclass")
                instances.append((name, cls(entry.get("config") or {})))
            except Exception as exc:
                logger.error("Could not load %s module %r: %s", setting, name, exc)
        _loaded[group] = instances
        return instances


def get_credentials_providers() -> list[tuple[str, CredentialsProvider]]:
    return _configured(entrypoints.CREDENTIALS, "credentials", CredentialsProvider)  # type: ignore[return-value]


def get_connection_modules() -> list[tuple[str, ConnectionModule]]:
    return _configured(entrypoints.CONNECTIONS, "connections", ConnectionModule)  # type: ignore[return-value]


def get_notification_modules() -> list[tuple[str, NotificationModule]]:
    return _configured(entrypoints.NOTIFICATIONS, "notifications", NotificationModule)  # type: ignore[return-value]


def notification_module(name: str) -> NotificationModule | None:
    return dict(get_notification_modules()).get(name)


def configured_notification_names() -> list[str]:
    """Names of the notification modules listed in the plugin config, in config order,
    whether or not they loaded (a module that fails to load is reported at delivery)."""
    return [e.get("module") for e in get_plugin_config("netbox_compare", "notifications") or []]


def connection_for_platform(
    platform: str | None,
) -> tuple[str, ConnectionModule, PlatformCapabilities] | None:
    """The first configured connection module that declares ``platform`` (a slug)."""
    if not platform:
        return None
    for name, module in get_connection_modules():
        try:
            capabilities = module.capabilities()
        except Exception as exc:
            logger.error("Connection module %r failed to declare capabilities: %s", name, exc)
            continue
        if platform in capabilities:
            return name, module, capabilities[platform]
    return None
