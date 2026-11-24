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

# NetBox has no native OS version field. It is documented in a Device custom field with this
# name; without one, the OS version is not comparable.
OS_VERSION_CUSTOM_FIELD = "os_version"


def _has_field(model, name: str) -> bool:
    try:
        model._meta.get_field(name)
    except FieldDoesNotExist:
        return False
    return True


# NetBox >= 4.2 keeps MACs in dcim.MACAddress, linked through Interface.primary_mac_address.
# Before that, Interface had a mac_address column.
if _has_field(Interface, "primary_mac_address"):
    MAC_SOURCE = "primary_mac_address"
elif _has_field(Interface, "mac_address"):
    MAC_SOURCE = "mac_address"
else:
    MAC_SOURCE = None


def _interface_mac(interface) -> Value:
    if MAC_SOURCE == "primary_mac_address":
        mac = interface.primary_mac_address
        return normalize_mac(str(mac.mac_address)) if mac else None
    if MAC_SOURCE == "mac_address":
        return normalize_mac(str(interface.mac_address)) if interface.mac_address else None
    return NOT_IN_SCHEMA


def _os_version(device) -> Value:
    from extras.models import CustomField

    if not CustomField.objects.filter(
        name=OS_VERSION_CUSTOM_FIELD, object_types__app_label="dcim", object_types__model="device"
    ).exists():
        return NOT_IN_SCHEMA
    value = device.custom_field_data.get(OS_VERSION_CUSTOM_FIELD)
    return "" if value is None else str(value)


def device_record(device) -> DeviceRecord:
    device_type = device.device_type
    return DeviceRecord(
        name=device.name,
        manufacturer=device_type.manufacturer.name,
        model=device_type.model,
        serial_number=device.serial,
        os_version=_os_version(device),
    )


def interface_record(iface) -> InterfaceRecord:
    return InterfaceRecord(
        name=iface.name,
        enabled=iface.enabled,
        description=iface.description,
        mtu=iface.mtu,
        speed=iface.speed,
        mac_address=_interface_mac(iface),
    )


def interfaces_of(device, queryset=None):
    queryset = Interface.objects.all() if queryset is None else queryset
    related = [MAC_SOURCE] if MAC_SOURCE == "primary_mac_address" else []
    return queryset.filter(device=device).select_related(*related)


def ip_addresses_of(interface_pks, queryset=None):
    """IP addresses assigned to the given interfaces, oldest first."""
    queryset = IPAddress.objects.all() if queryset is None else queryset
    return queryset.filter(
        assigned_object_type=ContentType.objects.get_for_model(Interface),
        assigned_object_id__in=list(interface_pks),
    ).order_by("pk")


def documented_snapshot(device) -> Snapshot:
    record = device_record(device)
    interfaces = {}
    by_pk = {}
    for iface in interfaces_of(device):
        interfaces[iface.name] = interface_record(iface)
        by_pk[iface.pk] = iface.name

    ip_addresses: dict[str, IPAddressRecord] = {}
    for ip in ip_addresses_of(by_pk):
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
