from dcim.models import Device
from django import forms
from django.utils.translation import gettext_lazy as _
from netbox.forms import NetBoxModelFilterSetForm
from utilities.forms.fields import DynamicModelMultipleChoiceField, TagFilterField
from utilities.forms.rendering import FieldSet

from netbox_compare.choices import ComparisonStatusChoices
from netbox_compare.models import Comparison


class ComparisonFilterForm(NetBoxModelFilterSetForm):
    model = Comparison
    fieldsets = (FieldSet("q", "filter_id", "tag"), FieldSet("device_id", "status"))
    device_id = DynamicModelMultipleChoiceField(
        queryset=Device.objects.all(), required=False, label=_("Device")
    )
    status = forms.MultipleChoiceField(
        choices=ComparisonStatusChoices, required=False, label=_("Status")
    )
    tag = TagFilterField(model)
