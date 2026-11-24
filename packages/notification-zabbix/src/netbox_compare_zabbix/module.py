"""The ``zabbix`` notification module.

Config (``PLUGINS_CONFIG["netbox_compare"]["notifications"]`` entry):

* ``transport``: ``"api"`` (default; ``history.push``, Zabbix 7.0+) or ``"trapper"``.
* API: ``url`` (frontend URL or full ``.../api_jsonrpc.php``), ``token``, ``verify`` (bool or
  CA bundle path, default True).
* Trapper: ``server``, ``port`` (default 10051).
* ``timeout``: seconds, default 10.
* ``item_prefix``: item key prefix, default ``netbox.compare`` (as in the shipped template).
* ``hosts``: optional ``{NetBox device name: Zabbix host name}`` for devices whose names differ.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from netbox_compare_core import NotificationError, NotificationModule, RunReport
from netbox_compare_zabbix.items import DEFAULT_PREFIX, report_values
from netbox_compare_zabbix.transport import ApiTransport, PushResult, TrapperTransport

BATCH = 1000
MISSING_HINT = (
    "host or item not found: is the host in Zabbix, linked to the netbox-compare template, "
    "and readable with the API token?"
)


class ZabbixNotifier(NotificationModule):
    def __init__(self, config: Mapping[str, Any]) -> None:
        super().__init__(config)
        self.prefix = config.get("item_prefix") or DEFAULT_PREFIX
        self.hosts = dict(config.get("hosts") or {})
        timeout = float(config.get("timeout", 10))
        kind = config.get("transport", "api")
        if kind == "api":
            if not config.get("url") or not config.get("token"):
                raise ValueError("the api transport needs 'url' and 'token'")
            self.transport = ApiTransport(
                config["url"], config["token"], verify=config.get("verify", True), timeout=timeout
            )
        elif kind == "trapper":
            if not config.get("server"):
                raise ValueError("the trapper transport needs 'server'")
            self.transport = TrapperTransport(
                config["server"], config.get("port", 10051), timeout=timeout
            )
        else:
            raise ValueError(f"unknown transport {kind!r}; use 'api' or 'trapper'")

    def notify(self, report: RunReport) -> str:
        values = report_values(report, prefix=self.prefix, hosts=self.hosts)
        if not values:
            return "Nothing to send: no device was compared."
        result = PushResult()
        for start in range(0, len(values), BATCH):
            part = self.transport.push(values[start : start + BATCH])
            result.accepted += part.accepted
            result.failed += part.failed
            result.errors += part.errors
        hosts = len({v.host for v in values})
        if result.accepted == 0:
            raise NotificationError(f"Zabbix rejected every value. {_describe(result)}".strip())
        summary = f"Sent {result.accepted} values for {hosts} hosts."
        if result.failed:
            summary += f" {result.failed} rejected. {_describe(result)}".rstrip()
        return summary


def _describe(result: PushResult) -> str:
    if not result.errors:
        return ""
    by_error: dict[str, set[str]] = defaultdict(set)
    for host, _key, error in result.errors:
        by_error[error].add(host)
    parts = []
    for error, hosts in by_error.items():
        text = MISSING_HINT if "does not exist" in error else error
        parts.append(f"{', '.join(sorted(hosts))}: {text}")
    return "\n".join(parts)
