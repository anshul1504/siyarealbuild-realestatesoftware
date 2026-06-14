from accounts.models import Role
from django.db import models

from .models import Property, PropertyVisit


def visible_properties(user, *, include_archived=False):
    profile = getattr(user, "profile", None)
    company = getattr(profile, "company", None)
    base = Property.objects.all()
    if not include_archived:
        base = base.filter(is_archived=False)
    role = getattr(profile, "role", "")
    if role in {Role.COMPANY_OWNER, Role.MANAGER} and company:
        return base.filter(owner__profile__company=company)
    if role == Role.TL and company:
        return base.filter(owner__profile__company=company).filter(owner=user) | base.filter(owner__profile__company=company, assigned_to=user)
    if company:
        return base.filter(owner__profile__company=company).filter(owner=user) | base.filter(owner__profile__company=company, assigned_to=user)
    return base.filter(owner=user)


def visible_visits(user):
    properties = visible_properties(user)
    profile = getattr(user, "profile", None)
    company = getattr(profile, "company", None)
    role = getattr(profile, "role", "")
    if role in {Role.COMPANY_OWNER, Role.MANAGER}:
        return PropertyVisit.objects.filter(property__in=properties)
    base = PropertyVisit.objects.all()
    if company:
        base = base.filter(property__owner__profile__company=company)
    return base.filter(
        models.Q(property__in=properties)
        | models.Q(assigned_employee=user)
        | models.Q(scheduled_by=user)
        | models.Q(property__owner=user)
        | models.Q(property__assigned_to=user)
    )
