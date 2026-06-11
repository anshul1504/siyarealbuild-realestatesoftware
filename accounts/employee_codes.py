import re

from django.db import transaction

from .models import Role, UserProfile


ROLE_CODE_PREFIXES = {
    Role.COMPANY_OWNER: "OWN",
    Role.MANAGER: "MGR",
    Role.TL: "TL",
    Role.EXECUTIVE: "EXE",
    Role.CHANNEL_PARTNER: "CP",
}


def employee_code_prefix(role):
    return f"SIYA-{ROLE_CODE_PREFIXES.get(role, 'EMP')}-"


def validate_employee_code(value, role):
    code = (value or "").upper().strip()
    if not code:
        return ""
    prefix = employee_code_prefix(role)
    if not re.fullmatch(rf"{re.escape(prefix)}\d{{3,}}", code):
        raise ValueError(f"Employee code must use {prefix}001 format.")
    return code


def next_employee_code(role, company=None):
    prefix = employee_code_prefix(role)
    with transaction.atomic():
        profiles = UserProfile.objects.select_for_update().filter(employee_code__istartswith=prefix)
        if company:
            profiles = profiles.filter(company=company)
        highest = 0
        for code in profiles.values_list("employee_code", flat=True):
            match = re.fullmatch(rf"{re.escape(prefix)}(\d+)", code, re.IGNORECASE)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"{prefix}{highest + 1:03d}"
