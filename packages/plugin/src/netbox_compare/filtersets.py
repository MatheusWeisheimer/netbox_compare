import django_filters
from dcim.models import Device
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from netbox.filtersets import NetBoxModelFilterSet, PrimaryModelFilterSet

from netbox_compare.choices import ComparisonStatusChoices, RecurrenceChoices
from netbox_compare.models import (
    Comparison,
    ComparisonPolicy,
    ComparisonRun,
    ComparisonSchedule,
)


class ComparisonPolicyFilterSet(PrimaryModelFilterSet):
    class Meta:
        model = ComparisonPolicy
        fields = ("id", "name", "description", "is_default")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))


class ComparisonScheduleFilterSet(PrimaryModelFilterSet):
    recurrence = django_filters.MultipleChoiceFilter(choices=RecurrenceChoices)
    policy_id = django_filters.ModelMultipleChoiceFilter(
        queryset=ComparisonPolicy.objects.all(), label=_("Policy (ID)")
    )

    class Meta:
        model = ComparisonSchedule
        fields = ("id", "name", "description", "enabled")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))


class ComparisonRunFilterSet(NetBoxModelFilterSet):
    schedule_id = django_filters.ModelMultipleChoiceFilter(
        queryset=ComparisonSchedule.objects.all(), label=_("Scheduled job (ID)")
    )
    policy_id = django_filters.ModelMultipleChoiceFilter(
        queryset=ComparisonPolicy.objects.all(), label=_("Policy (ID)")
    )

    class Meta:
        model = ComparisonRun
        fields = ("id", "name")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(name__icontains=value)


class ComparisonFilterSet(NetBoxModelFilterSet):
    device_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Device.objects.all(), label=_("Device (ID)")
    )
    run_id = django_filters.ModelMultipleChoiceFilter(
        queryset=ComparisonRun.objects.all(), label=_("Scheduled job result (ID)")
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
