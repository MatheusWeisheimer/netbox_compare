from django.db import migrations, models


def interval_to_recurrence(apps, schema_editor):
    """Minute intervals become the nearest calendar recurrence that is not more frequent."""
    ComparisonSchedule = apps.get_model("netbox_compare", "ComparisonSchedule")
    for schedule in ComparisonSchedule.objects.all():
        if schedule.interval <= 24 * 60:
            schedule.recurrence = "daily"
        elif schedule.interval <= 7 * 24 * 60:
            schedule.recurrence = "weekly"
        else:
            schedule.recurrence = "monthly"
        schedule.save(update_fields=["recurrence"])


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_compare", "0005_comparison_schedules"),
    ]

    operations = [
        migrations.AddField(
            model_name="comparisonschedule",
            name="recurrence",
            field=models.CharField(default="none", max_length=20),
        ),
        migrations.RunPython(interval_to_recurrence, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="comparisonschedule",
            name="interval",
        ),
    ]
