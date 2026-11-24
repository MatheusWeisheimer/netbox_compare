from django.db.models import Count
from netbox.api.viewsets import NetBoxModelViewSet, NetBoxReadOnlyModelViewSet

from netbox_compare.api.serializers import ComparisonPolicySerializer, ComparisonSerializer
from netbox_compare.filtersets import ComparisonFilterSet, ComparisonPolicyFilterSet
from netbox_compare.models import Comparison, ComparisonPolicy


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
