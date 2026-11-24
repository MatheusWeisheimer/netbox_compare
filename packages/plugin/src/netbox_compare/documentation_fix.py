"""Fix divergences in the documentation: make NetBox match what was observed on the device.

Each fix runs in its own savepoint, so one failure does not undo the others. Before writing, a
fix checks that NetBox still holds the value the report shows as documented. If someone changed
it since the comparison, the fix is refused instead of overwriting their work.

Writes go through the ORM with the request's user, so NetBox records them in the change log.
Object permissions are enforced the way NetBox's own views do: existing objects are fetched
through ``restrict(user, action)``, and new or changed objects must still be within the user's
constraints after the write.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

import netaddr
from dcim.choices import InterfaceTypeChoices
from dcim.models import Device, DeviceType, Interface
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError
from django.db.models.deletion import RestrictedError
from ipam.models import IPAddress
from netbox.plugins import get_plugin_config

from netbox_compare.choices import DivergenceKindChoices, ResolutionStatusChoices
from netbox_compare.diff import same_value
from netbox_compare.documented import (
    MAC_SOURCE,
    device_record,
    interface_record,
    interfaces_of,
    ip_addresses_of,
)
from netbox_compare_core import normalize_ip

logger = logging.getLogger(__name__)


class FixError(Exception):
    """The fix cannot be applied; the message is shown to the administrator."""


# --- helpers --------------------------------------------------------------------------------


def _show(value) -> str:
    if value is None:
        return "blank"
    if value == "":
        return "empty"
    return repr(value)


def _expect_unchanged(what: str, current, documented) -> None:
    if not same_value(current, documented):
        raise FixError(
            f"{what} changed in NetBox since the comparison (report: {_show(documented)}, "
            f"now: {_show(current)}). Run a new comparison."
        )


def _require_perm(user, perm: str) -> None:
    if not user.has_perm(perm):
        raise FixError(f"You do not have the {perm} permission.")


def _save(obj, user, action: str) -> None:
    """Validate and save ``obj``, then check it is still within the user's permissions."""
    obj.full_clean()
    obj.save()
    if not type(obj).objects.restrict(user, action).filter(pk=obj.pk).exists():
        raise FixError(f"Your permissions do not allow this {type(obj)._meta.verbose_name}.")


def _delete(obj) -> None:
    obj.snapshot()
    try:
        obj.delete()
    except (ProtectedError, RestrictedError) as exc:
        names = ", ".join(str(o) for o in list(exc.args[1])[:5])
        raise FixError(f"{obj} cannot be deleted; other objects depend on it: {names}.") from exc


def _device(device, user, action: str = "change") -> Device:
    found = Device.objects.restrict(user, action).filter(pk=device.pk).first()
    if found is None:
        raise FixError(f"You do not have permission to {action} device {device}.")
    found.snapshot()
    return found


def _interface(device, name: str, user, action: str = "change") -> Interface:
    found = interfaces_of(device, Interface.objects.restrict(user, action)).filter(name=name)
    found = found.first()
    if found is None:
        if interfaces_of(device).filter(name=name).exists():
            raise FixError(f"You do not have permission to {action} interface {name}.")
        raise FixError(f"Interface {name} is no longer documented in NetBox.")
    found.snapshot()
    return found


def _ip_address(device, address: str, user, action: str = "change") -> IPAddress:
    iface_pks = interfaces_of(device).values_list("pk", flat=True)
    for ip in ip_addresses_of(iface_pks):
        if normalize_ip(str(ip.address.ip)) != address:
            continue
        # The first match is the one the documented snapshot used.
        if not IPAddress.objects.restrict(user, action).filter(pk=ip.pk).exists():
            raise FixError(f"You do not have permission to {action} IP address {ip}.")
        ip.snapshot()
        return ip
    raise FixError(f"IP address {address} is no longer documented on {device}.")


def _set_mac(iface: Interface, mac: str | None, user) -> None:
    """Make ``mac`` the interface's (primary) MAC address. Saves nothing but MAC objects."""
    if MAC_SOURCE == "mac_address":
        iface.mac_address = mac
        return
    if MAC_SOURCE != "primary_mac_address":
        raise FixError("This NetBox version has no field for interface MAC addresses.")
    if mac is None:
        iface.primary_mac_address = None
        return
    from dcim.models import MACAddress

    existing = MACAddress.objects.filter(
        assigned_object_type=ContentType.objects.get_for_model(Interface),
        assigned_object_id=iface.pk,
        mac_address=mac,
    ).first()
    if existing is None:
        _require_perm(user, "dcim.add_macaddress")
        existing = MACAddress(mac_address=mac, assigned_object=iface)
        _save(existing, user, "add")
    iface.primary_mac_address = existing


