"""Comparison policy: which canonical fields are considered, and their severity."""

from __future__ import annotations

from netbox.plugins import get_plugin_config

from netbox_compare.diff import validate_policy

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


def get_policy() -> dict[str, str]:
    configured = get_plugin_config("netbox_compare", "policy")
    return validate_policy(DEFAULT_POLICY if configured is None else configured)
