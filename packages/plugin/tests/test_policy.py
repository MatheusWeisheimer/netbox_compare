import pytest

from netbox_compare.policy import DEFAULT_POLICY, considered, validate_policy_fields
from netbox_compare_core import ALL_FIELDS


def test_missing_fields_are_completed_disabled_with_default_severity():
    out = validate_policy_fields({"interface.mtu": {"enabled": True, "severity": "critical"}})
    assert set(out) == ALL_FIELDS
    assert out["interface.mtu"] == {"enabled": True, "severity": "critical"}
    assert out["device.model"] == {"enabled": False, "severity": DEFAULT_POLICY["device.model"]}


def test_disabled_field_keeps_its_severity_but_is_not_considered():
    fields = validate_policy_fields(
        {
            "interface.mtu": {"enabled": False, "severity": "critical"},
            "interface.description": {"enabled": True, "severity": "low"},
        }
    )
    assert fields["interface.mtu"]["severity"] == "critical"
    assert considered(fields) == {"interface.description": "low"}


@pytest.mark.parametrize(
    "raw",
    [
        {"interface.bogus": {"enabled": True, "severity": "low"}},
        {"interface.mtu": {"enabled": True, "severity": "urgent"}},
        {"interface.mtu": {"enabled": "yes", "severity": "low"}},
        {"interface.mtu": "low"},
        {"interface.mtu": {"enabled": True, "severity": "low", "extra": 1}},
        {"interface.mtu": {"enabled": False, "severity": "low"}},  # nothing enabled
        {},
        ["interface.mtu"],
    ],
)
def test_invalid(raw):
    with pytest.raises(ValueError):
        validate_policy_fields(raw)
