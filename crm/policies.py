from django.contrib.auth import get_user_model

from accounts.models import Role


MANAGEMENT_ROLES = {Role.COMPANY_OWNER, Role.MANAGER}
TEAM_ROLES = {Role.COMPANY_OWNER, Role.MANAGER, Role.TL}


def user_profile(user):
    return getattr(user, "profile", None)


def user_company(user):
    profile = user_profile(user)
    return getattr(profile, "company", None)


def user_role(user):
    profile = user_profile(user)
    return getattr(profile, "role", "")


def can_view_all_leads(user):
    return user_role(user) in MANAGEMENT_ROLES


def can_assign_leads(user):
    return user_role(user) in TEAM_ROLES


def can_configure_meta(user):
    return user_role(user) == Role.COMPANY_OWNER


def team_member_ids_for(user):
    company = user_company(user)
    profile = user_profile(user)
    if user_role(user) != Role.TL or not company or not profile:
        return []

    identifiers = {
        getattr(profile, "employee_code", ""),
        getattr(user, "email", ""),
        getattr(user, "username", ""),
        user.get_full_name(),
    }
    identifiers = [identifier.strip() for identifier in identifiers if identifier and identifier.strip()]
    if not identifiers:
        return []

    User = get_user_model()
    return list(
        User.objects.filter(
            profile__company=company,
            profile__reporting_manager__in=identifiers,
            is_active=True,
        ).values_list("id", flat=True)
    )


def can_view_lead(user, lead):
    role = user_role(user)
    if role in MANAGEMENT_ROLES and lead.company_id == getattr(user_company(user), "id", None):
        return True
    if role == Role.TL and lead.company_id == getattr(user_company(user), "id", None):
        team_ids = team_member_ids_for(user)
        if lead.assigned_to_id in team_ids or lead.created_by_id in team_ids:
            return True
    return lead.assigned_to_id == user.id or lead.created_by_id == user.id


def can_edit_lead(user, lead):
    return can_view_lead(user, lead)
