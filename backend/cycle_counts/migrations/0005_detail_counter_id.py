from django.db import migrations, models
from django.db.models import OuterRef, Subquery


# Migration: add nullable counter_id to the legacy detail table. Troubleshoot: a missing table or existing column before migration.
def add_counter_column(apps, schema_editor):
    connection = schema_editor.connection
    Detail = apps.get_model("cycle_counts", "CycleCountDetail")
    table = Detail._meta.db_table
    with connection.cursor() as cursor:
        tables = connection.introspection.table_names(cursor)
        if table not in tables:
            # Isolated SQLite tests create unmanaged legacy tables after migrations.
            if connection.vendor == "sqlite":
                return
            raise RuntimeError("The existing cycle_count_details table is required.")
        columns = connection.introspection.get_table_description(cursor, table)
    if any(column.name == "counter_id" for column in columns):
        raise RuntimeError("counter_id already exists; verify its mapping before applying this migration.")
    field = models.BigIntegerField(null=True, blank=True)
    field.set_attributes_from_name("counter_id")
    field.model = Detail
    schema_editor.add_field(Detail, field)


# Migration: fill null detail counter_id values from the latest audit log. Troubleshoot: detail IDs and log timestamps.
def populate_from_logs(apps, schema_editor):
    connection = schema_editor.connection
    Detail = apps.get_model("cycle_counts", "CycleCountDetail")
    Log = apps.get_model("cycle_counts", "CounterCountLog")
    with connection.cursor() as cursor:
        if Detail._meta.db_table not in connection.introspection.table_names(cursor):
            return
    logs = Log.objects.using(connection.alias)
    latest = logs.filter(cycle_count_detail_id=OuterRef("pk")).order_by("-counted_at", "-id")
    Detail.objects.using(connection.alias).filter(
        counter_id__isnull=True, pk__in=logs.values("cycle_count_detail_id"),
    ).update(counter_id=Subquery(latest.values("counter_id")[:1]))


class Migration(migrations.Migration):
    dependencies = [("cycle_counts", "0004_remove_supervisor_role")]

    operations = [
        # Explicitly authorized addition to an otherwise unmanaged legacy table.
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(add_counter_column)],
            state_operations=[migrations.AddField(
                model_name="cyclecountdetail", name="counter_id",
                field=models.BigIntegerField(null=True, blank=True),
            )],
        ),
        migrations.RunPython(populate_from_logs, migrations.RunPython.noop),
    ]
