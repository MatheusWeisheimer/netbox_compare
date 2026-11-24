"""Run one comparison: NetBox -> canonical, device -> canonical, diff, persist."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from netbox_compare.choices import ComparisonStatusChoices
from netbox_compare.credentials import resolve_credentials
from netbox_compare.diff import compare, validate_policy
from netbox_compare.documented import documented_snapshot
from netbox_compare.models import Comparison, Divergence
from netbox_compare.modules import connection_for_platform
from netbox_compare_core import ConnectionModuleError, CredentialsError

logger = logging.getLogger(__name__)


class ComparisonError(Exception):
    """An expected failure; the message is shown in the report."""


def run_comparison(comparison: Comparison, log: logging.Logger = logger) -> Comparison:
    comparison.status = ComparisonStatusChoices.RUNNING
    comparison.started = timezone.now()
    comparison.error = ""
    comparison.save()
    try:
        _run(comparison, log)
    except Exception as exc:
        expected = isinstance(exc, ComparisonError | ConnectionModuleError | CredentialsError)
        if not expected:
            log.exception("Comparison %s crashed", comparison.pk)
        comparison.status = ComparisonStatusChoices.FAILED
        comparison.error = str(exc) if expected else f"Internal error: {type(exc).__name__}: {exc}"
        comparison.completed = timezone.now()
        comparison.save()
        raise
    return comparison


def _run(comparison: Comparison, log: logging.Logger) -> None:
    device = comparison.device
    platform = device.platform.slug if device.platform else None
    comparison.platform = platform or ""
    if not platform:
        raise ComparisonError(f"Device {device} has no platform")

    selected = connection_for_platform(platform)
    if selected is None:
        raise ComparisonError(f"No connection module declares platform {platform!r}")
    module_name, module, capabilities = selected
    comparison.connection_module = module_name

    if comparison.policy is None:
        raise ComparisonError("The comparison policy was deleted before the comparison ran")
    policy = validate_policy(comparison.policy.considered_fields)
    comparison.policy_fields = policy
    requested = sorted(f for f in policy if f in capabilities.readable)
    log.info("Using connection module %r; requesting %d fields", module_name, len(requested))

    credentials = resolve_credentials(device)
    if credentials is None:
        raise ComparisonError(f"No credentials module resolved device {device}")

    documented = documented_snapshot(device)
    with module.open(platform, credentials) as session:
        observed = session.read(requested)
    # Never trust a module to return only what was asked for.
    observed = observed.restrict(requested)

    result = compare(documented, observed, policy, readable=capabilities.readable)
    log.info(
        "%d matches, %d divergences, %d not comparable",
        result.matches,
        len(result.divergences),
        len(result.not_comparable),
    )

    with transaction.atomic():
        comparison.divergences.all().delete()
        Divergence.objects.bulk_create(
            Divergence(
                comparison=comparison,
                object_type=d.object_type,
                object_key=d.key,
                kind=d.kind,
                field=d.field,
                severity=d.severity,
                documented=d.documented,
                observed=d.observed,
            )
            for d in result.divergences
        )
        comparison.not_comparable = [
            {"field": nc.field, "reason": nc.reason.value, "keys": list(nc.keys)}
            for nc in result.not_comparable
        ]
        comparison.match_count = result.matches
        comparison.divergence_count = len(result.divergences)
        comparison.status = ComparisonStatusChoices.COMPLETED
        comparison.completed = timezone.now()
        comparison.save()
