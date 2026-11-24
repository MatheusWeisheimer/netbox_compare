from collections import Counter

from dcim.models import Device
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from django.views import View
from netbox.object_actions import (
    AddObject,
    BulkDelete,
    BulkExport,
    CloneObject,
    DeleteObject,
    EditObject,
)
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from netbox_compare import filtersets, forms, tables
from netbox_compare.choices import (
    ComparisonStatusChoices,
    DeliveryStatusChoices,
    ObjectTypeChoices,
    ResolutionStatusChoices,
    SeverityChoices,
    SkipReasonChoices,
)
from netbox_compare.models import (
    Comparison,
    ComparisonPolicy,
    ComparisonRun,
    ComparisonSchedule,
    run_status,
    with_run_counts,
)
from netbox_compare.modules import connection_for_platform
from netbox_compare.policy import default_policy
from netbox_compare_core import FIELDS

REASON_LABELS = {
    "not_readable": _("The connection module cannot read this field on this platform"),
    "not_observed": _("The device did not return a value in this run"),
    "not_in_schema": _("This NetBox version has no field to document it"),
}


#
# Comparison policies
#


@register_model_view(ComparisonPolicy, "list", path="", detail=False)
class ComparisonPolicyListView(generic.ObjectListView):
    queryset = ComparisonPolicy.objects.annotate(comparison_count=Count("comparisons"))
    table = tables.ComparisonPolicyTable
    filterset = filtersets.ComparisonPolicyFilterSet
    filterset_form = forms.ComparisonPolicyFilterForm
    actions = (AddObject, BulkExport, BulkDelete)


@register_model_view(ComparisonPolicy)
class ComparisonPolicyView(generic.ObjectView):
    queryset = ComparisonPolicy.objects.all()
    actions = (CloneObject, EditObject, DeleteObject)

    def get_extra_context(self, request, instance):
        groups = []
        for object_type, label in ObjectTypeChoices:
            rows = []
            for path, spec in FIELDS.items():
                if spec.object_type != object_type:
                    continue
                entry = instance.fields.get(path) or {}
                severity = entry.get("severity")
                rows.append(
                    {
                        "path": path,
                        "label": forms.policy_field_label(spec),
                        "kind": spec.kind,
                        "key": spec.key,
                        "enabled": bool(entry.get("enabled")),
                        "severity_label": dict(SeverityChoices).get(severity, severity),
                        "color": SeverityChoices.colors.get(severity),
                    }
                )
            groups.append({"label": label, "rows": rows})
        return {
            "field_groups": groups,
            "comparison_count": instance.comparisons.count(),
        }


@register_model_view(ComparisonPolicy, "add", detail=False)
@register_model_view(ComparisonPolicy, "edit")
class ComparisonPolicyEditView(generic.ObjectEditView):
    queryset = ComparisonPolicy.objects.all()
    form = forms.ComparisonPolicyForm


@register_model_view(ComparisonPolicy, "delete")
class ComparisonPolicyDeleteView(generic.ObjectDeleteView):
    queryset = ComparisonPolicy.objects.all()


@register_model_view(ComparisonPolicy, "bulk_delete", path="delete", detail=False)
class ComparisonPolicyBulkDeleteView(generic.BulkDeleteView):
    queryset = ComparisonPolicy.objects.annotate(comparison_count=Count("comparisons"))
    filterset = filtersets.ComparisonPolicyFilterSet
    table = tables.ComparisonPolicyTable


#
# Comparison schedules
#


@register_model_view(ComparisonSchedule, "list", path="", detail=False)
class ComparisonScheduleListView(generic.ObjectListView):
    queryset = ComparisonSchedule.objects.select_related("policy").annotate(run_count=Count("runs"))
    table = tables.ComparisonScheduleTable
    filterset = filtersets.ComparisonScheduleFilterSet
    filterset_form = forms.ComparisonScheduleFilterForm
    actions = (AddObject, BulkExport, BulkDelete)


@register_model_view(ComparisonSchedule)
class ComparisonScheduleView(generic.ObjectView):
    queryset = ComparisonSchedule.objects.select_related("policy")
    actions = (CloneObject, EditObject, DeleteObject)

    def get_extra_context(self, request, instance):
        from netbox_compare.jobs import next_scheduled_job

        runs = with_run_counts(
            ComparisonRun.objects.restrict(request.user, "view").filter(schedule=instance)
        )
        job = next_scheduled_job(instance) if instance.enabled else None
        return {
            "next_job": job,
            "next_run": instance.next_run() if instance.enabled else None,
            "target_count": instance.target_devices().count(),
            "devices": instance.devices.order_by("name"),
            "device_tags": instance.device_tags.all(),
            "recent_runs": runs[:10],
            "run_count": runs.count(),
            "can_run": request.user.has_perm("netbox_compare.add_comparison"),
        }


