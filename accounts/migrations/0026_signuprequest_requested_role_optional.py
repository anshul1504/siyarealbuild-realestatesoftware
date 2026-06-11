from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0025_auditlog_employeeprofilechange_notificationdelivery_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="signuprequest",
            name="requested_role",
            field=models.CharField(blank=True, choices=[("company_owner", "Company Owner"), ("manager", "Manager"), ("tl", "TL"), ("executive", "Executive"), ("channel_partner", "Channel Partner")], max_length=32),
        ),
    ]
