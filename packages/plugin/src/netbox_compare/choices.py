from django.utils.translation import gettext_lazy as _
from utilities.choices import ChoiceSet


class ComparisonStatusChoices(ChoiceSet):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    CHOICES = (
        (PENDING, _("Pending"), "cyan"),
        (RUNNING, _("Running"), "blue"),
        (COMPLETED, _("Completed"), "green"),
        (FAILED, _("Failed"), "red"),
    )

    FINAL = (COMPLETED, FAILED)


class SeverityChoices(ChoiceSet):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    CHOICES = (
        (LOW, _("Low"), "gray"),
        (MEDIUM, _("Medium"), "yellow"),
        (HIGH, _("High"), "orange"),
        (CRITICAL, _("Critical"), "red"),
    )


class ObjectTypeChoices(ChoiceSet):
    DEVICE = "device"
    INTERFACE = "interface"
    IP_ADDRESS = "ip_address"

    CHOICES = (
        (DEVICE, _("Device")),
        (INTERFACE, _("Interface")),
        (IP_ADDRESS, _("IP address")),
    )


class DivergenceKindChoices(ChoiceSet):
    FIELD = "field"
    UNDOCUMENTED = "undocumented"
    MISSING_ON_DEVICE = "missing_on_device"

    CHOICES = (
        (FIELD, _("Field differs"), "orange"),
        (UNDOCUMENTED, _("Only on device"), "purple"),
        (MISSING_ON_DEVICE, _("Missing on device"), "red"),
    )


class ResolutionChoices(ChoiceSet):
    """Where the administrator chose to fix a divergence. Blank: no fix chosen."""

    DOCUMENTATION = "documentation"
    DEVICE = "device"

    CHOICES = (
        (DOCUMENTATION, _("Fix in documentation"), "blue"),
        (DEVICE, _("Fix on device"), "purple"),
    )


class ResolutionStatusChoices(ChoiceSet):
    APPLIED = "applied"  # NetBox was updated
    FAILED = "failed"  # the documentation fix could not be applied
    DEVICE_POSSIBLE = "device_possible"  # a connection module declares write support
    DEVICE_IMPOSSIBLE = "device_impossible"  # no connection module can write it

    CHOICES = (
        (APPLIED, _("Applied"), "green"),
        (FAILED, _("Failed"), "red"),
        (DEVICE_POSSIBLE, _("Possible on device"), "cyan"),
        (DEVICE_IMPOSSIBLE, _("Not possible on device"), "orange"),
    )

    # A divergence in one of these states is settled and can no longer be resolved.
    FINAL = (APPLIED,)


class SkipReasonChoices(ChoiceSet):
    """Why a device selected by a schedule was left out of a run."""

    NO_CONNECTION_MODULE = "no_connection_module"
    NO_CREDENTIALS = "no_credentials"
    CREDENTIALS_ERROR = "credentials_error"

    CHOICES = (
        (NO_CONNECTION_MODULE, _("No connection module declares the device's platform")),
        (NO_CREDENTIALS, _("No credentials module resolved the device")),
        (CREDENTIALS_ERROR, _("Credential resolution failed")),
    )


class RecurrenceChoices(ChoiceSet):
    """How a scheduled job repeats after its first run. Values match netbox_compare.schedule."""

    NONE = "none"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

    CHOICES = (
        (NONE, _("Does not repeat")),
        (DAILY, _("Daily")),
        (WEEKLY, _("Weekly")),
        (MONTHLY, _("Monthly")),
    )