@register_model_view(ComparisonSchedule, "add", detail=False)
@register_model_view(ComparisonSchedule, "edit")
class ComparisonScheduleEditView(generic.ObjectEditView):
    queryset = ComparisonSchedule.objects.all()
    form = forms.ComparisonScheduleForm


@register_model_view(ComparisonSchedule, "delete")
class ComparisonScheduleDeleteView(generic.ObjectDeleteView):
    queryset = ComparisonSchedule.objects.all()


@register_model_view(ComparisonSchedule, "bulk_delete", path="delete", detail=False)
class ComparisonScheduleBulkDeleteView(generic.BulkDeleteView):
    queryset = ComparisonSchedule.objects.annotate(run_count=Count("runs"))
    filterset = filtersets.ComparisonScheduleFilterSet
    table = tables.ComparisonScheduleTable


class ComparisonScheduleRunView(LoginRequiredMixin, View):
    """Start a run of a schedule now, outside its timing (POST only)."""

    def post(self, request, pk):
        if not request.user.has_perm("netbox_compare.add_comparison"):
            raise PermissionDenied
        schedule = get_object_or_404(
            ComparisonSchedule.objects.restrict(request.user, "view").select_related("policy"),
            pk=pk,
        )
        from netbox_compare.jobs import start_run

        run = start_run(schedule, user=request.user)
        messages.info(
            request,
            _("{schedule} started: {queued} devices queued, {skipped} skipped.").format(
                schedule=schedule, queued=run.comparisons.count(), skipped=len(run.skipped)
            ),
        )
        return redirect(run.get_absolute_url())


#
# Comparison runs
#


@register_model_view(ComparisonRun, "list", path="", detail=False)
class ComparisonRunListView(generic.ObjectListView):
    queryset = with_run_counts(
        ComparisonRun.objects.select_related("schedule", "policy", "requested_by")
    )
    table = tables.ComparisonRunTable
    filterset = filtersets.ComparisonRunFilterSet
    filterset_form = forms.ComparisonRunFilterForm
    actions = (BulkExport, BulkDelete)


@register_model_view(ComparisonRun)
class ComparisonRunView(generic.ObjectView):
    """The run's report: one section per device, with the divergences found on it."""

    queryset = ComparisonRun.objects.select_related("schedule", "policy", "requested_by", "job")
    actions = (DeleteObject,)

    def get_extra_context(self, request, instance):
        comparisons = list(
            instance.comparisons.select_related("device")
            .prefetch_related("divergences")
            .order_by("device__name", "pk")
        )
        severities = Counter()
        statuses = Counter()
        order = {path: i for i, path in enumerate(FIELDS)}
        object_order = {value: i for i, (value, _label) in enumerate(ObjectTypeChoices)}
        for c in comparisons:
            statuses[c.status] += 1
            c.sorted_divergences = sorted(
                c.divergences.all(),
                key=lambda d: (
                    object_order.get(d.object_type, 99),
                    d.object_key,
                    order.get(d.field, 99),
                ),
            )
            severities.update(d.severity for d in c.sorted_divergences)

        devices = {
            d.pk: d for d in Device.objects.filter(pk__in=[s["device"] for s in instance.skipped])
        }
        reasons = dict(SkipReasonChoices)
        skipped = [
            {
                **s,
                "object": devices.get(s["device"]),
                "reason_label": reasons.get(s["reason"], s["reason"]),
            }
            for s in instance.skipped
        ]
        status = run_status([c.status for c in comparisons])
        finished = [c.completed for c in comparisons if c.completed]
        done = status == ComparisonStatusChoices.COMPLETED
        deliveries = list(instance.deliveries.all())
        return {
            "comparisons": comparisons,
            "deliveries": deliveries,
            "notifying": any(d.status == DeliveryStatusChoices.PENDING for d in deliveries),
            "can_resend": instance.finalized
            and deliveries
            and request.user.has_perm("netbox_compare.change_comparisonrun"),
            "skipped": skipped,
            "status": status,
            "status_label": dict(ComparisonStatusChoices)[status],
            "status_color": ComparisonStatusChoices.colors[status],
            "completed": max(finished) if done and finished else None,
            "divergent_count": sum(1 for c in comparisons if c.divergence_count),
            "clean_count": sum(
                1
                for c in comparisons
                if c.status == ComparisonStatusChoices.COMPLETED and not c.divergence_count
            ),
            "failed_count": statuses[ComparisonStatusChoices.FAILED],
            "unfinished_count": sum(1 for c in comparisons if not c.is_final),
            "divergence_total": sum(c.divergence_count for c in comparisons),
            "severity_counts": [
                (label, severities[value], SeverityChoices.colors.get(value))
                for value, label in reversed(list(SeverityChoices))
                if severities[value]
            ],
        }