# --- fixes ----------------------------------------------------------------------------------
# Each takes (device, divergences, user) and returns a detail message.


def _fix_device_type(device, items, user) -> str:
    """device.manufacturer and device.model both come from the device type; fix them together."""
    device = _device(device, user)
    current = device_record(device)
    target = {"manufacturer": current.manufacturer, "model": current.model}
    for d in items:
        name = d.field.split(".", 1)[1]
        _expect_unchanged(f"Device {d.field_label.lower()}", getattr(current, name), d.documented)
        target[name] = d.observed
    device_type = DeviceType.objects.filter(
        manufacturer__name=target["manufacturer"], model=target["model"]
    ).first()
    if device_type is None:
        raise FixError(
            f"NetBox has no device type {target['model']!r} by {target['manufacturer']!r}. "
            "Create it, then apply again."
        )
    device.device_type = device_type
    _save(device, user, "change")
    return f"Device type set to {device_type}."


def _fix_device_field(device, items, user) -> str:
    (d,) = items
    device = _device(device, user)
    name = d.field.split(".", 1)[1]
    _expect_unchanged(
        f"Device {d.field_label.lower()}", getattr(device_record(device), name), d.documented
    )
    if name == "name":
        device.name = d.observed
    elif name == "serial_number":
        device.serial = d.observed or ""
    elif name == "os_version":
        custom_field = get_plugin_config("netbox_compare", "os_version_custom_field")
        if not custom_field:
            raise FixError("No os_version_custom_field is configured.")
        device.custom_field_data[custom_field] = d.observed
    else:
        raise FixError(f"Cannot fix {d.field} in the documentation.")
    _save(device, user, "change")
    return f"{d.field_label} set to {_show(d.observed)}."


def _fix_interface_field(device, items, user) -> str:
    (d,) = items
    iface = _interface(device, d.object_key, user)
    name = d.field.split(".", 1)[1]
    _expect_unchanged(
        f"{d.field_label} of {iface.name}", getattr(interface_record(iface), name), d.documented
    )
    if name == "mac_address":
        _set_mac(iface, d.observed, user)
    elif name == "description":
        iface.description = d.observed or ""
    elif name in ("enabled", "mtu", "speed"):
        setattr(iface, name, d.observed)
    else:
        raise FixError(f"Cannot fix {d.field} in the documentation.")
    _save(iface, user, "change")
    return f"{d.field_label} set to {_show(d.observed)}."


def _create_interface(device, items, user) -> str:
    (d,) = items
    _require_perm(user, "dcim.add_interface")
    if interfaces_of(device).filter(name=d.object_key).exists():
        raise FixError(f"Interface {d.object_key} is already documented in NetBox.")
    observed = d.observed or {}
    iface = Interface(device=device, name=d.object_key, type=InterfaceTypeChoices.TYPE_OTHER)
    for name in ("enabled", "mtu", "speed"):
        if name in observed:
            setattr(iface, name, observed[name])
    if "description" in observed:
        iface.description = observed["description"] or ""
    _save(iface, user, "add")
    if observed.get("mac_address"):
        iface.snapshot()
        _set_mac(iface, observed["mac_address"], user)
        _save(iface, user, "add")
    return f"Interface {iface.name} created with type Other; set its real type in NetBox."


def _delete_interface(device, items, user) -> str:
    (d,) = items
    iface = _interface(device, d.object_key, user, "delete")
    ip_count = ip_addresses_of([iface.pk]).count()
    if ip_count:
        raise FixError(
            f"{iface.name} still has {ip_count} IP address(es) in NetBox. Fix those first; "
            "deleting the interface would delete them too."
        )
    if iface.cable_id:
        raise FixError(f"{iface.name} is cabled in NetBox. Remove the cable first.")
    _delete(iface)
    return f"Interface {d.object_key} deleted."


def _target_interface(device, name, user) -> Interface:
    if not name:
        raise FixError("The device did not report the interface of this address.")
    iface = interfaces_of(device).filter(name=name).first()
    if iface is None:
        raise FixError(
            f"Interface {name} is not documented in NetBox. Fix it in the documentation first, "
            "or in the same apply."
        )
    return iface


def _fix_ip_field(device, items, user) -> str:
    (d,) = items
    ip = _ip_address(device, d.object_key, user)
    current_iface = ip.assigned_object.name if ip.assigned_object else None
    if d.field == "ip_address.interface":
        _expect_unchanged(f"Interface of {d.object_key}", current_iface, d.documented)
        ip.assigned_object = _target_interface(device, d.observed, user)
    elif d.field == "ip_address.prefix_length":
        _expect_unchanged(f"Prefix length of {d.object_key}", ip.address.prefixlen, d.documented)
        ip.address = netaddr.IPNetwork(f"{ip.address.ip}/{d.observed}")
    else:
        raise FixError(f"Cannot fix {d.field} in the documentation.")
    _save(ip, user, "change")
    return f"{d.field_label} set to {_show(d.observed)}."


