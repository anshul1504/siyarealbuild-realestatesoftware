from django.db import models

from .models import Role, RoleMatrixRule, UserProfile


TEAM_MODULE = "team_management"


def is_owner(profile):
    return bool(profile and profile.role == Role.COMPANY_OWNER)


def can_manage_team(profile):
    return bool(profile and profile.role in {Role.COMPANY_OWNER, Role.MANAGER})


def can_view_team(profile):
    return bool(profile and profile.role in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL})


def allowed_managed_roles(profile):
    if not profile:
        return set()
    if profile.role == Role.COMPANY_OWNER:
        return {Role.MANAGER, Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER}
    if profile.role == Role.MANAGER:
        return {Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER}
    return set()


def role_matrix_allows(profile, permission, module=TEAM_MODULE):
    if not profile:
        return False
    if profile.role == Role.COMPANY_OWNER:
        return True
    rule = RoleMatrixRule.objects.filter(
        company=profile.company,
        role=profile.role,
        module__iexact=module,
    ).first()
    if not rule:
        return True
    return bool(getattr(rule, f"can_{permission}", False))


def visible_team_profiles_for(profile, company):
    if not role_matrix_allows(profile, "view"):
        return None, False
    visible_roles = {
        Role.COMPANY_OWNER: {Role.COMPANY_OWNER, Role.MANAGER, Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER},
        Role.MANAGER: {Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER},
        Role.TL: {Role.EXECUTIVE, Role.CHANNEL_PARTNER},
    }.get(profile.role)
    if not visible_roles:
        return None, False
    profiles = UserProfile.objects.filter(company=company, role__in=visible_roles).select_related("user", "company")
    if profile.role != Role.COMPANY_OWNER:
        manager_keys = [profile.employee_code, profile.user.email, profile.user.get_full_name(), profile.user.username]
        manager_keys = [value for value in {key.strip() for key in manager_keys if key and key.strip()}]
        scoped = models.Q(reporting_manager__in=manager_keys)
        if profile.role == Role.MANAGER:
            scoped |= models.Q(role=Role.TL)
        profiles = profiles.filter(scoped).exclude(id=profile.id)
    return profiles.order_by("role", "user__first_name", "user__email"), profile.role == Role.COMPANY_OWNER
