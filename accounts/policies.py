from .models import Role


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
