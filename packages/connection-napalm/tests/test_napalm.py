import pytest

from netbox_compare_core import (
    ALL_FIELDS,
    NOT_OBSERVED,
    ConnectionModuleError,
    Credentials,
)
from netbox_compare_napalm.fixups import parse_vrp_admin_state, parse_vrp_manufacture_info
from netbox_compare_napalm.module import NapalmModule

# Trimmed output recorded from a Huawei S5720 (V200R011C10SPC600) via napalm-huawei-vrp 1.2.0.
FACTS = {
    "uptime": 34537080,
    "vendor": "Huawei",
    "os_version": "V200R011C10SPC600",
    "serial_number": [],
    "model": "S5720-36C-EI-AC",
    "hostname": "teste",
    "fqdn": "Unknown",
    "interface_list": ["GigabitEthernet0/0/1", "GigabitEthernet0/0/2", "NULL0"],
}
INTERFACES = {
    "GigabitEthernet0/0/1": {
        "is_up": False,
        "is_enabled": False,
        "description": '"interface de testes"',
        "last_flapped": -1.0,
        "mtu": -1,
        "speed": 1000.0,
        "mac_address": "F4:79:60:E5:8D:90",
    },
    "GigabitEthernet0/0/2": {
        "is_up": False,
        "is_enabled": False,
        "description": "",
        "last_flapped": -1.0,
        "mtu": -1,
        "speed": 1000.0,
        "mac_address": "F4:79:60:E5:8D:90",
    },
    "NULL0": {
        "is_up": True,
        "is_enabled": True,
        "description": "",
        "last_flapped": -1.0,
        "mtu": 1500,
        "speed": -1.0,
        "mac_address": "",
    },
}
INTERFACES_IP = {
    "MEth0/0/1": {"ipv4": {"200.132.1.28": {"prefix_length": 24}}},
    "Vlanif1": {"ipv6": {"FE80::1": {"prefix_length": 64}, "2001:DB8::1": {"prefix_length": 64}}},
}
BRIEF = """PHY: Physical
*down: administratively down
#down: LBDT down
InUti/OutUti: input utility/output utility
Interface                   PHY   Protocol  InUti OutUti   inErrors  outErrors
GigabitEthernet0/0/1        down  down         0%     0%          0          0
GigabitEthernet0/0/2        *down down         0%     0%          0          0
NULL0                       up    up(s)        0%     0%          0          0
"""
MANUFACTURE_INFO = """Slot  Sub  Serial-number          Manu-date
- - - - - - - - - - - - - - - - - - - - - -
0     -    2102359562DMK6003661   2019-06-25
"""
CREDS = Credentials("192.0.2.1", "admin", "pw")


class FakeDriver:
    instances: list["FakeDriver"] = []

    def __init__(self, hostname, username, password, timeout, optional_args):
        self.kwargs = dict(
            hostname=hostname,
            username=username,
            password=password,
            timeout=timeout,
            optional_args=optional_args,
        )
        self.opened = self.closed = False
        self.commands: list[str] = []
        FakeDriver.instances.append(self)

    def open(self):
        self.opened = True

    def close(self):
        self.closed = True

    def get_facts(self):
        return FACTS

    def get_interfaces(self):
        return INTERFACES

    def get_interfaces_ip(self):
        return INTERFACES_IP

    def cli(self, commands):
        self.commands.extend(commands)
        outputs = {
            "display interface brief": BRIEF,
            "display device manufacture-info": MANUFACTURE_INFO,
        }
        return {c: outputs.get(c, "") for c in commands}


def module(**platform):
    cfg = {"driver": "huawei_vrp", **platform}
    return NapalmModule({"platforms": {"huawei-vrp": cfg}}, driver_loader=lambda name: FakeDriver)


def test_capabilities():
    caps = module(exclude_fields=["interface.mtu"]).capabilities()["huawei-vrp"]
    assert caps.readable == ALL_FIELDS - {"interface.mtu"}
    assert caps.writable == frozenset()
    assert caps.exec_commands


def test_config_validation():
    with pytest.raises(ConnectionModuleError):
        NapalmModule({"platforms": {"x": {}}})
    with pytest.raises(ConnectionModuleError):
        module(exclude_fields=["interface.colour"])


def test_read_vrp_applies_fixups():
    with module(optional_args={"port": 22}).open("huawei-vrp", CREDS) as session:
        snap = session.read(ALL_FIELDS)
    driver = FakeDriver.instances[-1]
    assert driver.opened and driver.closed
    assert driver.kwargs["optional_args"] == {"port": 22}

    assert snap.device.name == "teste"
    assert snap.device.manufacturer == "Huawei"
    assert snap.device.serial_number == "2102359562DMK6003661"
    assert snap.device.os_version == "V200R011C10SPC600"

    gi1 = snap.interfaces["GigabitEthernet0/0/1"]
    assert gi1.description == "interface de testes"
    assert gi1.enabled is True  # link down, but not shut down
    assert gi1.mtu is NOT_OBSERVED
    assert gi1.speed == 1_000_000
    assert gi1.mac_address == "F4:79:60:E5:8D:90"
    assert snap.interfaces["GigabitEthernet0/0/2"].enabled is False
    null0 = snap.interfaces["NULL0"]
    assert null0.mac_address is None
    assert null0.speed is NOT_OBSERVED
    assert null0.mtu == 1500

    assert set(snap.ip_addresses) == {"200.132.1.28", "2001:db8::1"}
    assert snap.ip_addresses["200.132.1.28"].interface == "MEth0/0/1"
    assert snap.ip_addresses["200.132.1.28"].prefix_length == 24


def test_read_returns_only_requested_fields():
    with module().open("huawei-vrp", CREDS) as session:
        snap = session.read(["interface.description"])
    assert snap.device.name is NOT_OBSERVED
    assert snap.ip_addresses is None
    assert snap.interfaces["GigabitEthernet0/0/1"].enabled is NOT_OBSERVED
    assert "display interface brief" not in FakeDriver.instances[-1].commands


def test_unknown_platform():
    with pytest.raises(ConnectionModuleError):
        module().open("ios", CREDS)


def test_connect_failure_is_wrapped():
    class Refusing(FakeDriver):
        def open(self):
            raise OSError("connection refused")

    mod = NapalmModule({"platforms": {"p": {"driver": "x"}}}, driver_loader=lambda n: Refusing)
    with pytest.raises(ConnectionModuleError, match="connection refused"):
        mod.open("p", CREDS)


def test_all_getters_failing_raises():
    class Broken(FakeDriver):
        def get_facts(self):
            raise RuntimeError("boom")

    mod = NapalmModule({"platforms": {"p": {"driver": "x"}}}, driver_loader=lambda n: Broken)
    with mod.open("p", CREDS) as session, pytest.raises(ConnectionModuleError):
        session.read(["device.name"])


def test_parse_vrp_admin_state():
    assert parse_vrp_admin_state(BRIEF) == {
        "GigabitEthernet0/0/1": True,
        "GigabitEthernet0/0/2": False,
        "NULL0": True,
    }


def test_parse_vrp_manufacture_info_stack_is_ambiguous():
    assert parse_vrp_manufacture_info(MANUFACTURE_INFO) == "2102359562DMK6003661"
    stack = MANUFACTURE_INFO + "1     -    2102359562DMK6009999   2019-06-25\n"
    assert parse_vrp_manufacture_info(stack) is NOT_OBSERVED
