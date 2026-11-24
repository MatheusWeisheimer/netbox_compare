from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel, PrimaryModel
from netbox.models.features import JobsMixin

from netbox_compare.choices import (
    ComparisonStatusChoices,
    DeliveryStatusChoices,
    DivergenceKindChoices,
    ObjectTypeChoices,
    RecurrenceChoices,
    ResolutionChoices,
    ResolutionStatusChoices,
    SeverityChoices,
)
from netbox_compare.policy import considered, validate_policy_fields
from netbox_compare.schedule import next_run_at
from netbox_compare_core import FIELDS


class ComparisonPolicy(PrimaryModel):
    """Which canonical fields a comparison considers, and the severity of each.

    Divergences on fields the policy does not name are dropped and never reported.
    """

    name = models.CharField(max_length=100, unique=True)
    # {canonical field path: {"enabled": bool, "severity": str}}, one entry per canonical field.
    # See netbox_compare.policy.
    fields = models.JSONField(default=dict)
    is_default = models.BooleanField(
        default=False,
        verbose_name=_("default"),
        help_text=_("Used when a comparison is started without choosing a policy."),
    )

    class Meta:
        ordering = ("name",)
        verbose_name = _("comparison policy")
        verbose_name_plural = _("comparison policies")
        constraints = (
            models.UniqueConstraint(
                fields=("is_default",),
                condition=models.Q(is_default=True),
                name="netbox_compare_single_default_policy",
            ),
        )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_compare:comparisonpolicy", args=[self.pk])

    def clean(self):
        super().clean()
        # Non-field errors: the edit form has inputs per canonical field, not a "fields" one.
        try:
            self.fields = validate_policy_fields(self.fields)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def validate_constraints(self, exclude=None):
        # A new default replaces the old one in save(); the single-default constraint must not
        # reject it first. The database constraint still guards against races.
        if self.is_default:
            exclude = {*(exclude or ()), "is_default"}
        super().validate_constraints(exclude=exclude)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                # Only one default: demote the previous one (through save(), so it is logged).
                for other in ComparisonPolicy.objects.filter(is_default=True).exclude(pk=self.pk):
                    other.snapshot()
                    other.is_default = False
                    other.save()
            super().save(*args, **kwargs)

    @property
    def considered_fields(self) -> dict[str, str]:
        """The enabled fields, as the diff takes them: ``{path: severity}``."""
        return considered(self.fields)


