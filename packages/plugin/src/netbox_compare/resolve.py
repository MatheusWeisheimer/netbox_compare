"""Apply the administrator's resolution decisions for one comparison.

Each divergence is fixed in the documentation, on the device, or left alone. The plugin never
picks a direction itself, and this runs only on an explicit request from the UI: scheduled jobs
never call it.

Device fixes are only checked, not performed. The outcome says whether any configured connection
module declares write support for the field on the device's platform. No connection module
writes to devices yet.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping

from django.db import transaction
from django.utils import timezone

from netbox_compare.choices import (
    ComparisonStatusChoices,
    ResolutionChoices,
    ResolutionStatusChoices,
)
from netbox_compare.device_fix import device_feasibility
from netbox_compare.documentation_fix import apply_documentation_fixes
from netbox_compare.models import Comparison, Divergence
from netbox_compare.modules import get_connection_modules

logger = logging.getLogger(__name__)

DEVICE_WRITES_PENDING = "Device writes are not implemented yet; nothing was changed on the device."


class ResolveError(Exception):
    """The decisions cannot be applied at all; the message is shown to the administrator."""


def declared_capabilities():
    """``(name, capabilities)`` for each configured connection module that declares them."""
    out = []
    for name, module in get_connection_modules():
        try:
            out.append((name, module.capabilities()))
        except Exception as exc:
            logger.error("Connection module %r failed to declare capabilities: %s", name, exc)
    return out


def resolve(comparison: Comparison, decisions: Mapping[int, str], user) -> Counter:
    """Apply ``decisions`` (divergence pk -> resolution; blank means no fix) and return a count
    of outcomes per resolution status."""
    if comparison.status != ComparisonStatusChoices.COMPLETED:
        raise ResolveError("Only a completed comparison can be resolved.")
    unknown = {v for v in decisions.values() if v} - set(ResolutionChoices.values())
    if unknown:
        raise ResolveError(f"Unknown resolution {sorted(unknown)}.")
    chosen = {pk: v for pk, v in decisions.items() if v}
    if not chosen:
        raise ResolveError("No divergence was marked for a fix.")

    now = timezone.now()
    with transaction.atomic():
        divergences = list(
            Divergence.objects.select_for_update()
            .filter(comparison=comparison, pk__in=chosen)
            .exclude(resolution_status__in=ResolutionStatusChoices.FINAL)
            .order_by("pk")
        )
        if not divergences:
            raise ResolveError("The selected divergences were already fixed.")
        for d in divergences:
            d.resolution = chosen[d.pk]

        to_document = [d for d in divergences if d.resolution == ResolutionChoices.DOCUMENTATION]
        to_device = [d for d in divergences if d.resolution == ResolutionChoices.DEVICE]

        if to_document:
            apply_documentation_fixes(comparison.device, to_document, user)

        if to_device:
            modules = declared_capabilities()
            platform = comparison.device.platform.slug if comparison.device.platform else None
            for d in to_device:
                feasibility = device_feasibility(d.field, platform, modules)
                if feasibility.possible:
                    d.resolution_status = ResolutionStatusChoices.DEVICE_POSSIBLE
                    d.resolution_detail = f"{feasibility.reason} {DEVICE_WRITES_PENDING}"
                else:
                    d.resolution_status = ResolutionStatusChoices.DEVICE_IMPOSSIBLE
                    d.resolution_detail = feasibility.reason

        for d in divergences:
            d.resolved_by = user
            d.resolved_at = now
        Divergence.objects.bulk_update(
            divergences,
            ["resolution", "resolution_status", "resolution_detail", "resolved_by", "resolved_at"],
        )
    return Counter(d.resolution_status for d in divergences)
