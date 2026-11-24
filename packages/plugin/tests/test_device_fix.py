from netbox_compare.device_fix import device_feasibility
from netbox_compare_core import ALL_FIELDS, PlatformCapabilities

READ_ONLY = PlatformCapabilities(readable=ALL_FIELDS)
WRITER = PlatformCapabilities(
    readable=ALL_FIELDS, writable=frozenset({"interface.description", "ip_address.address"})
)


def test_read_only_fact_is_never_possible():
    result = device_feasibility("interface.mac_address", "vrp", [("w", {"vrp": WRITER})])
    assert not result.possible
    assert "read-only fact" in result.reason
    # Presence of an interface is keyed by its name, a fact: it cannot be created on the device.
    assert not device_feasibility("interface.name", "vrp", [("w", {"vrp": WRITER})]).possible


def test_config_attribute_without_writer():
    result = device_feasibility("interface.description", "vrp", [("napalm", {"vrp": READ_ONLY})])
    assert not result.possible
    assert result.modules == {"napalm": False}
    assert "napalm" in result.reason


def test_any_module_declaring_the_platform_is_considered():
    modules = [("napalm", {"vrp": READ_ONLY}), ("netconf", {"vrp": WRITER, "ios": READ_ONLY})]
    result = device_feasibility("interface.description", "vrp", modules)
    assert result.possible
    assert result.writers == ["netconf"]
    assert result.modules == {"napalm": False, "netconf": True}
    assert device_feasibility("ip_address.address", "vrp", modules).possible


def test_platform_not_declared_or_missing():
    assert not device_feasibility("interface.mtu", "eos", [("w", {"vrp": WRITER})]).possible
    assert not device_feasibility("interface.mtu", None, [("w", {"vrp": WRITER})]).possible
    assert not device_feasibility("interface.nope", "vrp", [("w", {"vrp": WRITER})]).possible
