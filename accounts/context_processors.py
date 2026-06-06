from .models import CompanyProfile, Role, UserProfile


def dashboard_access(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}

    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    company = user_profile.company or CompanyProfile.objects.order_by("id").first()
    if company and user_profile.company_id != company.id:
        user_profile.company = company
        user_profile.save(update_fields=["company", "updated_at"])

    role = user_profile.role
    is_owner = role == Role.COMPANY_OWNER
    is_manager = role == Role.MANAGER
    is_tl = role == Role.TL
    is_sales = role in {Role.MANAGER, Role.TL, Role.EXECUTIVE, Role.CHANNEL_PARTNER}

    return {
        "dashboard_profile": user_profile,
        "dashboard_company": company,
        "dashboard_role": role,
        "dashboard_role_label": user_profile.get_role_display(),
        "dashboard_is_owner": is_owner,
        "dashboard_is_manager": is_manager,
        "dashboard_is_tl": is_tl,
        "dashboard_is_sales": is_sales,
        "dashboard_can_manage_team": is_owner or is_manager,
        "dashboard_can_view_profiles": is_owner or is_manager or is_tl,
        "dashboard_can_manage_access": is_owner,
        "dashboard_can_manage_properties": is_owner or is_manager or is_tl,
        "dashboard_can_add_property": is_owner or is_manager,
        "dashboard_can_manage_marketing": is_owner,
        "dashboard_can_manage_operations": is_owner,
    }
