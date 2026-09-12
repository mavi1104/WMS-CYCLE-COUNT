import django.db.models.deletion
from django.db import migrations, models


# Migration: create assignments from distinct count/counter pairs. Troubleshoot: multiple counters for one count and the unique constraint.
def backfill_assignments(apps, schema_editor):
    Detail = apps.get_model("cycle_counts", "CycleCountDetail")
    Assignment = apps.get_model("cycle_counts", "CycleCountAssignment")
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if Detail._meta.db_table not in connection.introspection.table_names(cursor):
            return

    table = connection.ops.quote_name(Detail._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT DISTINCT cycle_count_id, counter_id FROM {table} "
            "WHERE counter_id IS NOT NULL"
        )
        rows = cursor.fetchall()
    assignments = [
        Assignment(cycle_count_id=cycle_count_id, counter_id=counter_id)
        for cycle_count_id, counter_id in rows
    ]
    Assignment.objects.using(connection.alias).bulk_create(assignments)


class Migration(migrations.Migration):
    dependencies = [("cycle_counts", "0005_detail_counter_id")]

    operations = [
        migrations.CreateModel(
            name="CycleCountAssignment",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("cycle_count_id", models.BigIntegerField(unique=True)),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                ("counter", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="cycle_count_assignments",
                    to="cycle_counts.counteraccount",
                )),
            ],
            options={
                "db_table": "mobile_cycle_count_assignments",
                "ordering": ["cycle_count_id"],
            },
        ),
        migrations.RunPython(backfill_assignments, migrations.RunPython.noop),
    ]
