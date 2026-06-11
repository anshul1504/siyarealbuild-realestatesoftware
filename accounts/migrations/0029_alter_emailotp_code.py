from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0028_remove_legacy_userprofile_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="emailotp",
            name="code",
            field=models.CharField(max_length=128),
        ),
    ]