class ComparisonRunNotifyView(LoginRequiredMixin, View):
    """Send a finalized run to its notification modules again (POST only). Only reports;
    never applies fixes."""

    def post(self, request, pk):
        if not request.user.has_perm("netbox_compare.change_comparisonrun"):
            raise PermissionDenied
        run = get_object_or_404(ComparisonRun.objects.restrict(request.user, "view"), pk=pk)
        from netbox_compare.jobs import resend_notifications

        if resend_notifications(run):
            messages.info(request, _("Notifications queued."))
        else:
            messages.warning(
                request, _("The run has not finished yet, or has no notification modules.")
            )
        return redirect(run.get_absolute_url())


@register_model_view(ComparisonRun, "delete")
class ComparisonRunDeleteView(generic.ObjectDeleteView):
    queryset = ComparisonRun.objects.all()


@register_model_view(ComparisonRun, "bulk_delete", path="delete", detail=False)
class ComparisonRunBulkDeleteView(generic.BulkDeleteView):
    queryset = with_run_counts(ComparisonRun.objects.all())
    filterset = filtersets.ComparisonRunFilterSet
    table = tables.ComparisonRunTable


#
# Comparisons
#


@register_model_view(Comparison, "list", path="", detail=False)
class ComparisonListView(generic.ObjectListView):
    queryset = Comparison.objects.select_related("device", "policy", "requested_by", "run")
    table = tables.ComparisonTable
    filterset = filtersets.ComparisonFilterSet
    filterset_form = forms.ComparisonFilterForm
    actions = (BulkExport, BulkDelete)


@register_model_view(Comparison)
class ComparisonView(generic.ObjectView):
    queryset = Comparison.objects.select_related("device", "policy", "requested_by", "job", "run")
    actions = (DeleteObject,)

    def get_extra_context(self, request, instance):
        divergences = list(instance.divergences.all())
        groups = []
        for object_type, label in ObjectTypeChoices:
            items = [d for d in divergences if d.object_type == object_type]
            if items:
                groups.append(
                    {
                        "object_type": object_type,
                        "label": label,
                        "items": items,
                        "open": any(not d.is_settled for d in items),
                    }
                )
        severities = Counter(d.severity for d in divergences)
        not_comparable = [
            {
                **nc,
                "label": FIELDS[nc["field"]].label if nc["field"] in FIELDS else nc["field"],
                "object_type": nc["field"].split(".", 1)[0],
                "reason_label": REASON_LABELS.get(nc["reason"], nc["reason"]),
            }
            for nc in instance.not_comparable
        ]
        order = {path: i for i, path in enumerate(FIELDS)}
        policy = [
            {"field": path, "severity": severity}
            for path, severity in sorted(
                instance.policy_fields.items(), key=lambda kv: order.get(kv[0], len(order))
            )
        ]
        return {
            "divergence_groups": groups,
            "severity_counts": [
                (label, severities[value], SeverityChoices.colors.get(value))
                for value, label in reversed(list(SeverityChoices))
                if severities[value]
            ],
            "not_comparable": not_comparable,
            "policy_fields": policy,
            "can_resolve": _can_resolve(request.user, instance)
            and any(not d.is_settled for d in divergences),
        }


def _can_resolve(user, comparison) -> bool:
    return (
        comparison.status == ComparisonStatusChoices.COMPLETED
        and Comparison.objects.restrict(user, "change").filter(pk=comparison.pk).exists()
    )


_SECTIONS = (
    (
        ResolutionStatusChoices.APPLIED,
        _("Fixed in the documentation"),
        _("NetBox now holds the value observed on the device. The change log has the details."),
    ),
    (
        ResolutionStatusChoices.FAILED,
        _("Documentation fixes that failed"),
        _("NetBox was not changed for these. They can be selected again from the report."),
    ),
    (
        ResolutionStatusChoices.DEVICE_POSSIBLE,
        _("Possible on the device"),
        _(
            "A connection module declares write support for these fields on this platform. "
            "Device writes are not implemented yet, so the device was not changed."
        ),
    ),
    (
        ResolutionStatusChoices.DEVICE_IMPOSSIBLE,
        _("Not possible on the device"),
        _(
            "No available connection module can write these on this platform. They can only "
            "be fixed in the documentation."
        ),
    ),
)


