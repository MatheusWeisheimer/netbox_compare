import django_tables2 as tables
from django.utils.translation import gettext_lazy as _
from netbox.tables import NetBoxTable, PrimaryModelTable, columns

from netbox_compare.models import Comparison, ComparisonPolicy
from netbox_compare.policy import considered


class ComparisonPolicyTable(PrimaryModelTable):
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    is_default = columns.BooleanColumn(verbose_name=_("Default"))
    field_count = tables.Column(
        accessor="fields", orderable=False, verbose_name=_("Fields compared")
    )
    comparison_count = columns.LinkedCountColumn(
        viewname="plugins:netbox_compare:comparison_list",
        url_params={"policy_id": "pk"},
        verbose_name=_("Comparisons"),
    )
    tags = columns.TagColumn(url_name="plugins:netbox_compare:comparisonpolicy_list")

    class Meta(PrimaryModelTable.Meta):
        model = ComparisonPolicy
        fields = (
            "pk",
            "id",
            "name",
            "description",
            "is_default",
            "field_count",
            "comparison_count",
            "owner",
            "comments",
            "tags",
            "created",
            "last_updated",
        )
        default_columns = (
            "pk",
            "name",
            "is_default",
            "field_count",
            "comparison_count",
            "description",
        )

    def render_field_count(self, value):
        return len(considered(value or {}))


class ComparisonTable(NetBoxTable):
    id = tables.Column(linkify=True, verbose_name=_("ID"))
    device = tables.Column(linkify=True, verbose_name=_("Device"))
    policy = tables.Column(linkify=True, verbose_name=_("Policy"))
    status = columns.ChoiceFieldColumn(verbose_name=_("Status"))
    divergence_count = tables.Column(verbose_name=_("Divergences"))
    match_count = tables.Column(verbose_name=_("Matches"))
    connection_module = tables.Column(verbose_name=_("Connection module"))
    requested_by = tables.Column(verbose_name=_("Requested by"))
    started = columns.DateTimeColumn(verbose_name=_("Started"))
    completed = columns.DateTimeColumn(verbose_name=_("Completed"))
    actions = columns.ActionsColumn(actions=("delete",))

    class Meta(NetBoxTable.Meta):
        model = Comparison
        fields = (
            "pk",
            "id",
            "device",
            "policy",
            "status",
            "divergence_count",
            "match_count",
            "platform",
            "connection_module",
            "requested_by",
            "created",
            "started",
            "completed",
            "error",
        )
        default_columns = (
            "pk",
            "id",
            "device",
            "policy",
            "status",
            "divergence_count",
            "requested_by",
            "created",
        )
