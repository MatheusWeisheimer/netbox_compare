"""Live test against a real Zabbix. Run with: uv run pytest -m live

Needs NBC_ZBX_URL, NBC_ZBX_TOKEN and NBC_ZBX_TEST_HOST: a host linked to the
"netbox-compare drift" template (contrib/zabbix_template.yaml). NBC_ZBX_TRAPPER (host[:port])
also tests the trapper transport.
"""

import os
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from netbox_compare_zabbix.module import ZabbixNotifier
from zbxreports import completed, divergence, report

pytestmark = pytest.mark.live


def live_report(host):
    r = report(completed(host, divergence("medium")))
    now = datetime.now(UTC)
    return replace(r, completed=now, devices=tuple(replace(d, completed=now) for d in r.devices))


@pytest.fixture
def env():
    missing = [
        v for v in ("NBC_ZBX_URL", "NBC_ZBX_TOKEN", "NBC_ZBX_TEST_HOST") if not os.environ.get(v)
    ]
    if missing:
        pytest.skip(f"missing env vars: {missing}")
    return os.environ


def test_api_live(env):
    n = ZabbixNotifier(
        {
            "url": env["NBC_ZBX_URL"],
            "token": env["NBC_ZBX_TOKEN"],
            "verify": env.get("NBC_ZBX_VERIFY", True),
        }
    )
    assert n.notify(live_report(env["NBC_ZBX_TEST_HOST"])) == "Sent 4 values for 1 hosts."


def test_trapper_live(env):
    if not env.get("NBC_ZBX_TRAPPER"):
        pytest.skip("NBC_ZBX_TRAPPER not set")
    server, _, port = env["NBC_ZBX_TRAPPER"].partition(":")
    n = ZabbixNotifier({"transport": "trapper", "server": server, "port": int(port or 10051)})
    assert n.notify(live_report(env["NBC_ZBX_TEST_HOST"])) == "Sent 4 values for 1 hosts."
