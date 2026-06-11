from django.db import migrations


def remove_legacy_employment_status(apps, schema_editor):
    table_name = "accounts_userprofile"
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }
    if "employment_status" in columns:
        schema_editor.execute(f"ALTER TABLE {table_name} DROP COLUMN employment_status")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0026_signuprequest_requested_role_optional"),
    ]

    operations = [
        migrations.RunPython(
            remove_legacy_employment_status,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
