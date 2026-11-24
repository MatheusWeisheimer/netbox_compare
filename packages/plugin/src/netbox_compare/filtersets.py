import django_filters
from dcim.models import Device
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from netbox.filtersets import NetBoxModelFilterSet

from netbox_compare.choices import ComparisonStatusChoices
from netbox_compare.models import Comparison


class ComparisonFilterSet(NetBoxModelFilterSet):
    device_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Device.objects.all(), label=_("Device (ID)")
    )
    status = django_filters.MultipleChoiceFilter(choices=ComparisonStatusChoices)

    class Meta:
        model = Comparison
        fields = ("id", "status", "platform", "connection_module")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(device__name__icontains=value) | Q(error__icontains=value))
