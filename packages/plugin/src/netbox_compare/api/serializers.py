from dcim.api.serializers import DeviceSerializer
from dcim.models import Device
from extras.api.serializers import TagSerializer
from extras.models import Tag
from netbox.api.fields import SerializedPKRelatedField
from netbox.api.serializers import NetBoxModelSerializer, PrimaryModelSerializer
from rest_framework import serializers

from netbox_compare.models import (
    Comparison,
    ComparisonPolicy,
    ComparisonRun,
    ComparisonSchedule,
    Divergence,
)
from netbox_compare.policy import validate_policy_fields


class ComparisonPolicySerializer(PrimaryModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_compare-api:comparisonpolicy-detail"
    )
    fields = serializers.JSONField(
        help_text='{canonical field path: {"enabled": bool, "severity": str}}; fields left out '
        "are disabled with their default severity."
    )
    comparison_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ComparisonPolicy
        fields = (
            "id",
            "url",
            "display",
            "name",
            "description",
            "fields",
            "is_default",
            "comparison_count",
            "owner",
            "comments",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "description", "is_default")

    def validate_fields(self, value):
        try:
            return validate_policy_fields(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


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
            "resolution",
            "resolution_status",
            "resolution_detail",
            "resolved_by",
            "resolved_at",
        )
        read_only_fields = fields


class ComparisonSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_compare-api:comparison-detail"
    )
    device = DeviceSerializer(nested=True, read_only=True)
    policy = ComparisonPolicySerializer(nested=True, read_only=True)
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
            "run",
            "policy_fields",
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
        brief_fields = (
            "id",
            "url",
            "display",
            "device",
            "policy",
            "status",
            "divergence_count",
        )


class ComparisonScheduleSerializer(PrimaryModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_compare-api:comparisonschedule-detail"
    )
    policy = ComparisonPolicySerializer(nested=True)
    devices = SerializedPKRelatedField(
        queryset=Device.objects.all(),
        serializer=DeviceSerializer,
        nested=True,
        required=False,
        many=True,
    )
    device_tags = SerializedPKRelatedField(
        queryset=Tag.objects.all(),
        serializer=TagSerializer,
        nested=True,
        required=False,
        many=True,
    )
    run_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ComparisonSchedule
        fields = (
            "id",
            "url",
            "display",
            "name",
            "description",
            "enabled",
            "policy",
            "devices",
            "device_tags",
            "start_time",
            "recurrence",
            "run_count",
            "owner",
            "comments",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "description", "enabled")

    def validate(self, data):
        data = super().validate(data)
        instance = self.instance

        def current(name):
            if name in data:
                return data[name]
            return list(getattr(instance, name).all()) if instance else []

        if not current("devices") and not current("device_tags"):
            raise serializers.ValidationError("Select at least one device or device tag.")
        return data


class ComparisonRunSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_compare-api:comparisonrun-detail"
    )
    schedule = ComparisonScheduleSerializer(nested=True, read_only=True)
    policy = ComparisonPolicySerializer(nested=True, read_only=True)
    status = serializers.CharField(read_only=True)
    comparisons = ComparisonSerializer(many=True, read_only=True)

    class Meta:
        model = ComparisonRun
        fields = (
            "id",
            "url",
            "display",
            "name",
            "schedule",
            "policy",
            "status",
            "requested_by",
            "job",
            "skipped",
            "comparisons",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        read_only_fields = fields
        brief_fields = ("id", "url", "display", "name", "status")
