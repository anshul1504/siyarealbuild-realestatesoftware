from django.db import migrations


LEGACY_COLUMNS = (
    "offboarded_at",
    "offboarded_by_id",
    "offboarding_reason",
    "reporting_manager_user_id",
    "department_master_id",
    "designation_master_id",
    "office_location_id",
    "team_id",
    "territory_master_id",
)


def remove_legacy_userprofile_fields(apps, schema_editor):
    table_name = "accounts_userprofile"
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }
        constraints = schema_editor.connection.introspection.get_constraints(cursor, table_name)
    for name, details in constraints.items():
        if details["index"] and set(details["columns"]).intersection(LEGACY_COLUMNS):
            schema_editor.execute(f'DROP INDEX "{name}"')
    for column in LEGACY_COLUMNS:
        if column in columns:
            schema_editor.execute(f"ALTER TABLE {table_name} DROP COLUMN {column}")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0027_remove_legacy_userprofile_employment_status"),
    ]

    operations = [
        migrations.RunPython(
            remove_legacy_userprofile_fields,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
