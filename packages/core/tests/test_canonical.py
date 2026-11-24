import copy

import pytest

from netbox_compare_core import (
    NOT_OBSERVED,
    DeviceRecord,
    InterfaceRecord,
    Snapshot,
    normalize_ip,
    normalize_mac,
)


def test_not_observed_is_distinct_from_blank():
    assert NOT_OBSERVED is not None
    assert NOT_OBSERVED != ""
    assert copy.deepcopy(NOT_OBSERVED) is NOT_OBSERVED


@pytest.mark.parametrize(
    "raw",
    ["f479-60e5-8d90", "F4:79:60:E5:8D:90", "f4.79.60.e5.8d.90", "f47960e58d90"],
)
def test_normalize_mac(raw):
    assert normalize_mac(raw) == "F4:79:60:E5:8D:90"


def test_normalize_mac_blank_and_invalid():
    assert normalize_mac("") is None
    assert normalize_mac(None) is None
    with pytest.raises(ValueError):
        normalize_mac("12:34")


def test_normalize_ip():
    assert normalize_ip("2001:DB8:0::1/64") == "2001:db8::1"
    assert normalize_ip("192.0.2.1") == "192.0.2.1"


def test_restrict_keeps_only_requested():
    snap = Snapshot(
        device=DeviceRecord(name="r1", serial_number="X"),
        interfaces={"Gi0": InterfaceRecord("Gi0", mtu=1500, description="up")},
        ip_addresses={},
    )
    out = snap.restrict(["device.name", "interface.mtu"])
    assert out.device.name == "r1"
    assert out.device.serial_number is NOT_OBSERVED
    assert out.interfaces["Gi0"].mtu == 1500
    assert out.interfaces["Gi0"].description is NOT_OBSERVED
    assert out.ip_addresses is None
