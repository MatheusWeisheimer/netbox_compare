from django.db.models import Count
from netbox.api.viewsets import NetBoxModelViewSet, NetBoxReadOnlyModelViewSet

from netbox_compare.api.serializers import (
    ComparisonPolicySerializer,
    ComparisonRunSerializer,
    ComparisonScheduleSerializer,
    ComparisonSerializer,
)
from netbox_compare.filtersets import (
    ComparisonFilterSet,
    ComparisonPolicyFilterSet,
    ComparisonRunFilterSet,
    ComparisonScheduleFilterSet,
)
from netbox_compare.models import Comparison, ComparisonPolicy, ComparisonRun, ComparisonSchedule


class ComparisonPolicyViewSet(NetBoxModelViewSet):
    queryset = ComparisonPolicy.objects.annotate(comparison_count=Count("comparisons"))
    serializer_class = ComparisonPolicySerializer
    filterset_class = ComparisonPolicyFilterSet


class ComparisonViewSet(NetBoxReadOnlyModelViewSet):
    queryset = Comparison.objects.select_related("device", "policy").prefetch_related(
        "divergences", "tags"
    )
    serializer_class = ComparisonSerializer
    filterset_class = ComparisonFilterSet


class ComparisonScheduleViewSet(NetBoxModelViewSet):
    queryset = (
        ComparisonSchedule.objects.select_related("policy")
        .prefetch_related("devices", "device_tags", "tags")
        .annotate(run_count=Count("runs"))
    )
    serializer_class = ComparisonScheduleSerializer
    filterset_class = ComparisonScheduleFilterSet


class ComparisonRunViewSet(NetBoxReadOnlyModelViewSet):
    queryset = ComparisonRun.objects.select_related("schedule", "policy").prefetch_related(
        "comparisons__device",
        "comparisons__policy",
        "comparisons__divergences",
        "deliveries",
        "tags",
    )
    serializer_class = ComparisonRunSerializer
    filterset_class = ComparisonRunFilterSet