@register_model_view(Comparison, "resolution", path="resolution")
class ComparisonResolutionView(generic.ObjectView):
    queryset = Comparison.objects.select_related("device__platform")
    template_name = "netbox_compare/comparison_resolution.html"
    tab = ViewTab(
        label=_("Resolution"),
        badge=lambda obj: obj.divergences.exclude(resolution_status="").count(),
        weight=500,
        hide_if_empty=True,
    )

    def get_extra_context(self, request, instance):
        from netbox_compare.resolve import declared_capabilities

        resolved = instance.divergences.exclude(resolution_status="").select_related("resolved_by")
        sections = []
        for status, label, help_text in _SECTIONS:
            items = [d for d in resolved if d.resolution_status == status]
            if items:
                sections.append(
                    {
                        "label": label,
                        "help": help_text,
                        "color": ResolutionStatusChoices.colors.get(status),
                        "items": items,
                    }
                )
        device_modules = []
        if any(d.resolution == "device" for d in resolved):
            platform = instance.device.platform.slug if instance.device.platform else None
            device_modules = [
                {"name": name, "writable": sorted(caps[platform].writable, key=list(FIELDS).index)}
                for name, caps in declared_capabilities()
                if platform in caps
            ]
        return {"sections": sections, "device_modules": device_modules}


class ComparisonResolveView(LoginRequiredMixin, View):
    """Apply the administrator's resolution choices for one comparison (POST only)."""

    def post(self, request, pk):
        from netbox_compare.resolve import ResolveError, resolve

        comparison = get_object_or_404(
            Comparison.objects.restrict(request.user, "change").select_related("device__platform"),
            pk=pk,
        )
        decisions = {}
        for key, value in request.POST.items():
            if key.startswith("resolution_") and key[len("resolution_") :].isdigit():
                decisions[int(key[len("resolution_") :])] = value
        try:
            outcome = resolve(comparison, decisions, request.user)
        except ResolveError as exc:
            messages.warning(request, str(exc))
            return redirect(comparison.get_absolute_url())

        labels = dict(ResolutionStatusChoices)
        summary = ", ".join(f"{labels[status]}: {count}" for status, count in outcome.items())
        level = messages.warning if outcome[ResolutionStatusChoices.FAILED] else messages.success
        level(request, _("Resolution applied. {summary}.").format(summary=summary))
        return redirect("plugins:netbox_compare:comparison_resolution", pk=comparison.pk)


@register_model_view(Comparison, "delete")
class ComparisonDeleteView(generic.ObjectDeleteView):
    queryset = Comparison.objects.all()


@register_model_view(Comparison, "bulk_delete", path="delete", detail=False)
class ComparisonBulkDeleteView(generic.BulkDeleteView):
    queryset = Comparison.objects.all()
    filterset = filtersets.ComparisonFilterSet
    table = tables.ComparisonTable


@register_model_view(Device, "compare_comparisons", path="comparisons")
class DeviceComparisonsView(generic.ObjectChildrenView):
    queryset = Device.objects.all()
    child_model = Comparison
    table = tables.ComparisonTable
    filterset = filtersets.ComparisonFilterSet
    filterset_form = forms.ComparisonFilterForm
    actions = (BulkDelete,)
    tab = ViewTab(
        label=_("Device comparison results"),
        badge=lambda obj: obj.compare_comparisons.count(),
        permission="netbox_compare.view_comparison",
        weight=2000,
        hide_if_empty=True,
    )

    def get_children(self, request, parent):
        return Comparison.objects.restrict(request.user, "view").filter(device=parent)


class DeviceCompareView(LoginRequiredMixin, View):
    """Start a comparison of one device (POST only)."""

    def post(self, request, pk):
        if not request.user.has_perm("netbox_compare.add_comparison"):
            raise PermissionDenied
        device = get_object_or_404(Device.objects.restrict(request.user, "view"), pk=pk)
        platform = device.platform.slug if device.platform else None
        if connection_for_platform(platform) is None:
            messages.error(
                request,
                _("No connection module declares platform {platform}.").format(
                    platform=platform or _("(none)")
                ),
            )
            return redirect(device.get_absolute_url())

        policies = ComparisonPolicy.objects.restrict(request.user, "view")
        policy_id = request.POST.get("policy")
        if policy_id:
            policy = policies.filter(pk=policy_id).first() if policy_id.isdigit() else None
        else:
            policy = default_policy()
            if policy is not None and not policies.filter(pk=policy.pk).exists():
                policy = None
        if policy is None:
            messages.error(
                request,
                _("Choose a comparison policy.")
                if not policy_id
                else _("That comparison policy does not exist."),
            )
            return redirect(device.get_absolute_url())

        from netbox_compare.jobs import enqueue_comparison

        comparison = enqueue_comparison(device, request.user, policy)
        messages.info(
            request,
            _("Comparison of {device} with policy {policy} queued.").format(
                device=device, policy=policy
            ),
        )
        return redirect(comparison.get_absolute_url())