class ComparisonSchedule(JobsMixin, PrimaryModel):
    """Periodic comparison of a set of devices: the devices chosen one by one, plus every
    device carrying one of the chosen tags at run time. Each run produces a
    :class:`ComparisonRun`. Runs detect and report only; they never apply fixes."""

    name = models.CharField(max_length=100, unique=True)
    enabled = models.BooleanField(default=True)
    policy = models.ForeignKey(
        to=ComparisonPolicy, on_delete=models.PROTECT, related_name="schedules"
    )
    devices = models.ManyToManyField(to="dcim.Device", blank=True, related_name="+")
    device_tags = models.ManyToManyField(
        to="extras.Tag",
        blank=True,
        related_name="+",
        verbose_name=_("device tags"),
        help_text=_("Every device with one of these tags when a run starts is included."),
    )
    start_time = models.DateTimeField(verbose_name=_("first run"))
    recurrence = models.CharField(
        max_length=20,
        choices=RecurrenceChoices,
        default=RecurrenceChoices.NONE,
        verbose_name=_("repeats"),
        help_text=_(
            "Later runs keep the first run's time of day: every day, every week on the same "
            "weekday, or every month on the same day (the last day of shorter months)."
        ),
    )
    # Names of configured notification modules (PLUGINS_CONFIG "notifications") that receive
    # each run's result.
    notifications = ArrayField(
        base_field=models.CharField(max_length=100),
        default=list,
        blank=True,
        verbose_name=_("notifications"),
        help_text=_("Notification modules that receive the result of each run."),
    )

    class Meta:
        ordering = ("name",)
        verbose_name = _("scheduled job")
        verbose_name_plural = _("scheduled jobs")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_compare:comparisonschedule", args=[self.pk])

    def target_devices(self):
        """Devices selected now: chosen ones plus those with a chosen tag. Whether they can
        actually be compared is decided when a run starts."""
        from dcim.models import Device

        return Device.objects.filter(
            models.Q(pk__in=self.devices.values("pk"))
            | models.Q(tags__in=self.device_tags.values("pk"))
        ).distinct()

    def clean(self):
        super().clean()
        from netbox_compare.modules import configured_notification_names

        configured = configured_notification_names()
        unknown = sorted(set(self.notifications) - set(configured))
        if unknown:
            raise ValidationError(
                {
                    "notifications": _(
                        "Not configured notification modules: {unknown}. Configured: {configured}."
                    ).format(unknown=", ".join(unknown), configured=", ".join(configured) or "none")
                }
            )
        self.notifications = [n for n in configured if n in self.notifications]
        if self.recurrence != RecurrenceChoices.NONE or self.start_time is None:
            return
        previous = None
        if self.pk:
            previous = (
                type(self).objects.filter(pk=self.pk).values_list("start_time", flat=True).first()
            )
        # A job that does not repeat would never run; one that already ran may stay as it is.
        if self.start_time != previous and self.start_time <= timezone.now():
            raise ValidationError(
                {
                    "start_time": _(
                        "A job that does not repeat must have its first run in the future."
                    )
                }
            )

    def next_run(self, now=None):
        """When the next run is due, in NetBox's time zone; None when no run is left."""
        return next_run_at(
            self.start_time,
            self.recurrence,
            now or timezone.now(),
            timezone.get_current_timezone(),
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from netbox_compare.jobs import sync_schedule

        transaction.on_commit(lambda: sync_schedule(self.pk))

    def delete(self, *args, **kwargs):
        from netbox_compare.jobs import cancel_scheduled_jobs

        with transaction.atomic():
            # Job.delete() also cancels the queued RQ job; the generic relation's cascade
            # would only delete the rows.
            cancel_scheduled_jobs(self)
            return super().delete(*args, **kwargs)


class ComparisonRun(JobsMixin, NetBoxModel):
    """One run of a schedule: a comparison per device, reported together, by device.

    Once every comparison is final (or the notification deadline passes) the run is finalized
    and its result is sent to the notification modules in :attr:`deliveries`."""

    schedule = models.ForeignKey(
        to=ComparisonSchedule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )
    # The schedule's name when it ran; kept after the schedule is renamed or deleted.
    name = models.CharField(max_length=100)
    policy = models.ForeignKey(
        to=ComparisonPolicy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runs",
    )
    # Set when a user started the run by hand; blank for scheduled runs.
    requested_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    job = models.ForeignKey(
        to="core.Job", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Selected devices that were not compared: [{"device": id, "name": str, "reason": str}].
    skipped = models.JSONField(default=list, blank=True)
    # When the run was finalized: every comparison final, or the deadline passed. Set once.
    finalized = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created", "-pk")
        verbose_name = _("scheduled job result")
        verbose_name_plural = _("scheduled jobs results")

    def __str__(self):
        return f"{self.name} #{self.pk}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_compare:comparisonrun", args=[self.pk])

    @property
    def status(self):
        """Derived from the run's comparisons: completed once each one is final."""
        statuses = list(self.comparisons.values_list("status", flat=True))
        return run_status(statuses)

    def get_status_display(self):
        return dict(ComparisonStatusChoices).get(self.status)

    def get_status_color(self):
        return ComparisonStatusChoices.colors.get(self.status)


class NotificationDelivery(models.Model):
    """Delivery of a run's result to one notification module. One row per module linked to
    the schedule when the run started."""

    run = models.ForeignKey(to=ComparisonRun, on_delete=models.CASCADE, related_name="deliveries")
    module = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20, choices=DeliveryStatusChoices, default=DeliveryStatusChoices.PENDING
    )
    detail = models.TextField(blank=True)
    attempted = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("run", "pk")
        constraints = (
            models.UniqueConstraint(
                fields=("run", "module"), name="netbox_compare_unique_delivery_module"
            ),
        )
        verbose_name = _("notification delivery")
        verbose_name_plural = _("notification deliveries")

    def __str__(self):
        return f"{self.run} -> {self.module}"

    def get_status_color(self):
        return DeliveryStatusChoices.colors.get(self.status)


def run_status(statuses) -> str:
    """A run's status from its comparisons' statuses."""
    if all(s in ComparisonStatusChoices.FINAL for s in statuses):
        return ComparisonStatusChoices.COMPLETED
    if all(s == ComparisonStatusChoices.PENDING for s in statuses):
        return ComparisonStatusChoices.PENDING
    return ComparisonStatusChoices.RUNNING


