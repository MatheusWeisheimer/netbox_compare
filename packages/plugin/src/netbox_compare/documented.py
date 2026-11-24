"""NetBox -> canonical model (the documented side).

Each field's home in the NetBox schema is checked explicitly. A canonical field with no home
in the installed schema is NOT_IN_SCHEMA, never blank.
"""

from __future__ import annotations

import logging

from dcim.models import Interface
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from ipam.models import IPAddress
from netbox.plugins import get_plugin_config

from netbox_compare_core import (
    NOT_IN_SCHEMA,
    DeviceRecord,
    InterfaceRecord,
    IPAddressRecord,
    Snapshot,
    Value,
    normalize_ip,
    normalize_mac,
)

logger = logging.getLogger(__name__)


def _has_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return True


# NetBox >= 4.2 keeps MACs in dcim.MACAddress, linked through Interface.primary_mac_address.
# Before that, Interface had a mac_address column.
if _has_field(Interface, "primary_mac_address"):
    _MAC_SOURCE = "primary_mac_address"
elif _has_field(Interface, "mac_address"):
    _MAC_SOURCE = "mac_address"
else:
    _MAC_SOURCE = None


def _interface_mac(interface) -> Value:
    if _MAC_SOURCE == "primary_mac_address":
        mac = interface.primary_mac_address
        return normalize_mac(str(mac.mac_address)) if mac else None
    if _MAC_SOURCE == "mac_address":
        return normalize_mac(str(interface.mac_address)) if interface.mac_address else None
    return NOT_IN_SCHEMA


def _os_version(device) -> Value:
    # NetBox has no native OS version field; it may be documented in a custom field.
    name = get_plugin_config("netbox_compare", "os_version_custom_field")
    if not name:
        return NOT_IN_SCHEMA
    from extras.models import CustomField

    if not CustomField.objects.filter(
        name=name, object_types__app_label="dcim", object_types__model="device"
    ).exists():
        logger.warning("os_version_custom_field %r is not a Device custom field", name)
        return NOT_IN_SCHEMA
    value = device.custom_field_data.get(name)
    return "" if value is None else str(value)


def documented_snapshot(device) -> Snapshot:
    device_type = device.device_type
    record = DeviceRecord(
        name=device.name,
        manufacturer=device_type.manufacturer.name,
        model=device_type.model,
        serial_number=device.serial,
        os_version=_os_version(device),
    )

    related = [_MAC_SOURCE] if _MAC_SOURCE == "primary_mac_address" else []
    interfaces = {}
    by_pk = {}
    for iface in Interface.objects.filter(device=device).select_related(*related):
        interfaces[iface.name] = InterfaceRecord(
            name=iface.name,
            enabled=iface.enabled,
            description=iface.description,
            mtu=iface.mtu,
            speed=iface.speed,
            mac_address=_interface_mac(iface),
        )
        by_pk[iface.pk] = iface.name

    ip_addresses: dict[str, IPAddressRecord] = {}
    ips = IPAddress.objects.filter(
        assigned_object_type=ContentType.objects.get_for_model(Interface),
        assigned_object_id__in=list(by_pk),
    ).order_by("pk")
    for ip in ips:
        address = normalize_ip(str(ip.address.ip))
        if address in ip_addresses:
            logger.warning("%s is documented twice on %s; keeping the first", address, device)
            continue
        ip_addresses[address] = IPAddressRecord(
            address=address,
            interface=by_pk[ip.assigned_object_id],
            prefix_length=ip.address.prefixlen,
        )

    return Snapshot(device=record, interfaces=interfaces, ip_addresses=ip_addresses)
