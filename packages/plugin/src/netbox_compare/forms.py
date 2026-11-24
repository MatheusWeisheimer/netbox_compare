from dcim.models import Device
from django import forms
from django.utils.translation import gettext_lazy as _
from netbox.forms import NetBoxModelFilterSetForm, PrimaryModelFilterSetForm, PrimaryModelForm
from utilities.forms import BOOLEAN_WITH_BLANK_CHOICES
from utilities.forms.fields import (
    CommentField,
    DynamicModelMultipleChoiceField,
    TagFilterField,
)
from utilities.forms.rendering import FieldSet, InlineFields

from netbox_compare.choices import ComparisonStatusChoices, ObjectTypeChoices, SeverityChoices
from netbox_compare.models import Comparison, ComparisonPolicy
from netbox_compare.policy import DEFAULT_POLICY, validate_policy_fields
from netbox_compare_core import FIELDS, FieldKind


def _suffix(path: str) -> str:
    return path.replace(".", "__")


def enabled_field_name(path: str) -> str:
    """Form field enabling the comparison of canonical field ``path`` (``interface.mtu``)."""
    return "enabled__" + _suffix(path)


def severity_field_name(path: str) -> str:
    """Form field holding the severity of divergences on canonical field ``path``."""
    return "severity__" + _suffix(path)


def policy_field_label(spec) -> str:
    if spec.key:
        return _("Presence")
    return spec.label


def policy_field_help(spec) -> str:
    if spec.key:
        return _("Compare: report objects found on only one side")
    if spec.kind == FieldKind.CONFIG:
        return _("Compare (configuration attribute)")
    return _("Compare (read-only fact)")


class ComparisonPolicyForm(PrimaryModelForm):
    """Per canonical field: a checkbox to compare it, and the severity of its divergences."""

    comments = CommentField()

    class Meta:
        model = ComparisonPolicy
        fields = ("name", "description", "is_default", "owner", "tags", "comments")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            try:
                current = validate_policy_fields(self.instance.fields)
            except ValueError:
                current = {}
        else:
            current = {p: {"enabled": True, "severity": s} for p, s in DEFAULT_POLICY.items()}
        groups = []
        for object_type, label in ObjectTypeChoices:
            rows = []
            for path, spec in FIELDS.items():
                if spec.object_type != object_type:
                    continue
                entry = current.get(path) or {}
                self.fields[enabled_field_name(path)] = forms.BooleanField(
                    required=False,
                    label=policy_field_help(spec),
                    initial=entry.get("enabled", False),
                )
                self.fields[severity_field_name(path)] = forms.ChoiceField(
                    choices=SeverityChoices,
                    label=_("Severity of divergences"),
                    initial=entry.get("severity") or DEFAULT_POLICY.get(path, "medium"),
                )
                rows.append(
                    InlineFields(
                        enabled_field_name(path),
                        severity_field_name(path),
                        label=policy_field_label(spec),
                    )
                )
            groups.append(FieldSet(*rows, name=label))
        self.fieldsets = (
            FieldSet("name", "description", "is_default", "tags", name=_("Policy")),
            *groups,
        )

    def clean(self):
        super().clean()
        cleaned = self.cleaned_data
        self.instance.fields = {
            path: {
                "enabled": bool(cleaned.get(enabled_field_name(path))),
                # A missing severity is reported on its own field; keep the default meanwhile.
                "severity": cleaned.get(severity_field_name(path))
                or DEFAULT_POLICY.get(path, "medium"),
            }
            for path in FIELDS
        }
        return cleaned


class ComparisonPolicyFilterForm(PrimaryModelFilterSetForm):
    model = ComparisonPolicy
    fieldsets = (
        FieldSet("q", "filter_id", "tag"),
        FieldSet("is_default"),
        FieldSet("owner_group_id", "owner_id", name=_("Ownership")),
    )
    is_default = forms.NullBooleanField(
        required=False,
        label=_("Default"),
        widget=forms.Select(choices=BOOLEAN_WITH_BLANK_CHOICES),
    )
    tag = TagFilterField(model)


class ComparisonFilterForm(NetBoxModelFilterSetForm):
    model = Comparison
    fieldsets = (FieldSet("q", "filter_id", "tag"), FieldSet("device_id", "policy_id", "status"))
    device_id = DynamicModelMultipleChoiceField(
        queryset=Device.objects.all(), required=False, label=_("Device")
    )
    policy_id = DynamicModelMultipleChoiceField(
        queryset=ComparisonPolicy.objects.all(), required=False, label=_("Policy")
    )
    status = forms.MultipleChoiceField(
        choices=ComparisonStatusChoices, required=False, label=_("Status")
    )
    tag = TagFilterField(model)
