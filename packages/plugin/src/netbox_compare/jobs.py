from django.db import transaction
from netbox.jobs import JobRunner

from netbox_compare.models import Comparison
from netbox_compare.runner import run_comparison


class CompareDeviceJob(JobRunner):
    """Background job running one :class:`Comparison`. Detects and reports only; it never
    applies fixes."""

    class Meta:
        name = "Device comparison"

    def run(self, comparison_id, *args, **kwargs):
        comparison = Comparison.objects.select_related("device__platform").get(pk=comparison_id)
        run_comparison(comparison, log=self.logger)


@transaction.atomic
def enqueue_comparison(device, user) -> Comparison:
    comparison = Comparison(device=device, requested_by=user)
    comparison.full_clean()
    comparison.save()
    # NetBox only attaches jobs to models with the `jobs` feature (JobsMixin); Device has none,
    # so the job belongs to the comparison.
    job = CompareDeviceJob.enqueue(instance=comparison, user=user, comparison_id=comparison.pk)
    comparison.job = job
    comparison.save(update_fields=["job"])
    return comparison
