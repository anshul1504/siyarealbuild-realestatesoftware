from accounts.models import Role

from .models import Property


def visible_properties(user):
    profile = getattr(user, "profile", None)
    company = getattr(profile, "company", None)
    if getattr(profile, "role", "") in {Role.COMPANY_OWNER, Role.MANAGER, Role.TL} and company:
        return Property.objects.filter(owner__profile__company=company)
    if company:
        return Property.objects.filter(owner__profile__company=company).filter(owner=user) | Property.objects.filter(owner__profile__company=company, assigned_to=user)
    return Property.objects.filter(owner=user)
