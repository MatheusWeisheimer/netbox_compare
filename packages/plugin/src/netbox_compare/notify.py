"""Send a finalized scheduled run to its notification modules.

The run is translated into a :class:`netbox_compare_core.RunReport` (no ORM objects leave the
plugin) and handed to each module linked to the run. Notifications only report; they never
apply fixes.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from netbox_compare.choices import ComparisonStatusChoices, DeliveryStatusChoices
from netbox_compare.modules import notification_module
from netbox_compare_core import (
    DeviceResult,
    DeviceStatus,
    DivergenceItem,
    NotificationError,
    RunReport,
    SkipReason,
)

logger = logging.getLogger(__name__)


def build_report(run) -> RunReport:
    devices = []
    comparisons = (
        run.comparisons.select_related("device")
        .prefetch_related("divergences")
        .order_by("device__name", "pk")
    )
    for c in comparisons:
        name = c.device.name or str(c.device)
        if c.status == ComparisonStatusChoices.COMPLETED:
            devices.append(
                DeviceResult(
                    name=name,
                    status=DeviceStatus.COMPLETED,
                    divergences=tuple(
                        DivergenceItem(
                            object_type=d.object_type,
                            object_key=d.object_key,
                            kind=d.kind,
                            field=d.field,
                            severity=d.severity,
                            documented=d.documented,
                            observed=d.observed,
                        )
                        for d in c.divergences.all()
                    ),
                    completed=c.completed,
                )
            )
        else:
            devices.append(
                DeviceResult(
                    name=name,
                    status=DeviceStatus.FAILED,
                    error=c.error or "The comparison did not finish",
                    completed=c.completed,
                )
            )
    for s in run.skipped:
        try:
            reason = SkipReason(s["reason"])
        except ValueError:
            reason = None
        devices.append(
            DeviceResult(name=s["name"], status=DeviceStatus.SKIPPED, skip_reason=reason)
        )
    return RunReport(
        run_id=run.pk,
        schedule_name=run.name,
        policy_name=run.policy.name if run.policy else None,
        started=run.created,
        completed=run.finalized or timezone.now(),
        devices=tuple(devices),
    )


def send_notifications(run, log: logging.Logger = logger) -> None:
    """Deliver the run to every module whose delivery is pending. Each module is independent:
    one failing does not stop the others."""
    deliveries = list(run.deliveries.filter(status=DeliveryStatusChoices.PENDING))
    if not deliveries:
        return
    report = build_report(run)
    for delivery in deliveries:
        module = notification_module(delivery.module)
        if module is None:
            status = DeliveryStatusChoices.FAILED
            detail = "The notification module is not configured, or failed to load"
        else:
            try:
                detail = module.notify(report) or ""
                status = DeliveryStatusChoices.SENT
            except NotificationError as exc:
                status, detail = DeliveryStatusChoices.FAILED, str(exc)
            except Exception as exc:
                log.exception("Notification module %r crashed", delivery.module)
                status = DeliveryStatusChoices.FAILED
                detail = f"Internal error: {type(exc).__name__}: {exc}"
        log.info("Notification %r: %s %s", delivery.module, status, detail)
        delivery.status = status
        delivery.detail = detail
        delivery.attempted = timezone.now()
        delivery.save(update_fields=["status", "detail", "attempted"])
