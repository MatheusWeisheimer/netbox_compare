import django_tables2 as tables
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from netbox.tables import NetBoxTable, PrimaryModelTable, columns

from netbox_compare.choices import ComparisonStatusChoices
from netbox_compare.models import Comparison, ComparisonPolicy, ComparisonRun, ComparisonSchedule
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


class DeviceTagColumn(columns.TagColumn):
    """Tags that select devices; each links to the devices carrying it."""

    def __init__(self, url_name=None):
        super().__init__(url_name=url_name)
        self.verbose_name = _("Device tags")


class ComparisonScheduleTable(PrimaryModelTable):
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    enabled = columns.BooleanColumn(verbose_name=_("Enabled"))
    policy = tables.Column(linkify=True, verbose_name=_("Policy"))
    devices = columns.ManyToManyColumn(linkify_item=True, verbose_name=_("Devices"))
    device_tags = DeviceTagColumn(url_name="dcim:device_list")
    start_time = columns.DateTimeColumn(verbose_name=_("First run"))
    recurrence = columns.ChoiceFieldColumn(verbose_name=_("Repeats"))
    run_count = columns.LinkedCountColumn(
        viewname="plugins:netbox_compare:comparisonrun_list",
        url_params={"schedule_id": "pk"},
        verbose_name=_("Results"),
    )
    tags = columns.TagColumn(url_name="plugins:netbox_compare:comparisonschedule_list")

    class Meta(PrimaryModelTable.Meta):
        model = ComparisonSchedule
        fields = (
            "pk",
            "id",
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
            "created",
            "last_updated",
        )
        default_columns = (
            "pk",
            "name",
            "enabled",
            "policy",
            "device_tags",
            "start_time",
            "recurrence",
            "run_count",
            "description",
        )


class ComparisonRunTable(NetBoxTable):
    id = tables.Column(linkify=True, verbose_name=_("ID"))
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    schedule = tables.Column(linkify=True, verbose_name=_("Scheduled job"))
    policy = tables.Column(linkify=True, verbose_name=_("Policy"))
    status = tables.Column(empty_values=(), orderable=False, verbose_name=_("Status"))
    device_count = tables.Column(verbose_name=_("Devices compared"))
    failed_count = tables.Column(verbose_name=_("Failed"))
    skipped_count = tables.Column(accessor="skipped", orderable=False, verbose_name=_("Skipped"))
    divergence_total = tables.Column(verbose_name=_("Divergences"))
    requested_by = tables.Column(verbose_name=_("Requested by"))
    actions = columns.ActionsColumn(actions=("delete",))

    class Meta(NetBoxTable.Meta):
        model = ComparisonRun
        fields = (
            "pk",
            "id",
            "name",
            "schedule",
            "policy",
            "status",
            "device_count",
            "failed_count",
            "skipped_count",
            "divergence_total",
            "requested_by",
            "created",
        )
        default_columns = (
            "pk",
            "id",
            "name",
            "status",
            "device_count",
            "failed_count",
            "skipped_count",
            "divergence_total",
            "created",
        )

    def render_status(self, record):
        if record.unfinished_count == 0:
            status = ComparisonStatusChoices.COMPLETED
        elif record.unfinished_count == record.device_count:
            status = record.status  # pending or running; needs the comparisons themselves
        else:
            status = ComparisonStatusChoices.RUNNING
        label = dict(ComparisonStatusChoices)[status]
        color = ComparisonStatusChoices.colors[status]
        return format_html('<span class="badge text-bg-{}">{}</span>', color, label)

    def render_skipped_count(self, value):
        return len(value or ())


class ComparisonTable(NetBoxTable):
    id = tables.Column(linkify=True, verbose_name=_("ID"))
    device = tables.Column(linkify=True, verbose_name=_("Device"))
    run = tables.Column(linkify=True, verbose_name=_("Scheduled job result"))
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
            "run",
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
