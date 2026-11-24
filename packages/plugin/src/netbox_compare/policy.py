"""Comparison policies: which canonical fields are considered, and their severity.

Policies are stored in NetBox (:class:`netbox_compare.models.ComparisonPolicy`). A policy's
``fields`` holds an entry for every canonical field::

    {"interface.mtu": {"enabled": True, "severity": "medium"}, ...}

Enabling a field and choosing its severity are separate, so a disabled field keeps its severity.
The diff only sees the enabled fields, as ``{path: severity}`` (see :func:`considered`).

:data:`DEFAULT_POLICY` seeds the "Default" policy and pre-fills the form for a new one.
This module has no Django import at module level, so it can be tested without NetBox.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from netbox_compare.diff import SEVERITIES
from netbox_compare_core import FIELDS

DEFAULT_POLICY = {
    "device.name": "medium",
    "device.manufacturer": "high",
    "device.model": "high",
    "device.serial_number": "high",
    "device.os_version": "low",
    "interface.name": "medium",
    "interface.enabled": "high",
    "interface.description": "low",
    "interface.mtu": "medium",
    "interface.speed": "medium",
    "interface.mac_address": "low",
    "ip_address.address": "high",
    "ip_address.interface": "high",
    "ip_address.prefix_length": "high",
}


def validate_policy_fields(raw: Any) -> dict[str, dict[str, Any]]:
    """Check ``raw`` and return it complete, in catalogue order. Raises ``ValueError``.

    Fields missing from ``raw`` are added disabled, with their default severity.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("Policy fields must be an object keyed by canonical field path.")
    unknown = sorted(set(raw) - set(FIELDS))
    if unknown:
        raise ValueError(f"Comparison policy names unknown fields: {unknown}")
    out = {}
    for path in FIELDS:
        entry = raw.get(path, {"enabled": False, "severity": DEFAULT_POLICY.get(path, "medium")})
        if not isinstance(entry, Mapping) or set(entry) - {"enabled", "severity"}:
            raise ValueError(f'{path}: expected {{"enabled": bool, "severity": str}}.')
        enabled = entry.get("enabled", False)
        severity = entry.get("severity", DEFAULT_POLICY.get(path, "medium"))
        if not isinstance(enabled, bool):
            raise ValueError(f"{path}: 'enabled' must be true or false.")
        if severity not in SEVERITIES:
            raise ValueError(f"{path}: invalid severity {severity!r}; use {SEVERITIES}.")
        out[path] = {"enabled": enabled, "severity": severity}
    if not any(entry["enabled"] for entry in out.values()):
        raise ValueError("A policy must enable at least one field.")
    return out


def considered(fields: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """The enabled fields of a policy, as the diff takes them: ``{path: severity}``."""
    return {
        path: entry["severity"]
        for path, entry in fields.items()
        if isinstance(entry, Mapping) and entry.get("enabled")
    }


def default_policy():
    """The policy used when none is chosen, or ``None`` if no policy is marked default."""
    from netbox_compare.models import ComparisonPolicy

    return ComparisonPolicy.objects.filter(is_default=True).first()
