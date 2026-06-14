from django.db import migrations


def normalize_choice_values(apps, schema_editor):
    Property = apps.get_model("properties", "Property")
    ColonyPlot = apps.get_model("properties", "ColonyPlot")

    Property.objects.filter(category="colony").exclude(
        development_status__in=["pre_launch", "launched", "under_development", "developed", "ready_possession", ""]
    ).update(development_status="under_development")

    facing_map = {
        "East": "east",
        "West": "west",
        "North": "north",
        "South": "south",
        "Corner": "corner",
        "Garden Facing": "garden_facing",
        "Main road": "main_road",
        "Main Road": "main_road",
    }
    for old_value, new_value in facing_map.items():
        ColonyPlot.objects.filter(facing=old_value).update(facing=new_value)


class Migration(migrations.Migration):
    dependencies = [
        ("properties", "0013_colonyplot_is_wide_road_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_choice_values, migrations.RunPython.noop),
    ]
