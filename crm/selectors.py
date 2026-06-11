from django.db.models import Q
from django.contrib.auth import get_user_model

from accounts.models import Role

from .models import Lead
from .policies import user_company, user_role


def visible_leads_for(user):
    company = user_company(user)
    if not company:
        return Lead.objects.none()
    leads = Lead.objects.filter(company=company).select_related("assigned_to", "created_by", "property", "company")
    role = user_role(user)
    if role in {Role.COMPANY_OWNER, Role.MANAGER}:
        return leads
    return leads.filter(Q(assigned_to=user) | Q(created_by=user))


def assignable_users_for(user):
    company = user_company(user)
    User = get_user_model()
    if not company:
        return User.objects.none()

    return (
        User.objects.filter(profile__company=company, is_active=True)
        .exclude(profile__role=Role.COMPANY_OWNER)
        .order_by("profile__role", "first_name", "email")
    )
