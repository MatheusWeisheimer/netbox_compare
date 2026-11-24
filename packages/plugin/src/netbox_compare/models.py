from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel, PrimaryModel
from netbox.models.features import JobsMixin

from netbox_compare.choices import (
    ComparisonStatusChoices,
    DivergenceKindChoices,
    ObjectTypeChoices,
    ResolutionChoices,
    ResolutionStatusChoices,
    SeverityChoices,
)
from netbox_compare.policy import considered, validate_policy_fields
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


class Comparison(JobsMixin, NetBoxModel):
    """One comparison run of a device: documented (NetBox) vs. observed (device)."""

    device = models.ForeignKey(
        to="dcim.Device", on_delete=models.CASCADE, related_name="compare_comparisons"
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
        verbose_name = _("comparison")
        verbose_name_plural = _("comparisons")

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
