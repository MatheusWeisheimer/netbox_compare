import logging
from datetime import timedelta

from core.choices import JobStatusChoices
from django.db import transaction
from django.utils import timezone
from netbox.jobs import JobRunner

from netbox_compare.choices import (
    ComparisonStatusChoices,
    DeliveryStatusChoices,
    SkipReasonChoices,
)
from netbox_compare.credentials import resolve_credentials
from netbox_compare.models import (
    Comparison,
    ComparisonRun,
    ComparisonSchedule,
    NotificationDelivery,
)
from netbox_compare.modules import connection_for_platform
from netbox_compare.runner import run_comparison

logger = logging.getLogger(__name__)

# Minutes after a scheduled run starts at which it is finalized (and notified) even if some
# comparisons have not finished; those are marked failed.
NOTIFICATION_DEADLINE = 60

# Queued but not started. A running job is left alone: it finishes, and sync runs after it.
QUEUED = (JobStatusChoices.STATUS_PENDING, JobStatusChoices.STATUS_SCHEDULED)


class CompareDeviceJob(JobRunner):
    """Background job running one :class:`Comparison`. Detects and reports only; it never
    applies fixes."""

    class Meta:
        name = "Device comparison"

    def run(self, comparison_id, *args, **kwargs):
        comparison = Comparison.objects.select_related("device__platform", "policy").get(
            pk=comparison_id
        )
        run_comparison(comparison, log=self.logger)

    @classmethod
    def handle(cls, job, *args, **kwargs):
        # super().handle() catches every exception (including job timeouts), so a run's last
        # comparison always gets here, whether it completed or failed.
        super().handle(job, *args, **kwargs)
        comparison_id = kwargs.get("comparison_id")
        run_id = (
            Comparison.objects.filter(pk=comparison_id).values_list("run_id", flat=True).first()
        )
        if run_id:
            try:
                finalize_run(run_id)
            except Exception:
                logger.exception("Could not finalize run %s", run_id)


@transaction.atomic
def enqueue_comparison(device, user, policy, run=None) -> Comparison:
    comparison = Comparison(device=device, requested_by=user, policy=policy, run=run)
    comparison.full_clean()
    comparison.save()
    # NetBox only attaches jobs to models with the `jobs` feature (JobsMixin); Device has none,
    # so the job belongs to the comparison.
    job = CompareDeviceJob.enqueue(instance=comparison, user=user, comparison_id=comparison.pk)
    comparison.job = job
    comparison.save(update_fields=["job"])
    return comparison


class ScheduledComparisonJob(JobRunner):
    """Starts one :class:`ComparisonRun` of a scheduled job (:class:`ComparisonSchedule`).

    Each instance is a one-off NetBox job at the schedule's next run time; when it finishes it
    queues the next one (months have no fixed length, so NetBox's minute intervals do not fit).
    It only selects the devices and queues one :class:`CompareDeviceJob` per device, so a run
    over many devices is spread across the workers and never hits the job timeout as a whole.
    Like every comparison, it detects and reports only; it never applies fixes."""

    class Meta:
        name = "Scheduled comparison"

    def run(self, *args, **kwargs):
        schedule = ComparisonSchedule.objects.filter(pk=self.job.object_id).first()
        if schedule is None:
            self.logger.warning("The scheduled job was deleted; nothing to run")
            return
        if not schedule.enabled:
            self.logger.info("Scheduled job %s is disabled; skipping this run", schedule)
            return
        run = start_run(schedule, user=self.job.user, job=self.job, log=self.logger)
        self.logger.info(
            "Run %s: %d devices queued, %d skipped",
            run.pk,
            run.comparisons.count(),
            len(run.skipped),
        )

    @classmethod
    def handle(cls, job, *args, **kwargs):
        super().handle(job, *args, **kwargs)
        # Queue the next run (none if the schedule does not repeat, is disabled or is gone).
        if job.object_id:
            sync_schedule(job.object_id)


