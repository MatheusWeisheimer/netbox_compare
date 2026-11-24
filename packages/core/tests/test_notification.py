from netbox_compare_core import (
    SEVERITIES,
    DeviceResult,
    DeviceStatus,
    DivergenceItem,
    severity_rank,
)


def divergence(severity):
    return DivergenceItem("interface", "GE0/0/1", "field", "interface.mtu", severity, 9000, 1500)


def test_severity_rank_orders_severities():
    assert [severity_rank(s) for s in SEVERITIES] == [1, 2, 3, 4]
    assert severity_rank(None) == 0
    assert severity_rank("bogus") == 0


def test_max_severity():
    device = DeviceResult(
        "r1",
        DeviceStatus.COMPLETED,
        divergences=(divergence("low"), divergence("critical"), divergence("medium")),
    )
    assert device.max_severity == "critical"
    assert DeviceResult("r2", DeviceStatus.COMPLETED).max_severity is None
