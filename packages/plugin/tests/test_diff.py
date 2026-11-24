import pytest

from netbox_compare.diff import Kind, Reason, compare, natural_key, validate_policy
from netbox_compare_core import (
    ALL_FIELDS,
    NOT_IN_SCHEMA,
    NOT_OBSERVED,
    DeviceRecord,
    InterfaceRecord,
    IPAddressRecord,
    Snapshot,
)

POLICY = {path: "medium" for path in ALL_FIELDS}


def documented(**kw):
    return Snapshot(
        device=DeviceRecord("r1", "Huawei", "S5720", "SN1", NOT_IN_SCHEMA),
        interfaces=kw.get(
            "interfaces",
            {
                "Gi0/0/1": InterfaceRecord("Gi0/0/1", True, "uplink", None, 1_000_000, None),
                "Gi0/0/2": InterfaceRecord("Gi0/0/2", True, "", None, None, None),
            },
        ),
        ip_addresses={"192.0.2.1": IPAddressRecord("192.0.2.1", "Gi0/0/1", 24)},
    )


def observed(**kw):
    return Snapshot(
        device=DeviceRecord("r1", "Huawei", "S5720", "SN1", "V200"),
        interfaces=kw.get(
            "interfaces",
            {
                "Gi0/0/1": InterfaceRecord(
                    "Gi0/0/1", True, "uplink", NOT_OBSERVED, 1_000_000, None
                ),
                "Gi0/0/2": InterfaceRecord("Gi0/0/2", True, "", NOT_OBSERVED, None, None),
            },
        ),
        ip_addresses={"192.0.2.1": IPAddressRecord("192.0.2.1", "Gi0/0/1", 24)},
    )


def test_identical_has_no_divergence():
    result = compare(documented(), observed(), POLICY)
    assert result.divergences == []
    reasons = {(nc.field, nc.reason) for nc in result.not_comparable}
    assert reasons == {
        ("device.os_version", Reason.NOT_IN_SCHEMA),
        ("interface.mtu", Reason.NOT_OBSERVED),
    }
    mtu = next(nc for nc in result.not_comparable if nc.field == "interface.mtu")
    assert mtu.keys == ("Gi0/0/1", "Gi0/0/2")


def test_field_divergence_and_blank_is_a_value():
    obs = observed()
    obs.interfaces["Gi0/0/2"].description = "spare"
    obs.interfaces["Gi0/0/2"].speed = 1_000_000  # documented blank (None)
    result = compare(documented(), obs, POLICY)
    got = {(d.key, d.field, d.documented, d.observed) for d in result.divergences}
    assert got == {
        ("Gi0/0/2", "interface.description", "", "spare"),
        ("Gi0/0/2", "interface.speed", None, 1_000_000),
    }
    assert all(d.kind == Kind.FIELD for d in result.divergences)


def test_object_level_classes():
    doc = documented()
    doc.interfaces["Gi0/0/9"] = InterfaceRecord("Gi0/0/9", True, "gone", None, None, None)
    obs = observed()
    obs.interfaces["NULL0"] = InterfaceRecord("NULL0", True, "", 1500, NOT_OBSERVED, None)
    result = compare(doc, obs, POLICY)
    by_key = {d.key: d for d in result.divergences}
    assert by_key["Gi0/0/9"].kind == Kind.MISSING_ON_DEVICE
    assert by_key["Gi0/0/9"].documented["description"] == "gone"
    assert by_key["NULL0"].kind == Kind.UNDOCUMENTED
    assert by_key["NULL0"].observed == {
        "name": "NULL0",
        "enabled": True,
        "description": "",
        "mtu": 1500,
        "mac_address": None,
    }


def test_policy_drops_unconsidered_fields_and_presence():
    obs = observed()
    obs.interfaces["Gi0/0/2"].description = "spare"
    obs.interfaces["NULL0"] = InterfaceRecord("NULL0")
    policy = {"interface.enabled": "high"}
    result = compare(documented(), obs, policy)
    assert result.divergences == []
    assert result.not_comparable == []


def test_severity_comes_from_policy():
    obs = observed()
    obs.device.serial_number = "SN2"
    result = compare(documented(), obs, {**POLICY, "device.serial_number": "critical"})
    (div,) = result.divergences
    assert (div.field, div.severity, div.key) == ("device.serial_number", "critical", "")


def test_unobserved_collection_is_not_comparable_not_missing():
    obs = observed()
    obs.interfaces = None
    readable = ALL_FIELDS - {f for f in ALL_FIELDS if f.startswith("interface.")}
    result = compare(documented(), obs, POLICY, readable=readable)
    assert not [d for d in result.divergences if d.object_type == "interface"]
    reasons = {nc.reason for nc in result.not_comparable if nc.field.startswith("interface.")}
    assert reasons == {Reason.NOT_READABLE}


def test_not_readable_vs_not_observed():
    readable = ALL_FIELDS - {"interface.mtu"}
    result = compare(documented(), observed(), POLICY, readable=readable)
    mtu = next(nc for nc in result.not_comparable if nc.field == "interface.mtu")
    assert mtu.reason == Reason.NOT_READABLE


def test_bool_is_not_int():
    doc = documented()
    doc.interfaces["Gi0/0/1"].mtu = 1
    obs = observed()
    obs.interfaces["Gi0/0/1"].mtu = True
    result = compare(doc, obs, {"interface.mtu": "low"})
    assert len(result.divergences) == 1


def test_validate_policy():
    with pytest.raises(ValueError):
        validate_policy({"interface.colour": "low"})
    with pytest.raises(ValueError):
        validate_policy({"interface.mtu": "urgent"})


def test_natural_key():
    names = ["Gi0/0/10", "Gi0/0/2", "Gi0/0/1"]
    assert sorted(names, key=natural_key) == ["Gi0/0/1", "Gi0/0/2", "Gi0/0/10"]
