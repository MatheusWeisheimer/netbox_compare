import django_tables2 as tables
from django.utils.translation import gettext_lazy as _
from netbox.tables import NetBoxTable, columns

from netbox_compare.models import Comparison


class ComparisonTable(NetBoxTable):
    id = tables.Column(linkify=True, verbose_name=_("ID"))
    device = tables.Column(linkify=True, verbose_name=_("Device"))
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
            "status",
            "divergence_count",
            "requested_by",
            "created",
        )
