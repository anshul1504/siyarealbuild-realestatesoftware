from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0020_delete_companyeventgalleryimage"),
    ]

    operations = [
        migrations.AddField(
            model_name="meeting",
            name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("completed", "Completed"), ("cancelled", "Cancelled")],
                default="active",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="meeting",
            name="status_note",
            field=models.TextField(blank=True),
        ),
    ]
