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


def can_view_lead(user, lead):
    role = user_role(user)
    if role in MANAGEMENT_ROLES and lead.company_id == getattr(user_company(user), "id", None):
        return True
    return lead.assigned_to_id == user.id or lead.created_by_id == user.id


def can_edit_lead(user, lead):
    return can_view_lead(user, lead)
