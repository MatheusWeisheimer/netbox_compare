from netbox.api.viewsets import NetBoxReadOnlyModelViewSet

from netbox_compare.api.serializers import ComparisonSerializer
from netbox_compare.filtersets import ComparisonFilterSet
from netbox_compare.models import Comparison


class ComparisonViewSet(NetBoxReadOnlyModelViewSet):
    queryset = Comparison.objects.select_related("device").prefetch_related("divergences", "tags")
    serializer_class = ComparisonSerializer
    filterset_class = ComparisonFilterSet
