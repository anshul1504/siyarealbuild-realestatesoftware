from accounts.models import Role


MANAGEMENT_ROLES = {Role.COMPANY_OWNER, Role.MANAGER}
SALES_ROLES = {Role.COMPANY_OWNER, Role.MANAGER, Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER}


def user_role(user):
    return getattr(getattr(user, "profile", None), "role", None)


def can_manage_properties(user):
    return user_role(user) in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL}


def can_create_property(user):
    return user_role(user) in MANAGEMENT_ROLES


def can_update_property(user, property_obj=None):
    role = user_role(user)
    if role in MANAGEMENT_ROLES:
        return True
    if role == Role.TL and property_obj:
        return property_obj.owner_id == user.id or property_obj.assigned_to_id == user.id
    return False


def can_archive_property(user, property_obj=None):
    return user_role(user) in MANAGEMENT_ROLES


def can_restore_property(user, property_obj=None):
    return user_role(user) == Role.COMPANY_OWNER


def can_delete_property(user, property_obj=None):
    return user_role(user) == Role.COMPANY_OWNER


def can_export_properties(user):
    return user_role(user) in MANAGEMENT_ROLES


def can_manage_commission_payouts(user):
    return user_role(user) in MANAGEMENT_ROLES


def can_share_property(user, property_obj=None):
    return user_role(user) in SALES_ROLES


def can_manage_property_visit(user, property_obj=None, visit=None):
    role = user_role(user)
    if role in MANAGEMENT_ROLES:
        return True
    if role == Role.TL:
        if property_obj and (property_obj.owner_id == user.id or property_obj.assigned_to_id == user.id):
            return True
        if visit and (visit.assigned_employee_id == user.id or visit.scheduled_by_id == user.id):
            return True
    if visit and (visit.assigned_employee_id == user.id or visit.scheduled_by_id == user.id):
        return True
    return False
