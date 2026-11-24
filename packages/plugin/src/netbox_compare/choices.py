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
