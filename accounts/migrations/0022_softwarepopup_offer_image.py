from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0021_meeting_status_meeting_status_note"),
    ]

    operations = [
        migrations.AddField(
            model_name="softwarepopup",
            name="offer_image",
            field=models.ImageField(blank=True, upload_to="popups/offers/"),
        ),
    ]
