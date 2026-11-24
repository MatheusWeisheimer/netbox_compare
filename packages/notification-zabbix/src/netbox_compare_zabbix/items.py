"""Translate a run report into Zabbix item values, one set per device host.

Each device is a Zabbix host with the same name (or mapped in config) that carries the
"netbox-compare drift" template (contrib/zabbix_template.yaml). Its trapper items:

* ``<prefix>.severity``: highest divergence severity, 0 (none) to 4 (critical). Triggers fire
  per level; a later run with no drift sends 0 and the problem resolves.
* ``<prefix>.divergences``: number of divergences.
* ``<prefix>.status``: 0 compared, 1 could not compare (comparison failed, or the credentials
  backend failed).
* ``<prefix>.report``: a short text summary.

A failed comparison sends only status and report: the last known drift stays as it was.
Devices skipped for setup reasons (no connection module, no credentials) send nothing.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from netbox_compare_core import (
    SEVERITIES,
    DeviceResult,
    DeviceStatus,
    DivergenceItem,
    RunReport,
    SkipReason,
    severity_rank,
)

DEFAULT_PREFIX = "netbox.compare"
MAX_REPORT_LINES = 20

KIND_TEXT = {
    "undocumented": "only on the device",
    "missing_on_device": "documented but not found on the device",
}


@dataclass(frozen=True)
class ItemValue:
    host: str
    key: str
    value: str | int
    clock: int  # Unix seconds


def report_values(
    report: RunReport, prefix: str = DEFAULT_PREFIX, hosts: dict[str, str] | None = None
) -> list[ItemValue]:
    hosts = hosts or {}
    values: list[ItemValue] = []
    for device in report.devices:
        host = hosts.get(device.name, device.name)
        clock = _clock(device.completed or report.completed)

        def item(name: str, value: str | int, host: str = host, clock: int = clock) -> None:
            values.append(ItemValue(host, f"{prefix}.{name}", value, clock))

        if device.status == DeviceStatus.COMPLETED:
            item("severity", severity_rank(device.max_severity))
            item("divergences", len(device.divergences))
            item("status", 0)
            item("report", device_summary(device, report))
        elif device.status == DeviceStatus.FAILED:
            item("status", 1)
            item("report", _with_header(f"Comparison failed: {device.error}", report))
        elif device.skip_reason == SkipReason.CREDENTIALS_ERROR:
            item("status", 1)
            item(
                "report",
                _with_header("Not compared: the credentials backend failed", report),
            )
    return values


def device_summary(device: DeviceResult, report: RunReport) -> str:
    if not device.divergences:
        text = "No divergences"
    else:
        counts = Counter(d.severity for d in device.divergences)
        by_severity = ", ".join(f"{s}: {counts[s]}" for s in reversed(SEVERITIES) if counts[s])
        ordered = sorted(device.divergences, key=lambda d: -severity_rank(d.severity))
        lines = [f"{len(device.divergences)} divergences ({by_severity})"]
        lines += [f"- {divergence_line(d)}" for d in ordered[:MAX_REPORT_LINES]]
        if len(ordered) > MAX_REPORT_LINES:
            lines.append(f"... and {len(ordered) - MAX_REPORT_LINES} more")
        text = "\n".join(lines)
    return _with_header(text, report)


def divergence_line(d: DivergenceItem) -> str:
    target = "device" if d.object_type == "device" else f"{d.object_type} {d.object_key}"
    if d.kind in KIND_TEXT:
        return f"[{d.severity}] {target}: {KIND_TEXT[d.kind]}"
    field = d.field.split(".", 1)[-1]
    return (
        f"[{d.severity}] {target}: {field} documented {_show(d.documented)}, "
        f"observed {_show(d.observed)}"
    )


def _show(value: Any) -> str:
    if value is None or value == "":
        return "(blank)"
    return repr(value) if isinstance(value, str) else str(value)


def _with_header(text: str, report: RunReport) -> str:
    header = f"netbox-compare: {report.schedule_name} (run #{report.run_id})"
    return f"{header}\n{text}"


def _clock(when: datetime) -> int:
    return int(when.timestamp())
