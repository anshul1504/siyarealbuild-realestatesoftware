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


def next_employee_code(role, company=None):
    prefix = f"SIYA-{ROLE_CODE_PREFIXES.get(role, 'EMP')}-"
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
