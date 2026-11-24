"""Connection module backed by NAPALM getters. Reads and open-command execution only; it
declares no write capability."""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Callable, Collection, Mapping
from typing import Any

from netbox_compare_core import (
    ALL_FIELDS,
    NOT_OBSERVED,
    ConnectionModule,
    ConnectionModuleError,
    Credentials,
    DeviceRecord,
    InterfaceRecord,
    IPAddressRecord,
    PlatformCapabilities,
    Session,
    Snapshot,
    Value,
    normalize_ip,
    normalize_mac,
)
from netbox_compare_napalm import fixups

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60


def _load_driver(name: str) -> type:
    from napalm import get_network_driver

    return get_network_driver(name)


class NapalmModule(ConnectionModule):
    """Configuration::

    {
        "platforms": {
            "<netbox platform slug>": {
                "driver": "huawei_vrp",       # NAPALM driver name (required)
                "optional_args": {...},       # passed to the driver
                "timeout": 60,                # seconds
                "exclude_fields": ["interface.mtu"],  # declare these unreadable
            },
        },
    }
    """

    def __init__(
        self,
        config: Mapping[str, Any],
        *,
        driver_loader: Callable[[str], type] = _load_driver,
    ) -> None:
        super().__init__(config)
        self._load_driver = driver_loader
        self._platforms: dict[str, Mapping[str, Any]] = {}
        for slug, platform in (config.get("platforms") or {}).items():
            if not platform.get("driver"):
                raise ConnectionModuleError(f"NAPALM platform {slug!r} has no 'driver'")
            unknown = set(platform.get("exclude_fields") or ()) - ALL_FIELDS
            if unknown:
                raise ConnectionModuleError(
                    f"NAPALM platform {slug!r} excludes unknown fields: {sorted(unknown)}"
                )
            self._platforms[slug] = platform

    def capabilities(self) -> dict[str, PlatformCapabilities]:
        return {
            slug: PlatformCapabilities(
                readable=ALL_FIELDS - frozenset(p.get("exclude_fields") or ()),
                writable=frozenset(),
                exec_commands=True,
            )
            for slug, p in self._platforms.items()
        }

    def open(self, platform: str, credentials: Credentials) -> NapalmSession:
        cfg = self._platforms.get(platform)
        if cfg is None:
            raise ConnectionModuleError(f"Platform {platform!r} is not configured for NAPALM")
        driver_name = cfg["driver"]
        try:
            driver_cls = self._load_driver(driver_name)
        except Exception as exc:
            raise ConnectionModuleError(
                f"NAPALM driver {driver_name!r} is not available: {exc}"
            ) from exc
        device = driver_cls(
            hostname=credentials.host,
            username=credentials.username,
            password=credentials.password,
            timeout=int(cfg.get("timeout", DEFAULT_TIMEOUT)),
            optional_args=dict(cfg.get("optional_args") or {}),
        )
        try:
            device.open()
        except Exception as exc:
            raise ConnectionModuleError(
                f"Could not connect to {credentials.host} with NAPALM driver {driver_name!r}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        return NapalmSession(device, driver_name)


class NapalmSession(Session):
    def __init__(self, device: Any, driver_name: str) -> None:
        self.device = device
        self.driver_name = driver_name

    def close(self) -> None:
        try:
            self.device.close()
        except Exception:
            logger.debug("Error closing NAPALM session", exc_info=True)

    def execute(self, command: str) -> str:
        try:
            return self.device.cli([command])[command]
        except Exception as exc:
            raise ConnectionModuleError(f"Command failed: {type(exc).__name__}: {exc}") from exc

    def _getter(self, name: str) -> Any:
        """Call a NAPALM getter; ``None`` if it failed (the fields stay NOT_OBSERVED)."""
        try:
            return getattr(self.device, name)()
        except Exception as exc:
            logger.warning(
                "NAPALM %s.%s failed: %s: %s", self.driver_name, name, type(exc).__name__, exc
            )
            return None

    def read(self, fields: Collection[str]) -> Snapshot:
        wanted = set(fields)
        snapshot = Snapshot()
        attempted = succeeded = 0

        if any(f.startswith("device.") for f in wanted):
            attempted += 1
            facts = self._getter("get_facts")
            if facts is not None:
                succeeded += 1
                snapshot.device = device_from_facts(facts)

        if any(f.startswith("interface.") for f in wanted):
            attempted += 1
            interfaces = self._getter("get_interfaces")
            if interfaces is not None:
                succeeded += 1
                snapshot.interfaces = interfaces_from_getter(interfaces)

        if any(f.startswith("ip_address.") for f in wanted):
            attempted += 1
            ips = self._getter("get_interfaces_ip")
            if ips is not None:
                succeeded += 1
                snapshot.ip_addresses = ip_addresses_from_getter(ips)

        if attempted and not succeeded:
            raise ConnectionModuleError(
                f"Every NAPALM getter failed on driver {self.driver_name!r}; see the logs"
            )

        fixup = fixups.FIXUPS.get(self.driver_name)
        if fixup is not None:
            fixup(self.device, snapshot, wanted)
        return snapshot.restrict(wanted)


# --- NAPALM getter output -> canonical ----------------------------------------------------


def _text(value: Any) -> Value:
    """Identity strings: NAPALM uses "" (or junk types) for "unknown"."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return NOT_OBSERVED


def _serial(value: Any) -> Value:
    # Some drivers return a list (one serial per stack member).
    if isinstance(value, list | tuple):
        return _text(value[0]) if len(value) == 1 else NOT_OBSERVED
    return _text(value)


def device_from_facts(facts: Mapping[str, Any]) -> DeviceRecord:
    return DeviceRecord(
        name=_text(facts.get("hostname")),
        manufacturer=_text(facts.get("vendor")),
        model=_text(facts.get("model")),
        serial_number=_serial(facts.get("serial_number")),
        os_version=_text(facts.get("os_version")),
    )


def _positive_int(value: Any, factor: float = 1) -> Value:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return NOT_OBSERVED
    return round(number * factor) if number > 0 else NOT_OBSERVED


def _mac(value: Any) -> Value:
    try:
        return normalize_mac(value or None)
    except ValueError:
        return NOT_OBSERVED


def interfaces_from_getter(data: Mapping[str, Mapping[str, Any]]) -> dict[str, InterfaceRecord]:
    out = {}
    for name, d in data.items():
        enabled = d.get("is_enabled")
        description = d.get("description")
        out[name] = InterfaceRecord(
            name=name,
            enabled=enabled if isinstance(enabled, bool) else NOT_OBSERVED,
            description=description.strip() if isinstance(description, str) else NOT_OBSERVED,
            mtu=_positive_int(d.get("mtu")),
            speed=_positive_int(d.get("speed"), 1000),  # NAPALM: Mbit/s; canonical: kbit/s
            mac_address=_mac(d.get("mac_address")),
        )
    return out


def ip_addresses_from_getter(
    data: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, IPAddressRecord]:
    out: dict[str, IPAddressRecord] = {}
    for interface, families in data.items():
        for family in ("ipv4", "ipv6"):
            for raw, attrs in (families.get(family) or {}).items():
                try:
                    address = normalize_ip(raw)
                except ValueError:
                    logger.warning("Ignoring unparsable address %r on %s", raw, interface)
                    continue
                # IPv6 link-local addresses are generated by the device, never documented.
                if ipaddress.ip_address(address).is_link_local and family == "ipv6":
                    continue
                if address in out:
                    logger.warning(
                        "Address %s seen on %s and %s; keeping the first",
                        address,
                        out[address].interface,
                        interface,
                    )
                    continue
                out[address] = IPAddressRecord(
                    address=address,
                    interface=interface,
                    prefix_length=_positive_int((attrs or {}).get("prefix_length")),
                )
    return out
