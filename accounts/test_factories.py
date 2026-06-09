from django.contrib.auth import get_user_model

from .models import CompanyProfile, Role, UserProfile


def create_company(**overrides):
    defaults = {"name": "Test Company", "email": "company@example.com"}
    defaults.update(overrides)
    return CompanyProfile.objects.create(**defaults)


def create_user(*, company=None, role=Role.EXECUTIVE, email="user@example.com", **overrides):
    user = get_user_model().objects.create_user(username=email, email=email, **overrides)
    UserProfile.objects.create(user=user, company=company, role=role)
    return user
