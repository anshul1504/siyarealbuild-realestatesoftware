from django.db import migrations, models
from django.db.models import Q


PREFIXES = {
    "company_owner": "OWN",
    "manager": "MGR",
    "tl": "TL",
    "executive": "EXE",
    "channel_partner": "CP",
}


def normalize_employee_codes(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    EmployeeInvite = apps.get_model("accounts", "EmployeeInvite")
    companies = UserProfile.objects.values_list("company_id", flat=True).distinct()
    for company_id in companies:
        for role, prefix in PREFIXES.items():
            profiles = UserProfile.objects.filter(company_id=company_id, role=role).order_by("id")
            for number, profile in enumerate(profiles, start=1):
                profile.employee_code = f"SIYA-{prefix}-{number:03d}"
                profile.save(update_fields=["employee_code"])
            invites = EmployeeInvite.objects.filter(company_id=company_id, role=role).order_by("id")
            for number, invite in enumerate(invites, start=profiles.count() + 1):
                invite.employee_code = f"SIYA-{prefix}-{number:03d}"
                invite.save(update_fields=["employee_code"])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0029_alter_emailotp_code")]

    operations = [
        migrations.RunPython(normalize_employee_codes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="userprofile",
            constraint=models.UniqueConstraint(
                fields=("company", "employee_code"),
                condition=~Q(employee_code=""),
                name="unique_company_employee_code",
            ),
        ),
    ]
