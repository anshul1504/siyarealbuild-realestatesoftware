from django.db import migrations


def repair_plot_status_history_schema(apps, schema_editor):
    table_name = "properties_plotstatushistory"
    existing_tables = schema_editor.connection.introspection.table_names()
    if table_name not in existing_tables:
        return

    cursor = schema_editor.connection.cursor()
    columns = {column.name for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)}
    rename_pairs = [
        ("previous_status", "from_status"),
        ("new_status", "to_status"),
        ("reason", "note"),
    ]
    for old_name, new_name in rename_pairs:
        if old_name in columns and new_name not in columns:
            schema_editor.execute(f'ALTER TABLE "{table_name}" RENAME COLUMN "{old_name}" TO "{new_name}"')
            columns.remove(old_name)
            columns.add(new_name)


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0009_property_archive_note_property_archived_at_and_more"),
    ]

    operations = [
        migrations.RunPython(repair_plot_status_history_schema, migrations.RunPython.noop),
    ]