def _create_ip(device, items, user) -> str:
    (d,) = items
    _require_perm(user, "ipam.add_ipaddress")
    observed = d.observed or {}
    if observed.get("prefix_length") is None:
        raise FixError("The device did not report the prefix length of this address.")
    iface_pks = interfaces_of(device).values_list("pk", flat=True)
    if any(normalize_ip(str(ip.address.ip)) == d.object_key for ip in ip_addresses_of(iface_pks)):
        raise FixError(f"{d.object_key} is already documented on {device}.")
    iface = _target_interface(device, observed.get("interface"), user)
    ip = IPAddress(
        address=netaddr.IPNetwork(f"{d.object_key}/{observed['prefix_length']}"),
        assigned_object=iface,
    )
    _save(ip, user, "add")
    return f"IP address {ip} created on {iface.name}."


def _delete_ip(device, items, user) -> str:
    (d,) = items
    ip = _ip_address(device, d.object_key, user, "delete")
    device = Device.objects.get(pk=device.pk)
    roles = {"primary_ip4": "primary IPv4", "primary_ip6": "primary IPv6", "oob_ip": "OOB IP"}
    for role, label in roles.items():
        if getattr(device, f"{role}_id") == ip.pk:
            raise FixError(
                f"{ip} is the device's {label}; NetBox would unset it. "
                "Change that in NetBox by hand."
            )
    _delete(ip)
    return f"IP address {ip} deleted."


# --- planning -------------------------------------------------------------------------------

Fix = Callable[[Device, list, object], str]

# Order matters: create interfaces before the addresses that go on them, and remove addresses
# before the interfaces that hold them.
_STEPS = (
    "create_interface",
    "device_type",
    "device_field",
    "interface_field",
    "create_ip",
    "ip_field",
    "delete_ip",
    "delete_interface",
)

_FIXES: dict[str, Fix] = {
    "create_interface": _create_interface,
    "device_type": _fix_device_type,
    "device_field": _fix_device_field,
    "interface_field": _fix_interface_field,
    "create_ip": _create_ip,
    "ip_field": _fix_ip_field,
    "delete_ip": _delete_ip,
    "delete_interface": _delete_interface,
}


_OBJECT_STEP = {"interface": "interface", "ip_address": "ip"}


def _step(d) -> str:
    if d.kind == DivergenceKindChoices.UNDOCUMENTED:
        return f"create_{_OBJECT_STEP[d.object_type]}"
    if d.kind == DivergenceKindChoices.MISSING_ON_DEVICE:
        return f"delete_{_OBJECT_STEP[d.object_type]}"
    if d.field in ("device.manufacturer", "device.model"):
        return "device_type"
    return {"device": "device_field", "interface": "interface_field", "ip_address": "ip_field"}[
        d.object_type
    ]


def plan(divergences: Iterable) -> list[tuple[Fix, list]]:
    """Group and order the divergences into fixes."""
    by_step: dict[str, list] = {step: [] for step in _STEPS}
    for d in divergences:
        by_step[_step(d)].append(d)
    ops: list[tuple[Fix, list]] = []
    for step in _STEPS:
        items = by_step[step]
        if step == "device_type":
            if items:
                ops.append((_FIXES[step], items))
        else:
            ops.extend((_FIXES[step], [d]) for d in items)
    return ops


def apply_documentation_fixes(device, divergences: Iterable, user) -> None:
    """Fix each divergence in NetBox. Sets ``resolution_status`` and ``resolution_detail`` on
    each divergence; the caller saves them."""
    for fix, items in plan(divergences):
        try:
            with transaction.atomic():
                detail = fix(device, items, user)
        except FixError as exc:
            status, detail = ResolutionStatusChoices.FAILED, str(exc)
        except ValidationError as exc:
            status, detail = (
                ResolutionStatusChoices.FAILED,
                "NetBox refused it: " + "; ".join(exc.messages),
            )
        except Exception as exc:
            logger.exception("Documentation fix crashed for %s", [d.pk for d in items])
            status = ResolutionStatusChoices.FAILED
            detail = f"Internal error: {type(exc).__name__}: {exc}"
        else:
            status = ResolutionStatusChoices.APPLIED
        for d in items:
            d.resolution_status = status
            d.resolution_detail = detail