def start_run(schedule, user=None, job=None, log=logger) -> ComparisonRun:
    """Select the schedule's devices and queue a comparison of each one that can be compared:
    its platform has a connection module and a credentials module resolves it. The others are
    recorded in the run as skipped."""
    selected, skipped = [], []
    devices = (
        schedule.target_devices()
        .select_related("platform", "primary_ip4", "primary_ip6")
        .order_by("name", "pk")
    )
    for device in devices:
        platform = device.platform.slug if device.platform else None
        reason = None
        if connection_for_platform(platform) is None:
            reason = SkipReasonChoices.NO_CONNECTION_MODULE
        else:
            try:
                if resolve_credentials(device) is None:
                    reason = SkipReasonChoices.NO_CREDENTIALS
            except Exception:
                log.exception("Credential resolution crashed for device %s", device)
                reason = SkipReasonChoices.CREDENTIALS_ERROR
        if reason:
            skipped.append({"device": device.pk, "name": str(device), "reason": reason})
        else:
            selected.append(device)

    with transaction.atomic():
        run = ComparisonRun(
            schedule=schedule,
            name=schedule.name,
            policy=schedule.policy,
            requested_by=user,
            job=job,
            skipped=skipped,
        )
        run.full_clean()
        run.save()
        NotificationDelivery.objects.bulk_create(
            NotificationDelivery(run=run, module=name) for name in schedule.notifications
        )
        for device in selected:
            enqueue_comparison(device, user, schedule.policy, run=run)
        if selected:
            # Backstop: a comparison whose worker dies never reports back.
            FinalizeRunJob.enqueue(
                instance=run, schedule_at=timezone.now() + timedelta(minutes=NOTIFICATION_DEADLINE)
            )
    if not selected:
        finalize_run(run.pk)
    return run


class FinalizeRunJob(JobRunner):
    """Finalizes a run whose comparisons did not all finish by the notification deadline;
    the unfinished ones are marked failed. Removed when the run finalizes in time."""

    class Meta:
        name = "Scheduled comparison deadline"

    def run(self, *args, **kwargs):
        if finalize_run(self.job.object_id, deadline_passed=True, log=self.logger):
            self.logger.info("Run finalized at its deadline")
        else:
            self.logger.info("Run already finalized; nothing to do")


class NotifyRunJob(JobRunner):
    """Sends a finalized run to its notification modules. A separate job, so a slow or
    unreachable notification channel never holds up a comparison."""

    class Meta:
        name = "Scheduled comparison notification"

    def run(self, *args, **kwargs):
        from netbox_compare.notify import send_notifications

        run = ComparisonRun.objects.select_related("policy").filter(pk=self.job.object_id).first()
        if run is None:
            self.logger.warning("The run was deleted; nothing to send")
            return
        send_notifications(run, log=self.logger)


def finalize_run(run_id, deadline_passed=False, log=logger) -> bool:
    """Finalize the run once all its comparisons are final, or now if ``deadline_passed``
    (unfinished comparisons are marked failed). Queues its notifications. Returns True if this
    call finalized it. Safe to call concurrently: only one caller ever finalizes a run."""
    with transaction.atomic():
        run = ComparisonRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None or run.finalized:
            return False
        unfinished = run.comparisons.exclude(status__in=ComparisonStatusChoices.FINAL)
        if unfinished.exists():
            if not deadline_passed:
                return False
            count = unfinished.update(
                status=ComparisonStatusChoices.FAILED,
                error=f"Did not finish within {NOTIFICATION_DEADLINE} minutes of the run's start",
                completed=timezone.now(),
            )
            log.warning("Run %s: %d comparisons did not finish; marked failed", run_id, count)
        run.finalized = timezone.now()
        run.save(update_fields=["finalized"])
        for job in FinalizeRunJob.get_jobs(run).filter(status__in=QUEUED):
            job.delete()
        if run.deliveries.filter(status=DeliveryStatusChoices.PENDING).exists():
            NotifyRunJob.enqueue(instance=run)
    return True


def resend_notifications(run) -> bool:
    """Send a finalized run to its notification modules again. Returns False if the run is
    not finalized yet or has no notification modules."""
    with transaction.atomic():
        run = ComparisonRun.objects.select_for_update().get(pk=run.pk)
        if not run.finalized or not run.deliveries.exists():
            return False
        run.deliveries.update(status=DeliveryStatusChoices.PENDING, detail="", attempted=None)
        NotifyRunJob.enqueue(instance=run)
    return True


def _schedule_jobs(schedule):
    return ScheduledComparisonJob.get_jobs(schedule).filter(status__in=QUEUED)


def cancel_scheduled_jobs(schedule):
    """Remove the schedule's queued jobs."""
    for job in _schedule_jobs(schedule):
        job.delete()


def sync_schedule(schedule_id):
    """Make the queue hold exactly one job for the schedule, at its next run time, or none
    when it is disabled or has no run left. Returns the job (or None), and False when the
    schedule does not exist."""
    with transaction.atomic():
        schedule = ComparisonSchedule.objects.select_for_update().filter(pk=schedule_id).first()
        if schedule is None:
            return False
        when = schedule.next_run(timezone.now()) if schedule.enabled else None
        keep = None
        for job in _schedule_jobs(schedule):
            # Jobs with an interval come from the old minute-based schedules: always replace.
            if keep is None and when and job.scheduled == when and not job.interval:
                keep = job
            else:
                job.delete()
        if when and keep is None:
            keep = ScheduledComparisonJob.enqueue(instance=schedule, schedule_at=when)
        return keep


def next_scheduled_job(schedule):
    return _schedule_jobs(schedule).order_by("scheduled").first()
