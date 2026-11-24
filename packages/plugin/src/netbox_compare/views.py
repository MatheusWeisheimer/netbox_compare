from collections import Counter

from dcim.models import Device
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from django.views import View
from netbox.object_actions import BulkDelete, BulkExport, DeleteObject
from netbox.views import generic
from utilities.views import ViewTab, register_model_view

from netbox_compare import filtersets, forms, tables
from netbox_compare.choices import ObjectTypeChoices, SeverityChoices
from netbox_compare.models import Comparison
from netbox_compare.modules import connection_for_platform
from netbox_compare_core import FIELDS

REASON_LABELS = {
    "not_readable": _("The connection module cannot read this field on this platform"),
    "not_observed": _("The device did not return a value in this run"),
    "not_in_schema": _("This NetBox version has no field to document it"),
}


@register_model_view(Comparison, "list", path="", detail=False)
class ComparisonListView(generic.ObjectListView):
    queryset = Comparison.objects.select_related("device", "requested_by")
    table = tables.ComparisonTable
    filterset = filtersets.ComparisonFilterSet
    filterset_form = forms.ComparisonFilterForm
    actions = (BulkExport, BulkDelete)


@register_model_view(Comparison)
class ComparisonView(generic.ObjectView):
    queryset = Comparison.objects.select_related("device", "requested_by", "job")
    actions = (DeleteObject,)

    def get_extra_context(self, request, instance):
        divergences = list(instance.divergences.all())
        groups = []
        for object_type, label in ObjectTypeChoices:
            items = [d for d in divergences if d.object_type == object_type]
            if items:
                groups.append({"object_type": object_type, "label": label, "items": items})
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
                instance.policy.items(), key=lambda kv: order.get(kv[0], len(order))
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
        }


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
        label=_("Comparisons"),
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

        from netbox_compare.jobs import enqueue_comparison

        comparison = enqueue_comparison(device, request.user)
        messages.info(request, _("Comparison of {device} queued.").format(device=device))
        return redirect(comparison.get_absolute_url())
