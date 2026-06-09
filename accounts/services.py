from django.db import transaction

from .models import AuditLog, EmployeeProfileChange


def record_audit(*, actor, action, target, company=None, details=None, target_label=None):
    return AuditLog.objects.create(
        company=company,
        actor=actor,
        action=action,
        target_type=target.__class__.__name__,
        target_id=str(getattr(target, "pk", "") or ""),
        target_label=target_label or str(target),
        details=details or {},
    )


@transaction.atomic
def update_employee_profile(*, profile, form, actor):
    tracked = set(form.changed_data) - {"profile_image", "aadhaar_document", "pan_document"}
    before = {field: str(getattr(profile, field, "") or "") for field in tracked if hasattr(profile, field)}
    updated = form.save()
    changes = {
        field: {"from": before.get(field, ""), "to": str(getattr(updated, field, "") or "")}
        for field in tracked
        if before.get(field, "") != str(getattr(updated, field, "") or "")
    }
    if changes:
        EmployeeProfileChange.objects.create(profile=updated, changed_by=actor, changes=changes)
        record_audit(actor=actor, action="employee.profile_updated", target=updated, company=updated.company, details=changes)
    return updated


@transaction.atomic
def bulk_update_profiles(*, profiles, actor, department="", reporting_manager="", work_location=""):
    changes = {key: value for key, value in {
        "department": department,
        "reporting_manager": reporting_manager,
        "work_location": work_location,
    }.items() if value}
    count = 0
    for profile in profiles.select_for_update():
        previous = {key: getattr(profile, key) for key in changes}
        for key, value in changes.items():
            setattr(profile, key, value)
        profile.save(update_fields=[*changes, "updated_at"])
        EmployeeProfileChange.objects.create(
            profile=profile,
            changed_by=actor,
            changes={key: {"from": previous[key], "to": value} for key, value in changes.items()},
        )
        count += 1
    if count:
        record_audit(actor=actor, action="employee.bulk_updated", target=actor, company=actor.profile.company, details={"count": count, **changes})
    return count
