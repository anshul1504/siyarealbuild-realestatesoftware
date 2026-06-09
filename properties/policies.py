from accounts.models import Role


def can_manage_properties(user):
    return getattr(getattr(user, "profile", None), "role", None) in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL}
