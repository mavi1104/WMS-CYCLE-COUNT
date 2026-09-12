from django.db import migrations, models


FIELD_DEFINITIONS = (
    ("production_date_from", models.DateField(null=True, blank=True)),
    ("expiry_date_from", models.DateField(null=True, blank=True)),
    ("lot_no_from", models.CharField(max_length=4000, null=True, blank=True)),
)


# Add nullable history columns to the existing unmanaged detail table without changing current rows.
def add_metadata_from_columns(apps, schema_editor):
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
        existing_columns = {
            column.name for column in connection.introspection.get_table_description(cursor, table)
        }

    duplicate_columns = [name for name, _field in FIELD_DEFINITIONS if name in existing_columns]
    if duplicate_columns:
        raise RuntimeError(
            f"Columns already exist: {', '.join(duplicate_columns)}. Verify the database before applying this migration."
        )

    for name, field in FIELD_DEFINITIONS:
        field.set_attributes_from_name(name)
        field.model = Detail
        schema_editor.add_field(Detail, field)


class Migration(migrations.Migration):
    dependencies = [("cycle_counts", "0007_assignment_last_seen")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(add_metadata_from_columns)],
            state_operations=[
                migrations.AddField(
                    model_name="cyclecountdetail",
                    name="production_date_from",
                    field=models.DateField(null=True, blank=True),
                ),
                migrations.AddField(
                    model_name="cyclecountdetail",
                    name="expiry_date_from",
                    field=models.DateField(null=True, blank=True),
                ),
                migrations.AddField(
                    model_name="cyclecountdetail",
                    name="lot_no_from",
                    field=models.CharField(max_length=4000, null=True, blank=True),
                ),
            ],
        ),
    ]
