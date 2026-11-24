"""Canonical model: the vocabulary shared by the plugin and the connection modules.

Both sides of a comparison (documented in NetBox, observed on the device) are expressed as a
:class:`Snapshot`. The diff runs only on snapshots.

Values are plain ``str``/``int``/``bool``/``None``. ``None`` (or ``""`` for text fields) is a real,
blank value. A value that is not known at all is one of the :class:`Unavailable` sentinels:

* :data:`NOT_OBSERVED`: the device side did not produce it (default for every field).
* :data:`NOT_IN_SCHEMA`: the installed NetBox version has nowhere to document it.

Canonical units and formats:

* ``interface.speed``: kbit/s (NetBox's unit), ``int``.
* ``interface.mac_address``: upper-case, colon separated (``AA:BB:CC:DD:EE:FF``).
* ``ip_address.address``: the host address without prefix length, compressed (``2001:db8::1``).
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterable
from dataclasses import dataclass, field, fields, replace
from enum import StrEnum
from typing import Any


class Unavailable:
    """A value that is unknown, as opposed to a known blank value."""

    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def __repr__(self) -> str:
        return f"<{self.reason}>"

    def __bool__(self) -> bool:
        return False

    def __copy__(self) -> Unavailable:
        return self

    def __deepcopy__(self, memo: Any) -> Unavailable:
        return self


NOT_OBSERVED = Unavailable("not_observed")
NOT_IN_SCHEMA = Unavailable("not_in_schema")

Value = str | int | bool | None | Unavailable


def is_available(value: Any) -> bool:
    return not isinstance(value, Unavailable)


# --- field catalogue ------------------------------------------------------------------------


class ObjectType(StrEnum):
    DEVICE = "device"
    INTERFACE = "interface"
    IP_ADDRESS = "ip_address"


class FieldKind(StrEnum):
    FACT = "fact"  # read-only: identity and hardware
    CONFIG = "config"  # can also be changed on the device, if a connection module supports it


@dataclass(frozen=True)
class FieldSpec:
    object_type: ObjectType
    name: str
    kind: FieldKind
    label: str
    key: bool = False  # the object's key: its presence, not an attribute

    @property
    def path(self) -> str:
        return f"{self.object_type}.{self.name}"


_SPECS = (
    FieldSpec(ObjectType.DEVICE, "name", FieldKind.FACT, "Name"),
    FieldSpec(ObjectType.DEVICE, "manufacturer", FieldKind.FACT, "Manufacturer"),
    FieldSpec(ObjectType.DEVICE, "model", FieldKind.FACT, "Model"),
    FieldSpec(ObjectType.DEVICE, "serial_number", FieldKind.FACT, "Serial number"),
    FieldSpec(ObjectType.DEVICE, "os_version", FieldKind.FACT, "OS version"),
    FieldSpec(ObjectType.INTERFACE, "name", FieldKind.FACT, "Interface", key=True),
    FieldSpec(ObjectType.INTERFACE, "enabled", FieldKind.CONFIG, "Enabled"),
    FieldSpec(ObjectType.INTERFACE, "description", FieldKind.CONFIG, "Description"),
    FieldSpec(ObjectType.INTERFACE, "mtu", FieldKind.CONFIG, "MTU"),
    FieldSpec(ObjectType.INTERFACE, "speed", FieldKind.CONFIG, "Speed"),
    FieldSpec(ObjectType.INTERFACE, "mac_address", FieldKind.FACT, "MAC address"),
    FieldSpec(ObjectType.IP_ADDRESS, "address", FieldKind.CONFIG, "IP address", key=True),
    FieldSpec(ObjectType.IP_ADDRESS, "interface", FieldKind.CONFIG, "Interface"),
    FieldSpec(ObjectType.IP_ADDRESS, "prefix_length", FieldKind.CONFIG, "Prefix length"),
)

#: Every canonical field, keyed by path (``"interface.mtu"``).
FIELDS: dict[str, FieldSpec] = {spec.path: spec for spec in _SPECS}
ALL_FIELDS: frozenset[str] = frozenset(FIELDS)


def fields_of(object_type: ObjectType, paths: Iterable[str]) -> list[FieldSpec]:
    """The specs among ``paths`` that belong to ``object_type``, in catalogue order."""
    wanted = set(paths)
    return [s for s in _SPECS if s.object_type == object_type and s.path in wanted]


def key_field(object_type: ObjectType) -> FieldSpec | None:
    return next((s for s in _SPECS if s.object_type == object_type and s.key), None)


# --- records --------------------------------------------------------------------------------


@dataclass
class DeviceRecord:
    name: Value = NOT_OBSERVED
    manufacturer: Value = NOT_OBSERVED
    model: Value = NOT_OBSERVED
    serial_number: Value = NOT_OBSERVED
    os_version: Value = NOT_OBSERVED


@dataclass
class InterfaceRecord:
    name: str
    enabled: Value = NOT_OBSERVED
    description: Value = NOT_OBSERVED
    mtu: Value = NOT_OBSERVED
    speed: Value = NOT_OBSERVED
    mac_address: Value = NOT_OBSERVED


@dataclass
class IPAddressRecord:
    address: str
    interface: Value = NOT_OBSERVED
    prefix_length: Value = NOT_OBSERVED


Record = DeviceRecord | InterfaceRecord | IPAddressRecord


@dataclass
class Snapshot:
    """One side of a comparison.

    A collection set to ``None`` was not observed at all, which is different from an empty
    collection (the device has no interfaces).
    """

    device: DeviceRecord = field(default_factory=DeviceRecord)
    interfaces: dict[str, InterfaceRecord] | None = None
    ip_addresses: dict[str, IPAddressRecord] | None = None

    def collection(self, object_type: ObjectType) -> dict[str, Record] | None:
        if object_type == ObjectType.INTERFACE:
            return self.interfaces
        if object_type == ObjectType.IP_ADDRESS:
            return self.ip_addresses
        raise ValueError(f"{object_type} is not a collection")

    def restrict(self, paths: Iterable[str]) -> Snapshot:
        """A copy keeping only ``paths``; every other field becomes NOT_OBSERVED.

        A collection is kept only if at least one of its fields was requested.
        """
        wanted = set(paths)
        return Snapshot(
            device=_restrict_record(self.device, ObjectType.DEVICE, wanted),
            interfaces=_restrict_collection(self.interfaces, ObjectType.INTERFACE, wanted),
            ip_addresses=_restrict_collection(self.ip_addresses, ObjectType.IP_ADDRESS, wanted),
        )


def record_values(record: Record) -> dict[str, Value]:
    return {f.name: getattr(record, f.name) for f in fields(record)}


def _restrict_record(record: Record, object_type: ObjectType, wanted: set[str]) -> Record:
    changes = {}
    for f in fields(record):
        spec = FIELDS[f"{object_type}.{f.name}"]
        if not spec.key and spec.path not in wanted:
            changes[f.name] = NOT_OBSERVED
    return replace(record, **changes)


def _restrict_collection(
    records: dict[str, Record] | None, object_type: ObjectType, wanted: set[str]
) -> dict[str, Record] | None:
    if records is None or not any(p.startswith(f"{object_type}.") for p in wanted):
        return None
    return {k: _restrict_record(r, object_type, wanted) for k, r in records.items()}


# --- normalisation helpers (used by both sides) ---------------------------------------------

_HEX = re.compile(r"[0-9a-fA-F]")


def normalize_mac(value: str | None) -> str | None:
    """Any common MAC notation -> ``AA:BB:CC:DD:EE:FF``; blank -> ``None``."""
    if value is None:
        return None
    digits = "".join(_HEX.findall(str(value)))
    if not digits:
        return None
    if len(digits) != 12:
        raise ValueError(f"not a MAC address: {value!r}")
    digits = digits.upper()
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


def normalize_ip(value: str) -> str:
    """Host address in canonical (compressed) form, without prefix length."""
    return str(ipaddress.ip_interface(str(value).strip()).ip)
