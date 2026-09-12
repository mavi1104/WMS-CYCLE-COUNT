from django.db import migrations, models


# Migration: assign sequential counter numbers in ID order. Troubleshoot: the historical model and unique counter numbers.
def assign_counter_numbers(apps, schema_editor):
    CounterAccount = apps.get_model("cycle_counts", "CounterAccount")
    for number, counter in enumerate(CounterAccount.objects.order_by("id"), start=1):
        counter.counter_number = number
        counter.save(update_fields=["counter_number"])


class Migration(migrations.Migration):
    dependencies = [
        ("cycle_counts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="counteraccount",
            name="counter_number",
            field=models.PositiveIntegerField(null=True),
        ),
        migrations.RunPython(assign_counter_numbers, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="counteraccount",
            name="counter_number",
            field=models.PositiveIntegerField(unique=True),
        ),
    ]
