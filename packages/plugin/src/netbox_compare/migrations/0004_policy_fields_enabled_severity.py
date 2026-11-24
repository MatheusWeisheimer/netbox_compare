from django.db import migrations

# Frozen copies, as of this migration, of the canonical field catalogue order and of
# netbox_compare.policy.DEFAULT_POLICY (the severity a field gets when it was not in a policy).
DEFAULT_SEVERITIES = {
    "device.name": "medium",
    "device.manufacturer": "high",
    "device.model": "high",
    "device.serial_number": "high",
    "device.os_version": "low",
    "interface.name": "medium",
    "interface.enabled": "high",
    "interface.description": "low",
    "interface.mtu": "medium",
    "interface.speed": "medium",
    "interface.mac_address": "low",
    "ip_address.address": "high",
    "ip_address.interface": "high",
    "ip_address.prefix_length": "high",
}


def forwards(apps, schema_editor):
    """{path: severity} -> {path: {"enabled", "severity"}} for every canonical field."""
    ComparisonPolicy = apps.get_model('netbox_compare', 'ComparisonPolicy')
    for policy in ComparisonPolicy.objects.all():
        old = policy.fields or {}
        if all(isinstance(v, dict) for v in old.values()) and old:
            continue  # already converted
        policy.fields = {
            path: {
                'enabled': path in old,
                'severity': old.get(path, default),
            }
            for path, default in DEFAULT_SEVERITIES.items()
        }
        policy.save(update_fields=['fields'])


def backwards(apps, schema_editor):
    ComparisonPolicy = apps.get_model('netbox_compare', 'ComparisonPolicy')
    for policy in ComparisonPolicy.objects.all():
        policy.fields = {
            path: entry['severity']
            for path, entry in (policy.fields or {}).items()
            if isinstance(entry, dict) and entry.get('enabled')
        }
        policy.save(update_fields=['fields'])


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_compare', '0003_comparison_policy'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