class Comparison(JobsMixin, NetBoxModel):
    """One comparison run of a device: documented (NetBox) vs. observed (device)."""

    device = models.ForeignKey(
        to="dcim.Device", on_delete=models.CASCADE, related_name="compare_comparisons"
    )
    # The scheduled run this comparison is part of; blank when started from the device page.
    run = models.ForeignKey(
        to=ComparisonRun,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="comparisons",
    )
    status = models.CharField(
        max_length=20,
        choices=ComparisonStatusChoices,
        default=ComparisonStatusChoices.PENDING,
    )
    job = models.ForeignKey(
        to="core.Job", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    requested_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    started = models.DateTimeField(null=True, blank=True)
    completed = models.DateTimeField(null=True, blank=True)
    platform = models.CharField(max_length=100, blank=True)
    connection_module = models.CharField(max_length=100, blank=True)
    error = models.TextField(blank=True)
    policy = models.ForeignKey(
        to=ComparisonPolicy,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comparisons",
    )
    # The policy's fields as they were when this comparison ran: {field path: severity}.
    # Kept so the report stays accurate after the policy is edited or deleted.
    policy_fields = models.JSONField(default=dict, blank=True)
    # [{"field": path, "reason": ..., "keys": [...]}]; empty keys: device or whole collection.
    not_comparable = models.JSONField(default=list, blank=True)
    match_count = models.PositiveIntegerField(default=0)
    divergence_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-created", "-pk")
        verbose_name = _("device comparison result")
        verbose_name_plural = _("device comparison results")

    def __str__(self):
        return f"{self.device} #{self.pk}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_compare:comparison", args=[self.pk])

    def get_status_color(self):
        return ComparisonStatusChoices.colors.get(self.status)

    @property
    def is_final(self):
        return self.status in ComparisonStatusChoices.FINAL

    @property
    def duration(self):
        if self.started and self.completed:
            return self.completed - self.started
        return None


class Divergence(models.Model):
    """One divergence found by a comparison."""

    comparison = models.ForeignKey(
        to=Comparison, on_delete=models.CASCADE, related_name="divergences"
    )
    object_type = models.CharField(max_length=20, choices=ObjectTypeChoices)
    object_key = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=20, choices=DivergenceKindChoices)
    field = models.CharField(max_length=100)
    severity = models.CharField(max_length=20, choices=SeverityChoices)
    documented = models.JSONField(null=True, blank=True)
    observed = models.JSONField(null=True, blank=True)
    # The administrator's last decision on this divergence and its outcome. Blank: undecided.
    resolution = models.CharField(max_length=20, choices=ResolutionChoices, blank=True)
    resolution_status = models.CharField(max_length=20, choices=ResolutionStatusChoices, blank=True)
    resolution_detail = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("comparison", "pk")
        verbose_name = _("divergence")
        verbose_name_plural = _("divergences")

    def __str__(self):
        target = self.object_key or self.object_type
        return f"{target}: {self.field_label}"

    @property
    def field_spec(self):
        return FIELDS.get(self.field)

    @property
    def field_label(self):
        spec = self.field_spec
        return spec.label if spec else self.field

    @property
    def field_kind(self):
        spec = self.field_spec
        return spec.kind if spec else None

    def get_severity_color(self):
        return SeverityChoices.colors.get(self.severity)

    def get_kind_color(self):
        return DivergenceKindChoices.colors.get(self.kind)

    def get_resolution_color(self):
        return ResolutionChoices.colors.get(self.resolution)

    def get_resolution_status_color(self):
        return ResolutionStatusChoices.colors.get(self.resolution_status)

    @property
    def is_settled(self):
        """Already fixed; it can no longer be resolved."""
        return self.resolution_status in ResolutionStatusChoices.FINAL


def with_run_counts(queryset):
    """Annotate :class:`ComparisonRun` rows with per-device totals, for lists."""
    final = ComparisonStatusChoices.FINAL
    return queryset.annotate(
        device_count=models.Count("comparisons"),
        failed_count=models.Count(
            "comparisons", filter=models.Q(comparisons__status=ComparisonStatusChoices.FAILED)
        ),
        unfinished_count=models.Count(
            "comparisons", filter=~models.Q(comparisons__status__in=final)
        ),
        divergence_total=Coalesce(models.Sum("comparisons__divergence_count"), 0),
    )
