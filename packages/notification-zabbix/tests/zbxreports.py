from datetime import UTC, datetime

from netbox_compare_core import DeviceResult, DeviceStatus, DivergenceItem, RunReport, SkipReason

DONE = datetime(2026, 11, 24, 3, 5, tzinfo=UTC)


def divergence(
    severity="high", kind="field", field="interface.mtu", documented=9000, observed=1500
):
    return DivergenceItem("interface", "GE0/0/1", kind, field, severity, documented, observed)


def report(*devices, url="https://nb/plugins/compare/runs/7/"):
    return RunReport(
        run_id=7,
        schedule_name="nightly",
        policy_name="default",
        started=DONE,
        completed=DONE,
        devices=tuple(devices),
        url=url,
    )


def completed(name="r1", *divergences):
    return DeviceResult(name, DeviceStatus.COMPLETED, divergences=divergences, completed=DONE)


def failed(name="r1", error="timeout"):
    return DeviceResult(name, DeviceStatus.FAILED, error=error, completed=DONE)


def skipped(name="r1", reason=SkipReason.NO_CREDENTIALS):
    return DeviceResult(name, DeviceStatus.SKIPPED, skip_reason=reason)
