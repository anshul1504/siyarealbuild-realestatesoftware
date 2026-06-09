from django.contrib import messages
from django.shortcuts import render

from ..models import CompanyProfile, Role


def owner_context(request):
    user_profile = getattr(request.user, "profile", None)
    company = getattr(user_profile, "company", None)
    if not user_profile or user_profile.role != Role.COMPANY_OWNER:
        messages.error(request, "Only company owner can access this section.")
        return user_profile, company, False
    if not company:
        company = CompanyProfile.objects.create(name="Siya Real Build", email=request.user.email)
        user_profile.company = company
        user_profile.save(update_fields=["company", "updated_at"])
    return user_profile, company, True


def owner_render(request, template, context):
    return render(request, template, context)
