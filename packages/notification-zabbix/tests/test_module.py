from unittest import mock

import pytest

from netbox_compare_core import NotificationError
from netbox_compare_zabbix.module import ZabbixNotifier
from netbox_compare_zabbix.transport import ApiTransport, PushResult, TrapperTransport
from zbxreports import completed, divergence, failed, report, skipped


def notifier(push_result):
    n = ZabbixNotifier({"url": "http://zbx", "token": "t"})
    n.transport = mock.Mock()
    n.transport.push.return_value = push_result
    return n


def test_transport_selection():
    assert isinstance(ZabbixNotifier({"url": "u", "token": "t"}).transport, ApiTransport)
    trapper = ZabbixNotifier({"transport": "trapper", "server": "zbx"}).transport
    assert isinstance(trapper, TrapperTransport) and trapper.port == 10051
    with pytest.raises(ValueError):
        ZabbixNotifier({"transport": "api"})
    with pytest.raises(ValueError):
        ZabbixNotifier({"transport": "smoke"})


def test_summary():
    n = notifier(PushResult(accepted=4))
    assert n.notify(report(completed("r1", divergence()))) == "Sent 4 values for 1 hosts."


def test_partial_rejection_names_hosts():
    n = notifier(
        PushResult(
            accepted=4,
            failed=4,
            errors=[("r2", "k", "No permissions to referred object or it does not exist.")] * 4,
        )
    )
    summary = n.notify(report(completed("r1"), completed("r2")))
    assert summary.startswith("Sent 4 values for 2 hosts. 4 rejected.")
    assert "r2: host or item not found" in summary


def test_everything_rejected_raises():
    n = notifier(PushResult(failed=2))
    with pytest.raises(NotificationError, match="rejected every value"):
        n.notify(report(failed("r1")))


def test_nothing_to_send():
    n = notifier(PushResult())
    assert n.notify(report(skipped("r1"))).startswith("Nothing to send")
    n.transport.push.assert_not_called()
