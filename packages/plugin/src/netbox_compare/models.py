from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from netbox.models import NetBoxModel
from netbox.models.features import JobsMixin

from netbox_compare.choices import (
    ComparisonStatusChoices,
    DivergenceKindChoices,
    ObjectTypeChoices,
    SeverityChoices,
)
from netbox_compare_core import FIELDS


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
    # Snapshot of the policy used for this run: {field path: severity}.
    policy = models.JSONField(default=dict, blank=True)
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
