from django.contrib import messages
from django.shortcuts import render

from ..models import CompanyProfile, Role
from ..policies import role_matrix_allows


def owner_context(request, *, module=None, permission="view"):
    user_profile = getattr(request.user, "profile", None)
    company = getattr(user_profile, "company", None)
    delegated = bool(module and role_matrix_allows(user_profile, permission, module=module))
    if not user_profile or (user_profile.role != Role.COMPANY_OWNER and not delegated):
        messages.error(request, "Only company owner can access this section.")
        return user_profile, company, False
    if not company:
        company = CompanyProfile.objects.create(name="Siya Real Build", email=request.user.email)
        user_profile.company = company
        user_profile.save(update_fields=["company", "updated_at"])
    return user_profile, company, True


def owner_render(request, template, context):
    return render(request, template, context)
