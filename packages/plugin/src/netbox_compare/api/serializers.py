from dcim.api.serializers import DeviceSerializer
from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_compare.models import Comparison, Divergence


class DivergenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Divergence
        fields = (
            "id",
            "object_type",
            "object_key",
            "kind",
            "field",
            "severity",
            "documented",
            "observed",
        )


class ComparisonSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_compare-api:comparison-detail"
    )
    device = DeviceSerializer(nested=True, read_only=True)
    divergences = DivergenceSerializer(many=True, read_only=True)

    class Meta:
        model = Comparison
        fields = (
            "id",
            "url",
            "display",
            "device",
            "status",
            "job",
            "requested_by",
            "started",
            "completed",
            "platform",
            "connection_module",
            "error",
            "policy",
            "match_count",
            "divergence_count",
            "not_comparable",
            "divergences",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        read_only_fields = fields
        brief_fields = ("id", "url", "display", "device", "status", "divergence_count")
