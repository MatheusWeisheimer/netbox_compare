import django_filters
from dcim.models import Device
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from netbox.filtersets import NetBoxModelFilterSet, PrimaryModelFilterSet

from netbox_compare.choices import ComparisonStatusChoices
from netbox_compare.models import Comparison, ComparisonPolicy


class ComparisonPolicyFilterSet(PrimaryModelFilterSet):
    class Meta:
        model = ComparisonPolicy
        fields = ("id", "name", "description", "is_default")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))


class ComparisonFilterSet(NetBoxModelFilterSet):
    device_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Device.objects.all(), label=_("Device (ID)")
    )
    policy_id = django_filters.ModelMultipleChoiceFilter(
        queryset=ComparisonPolicy.objects.all(), label=_("Policy (ID)")
    )
    status = django_filters.MultipleChoiceFilter(choices=ComparisonStatusChoices)

    class Meta:
        model = Comparison
        fields = ("id", "status", "platform", "connection_module")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(device__name__icontains=value) | Q(error__icontains=value))
