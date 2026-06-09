from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.shortcuts import get_object_or_404, redirect

from ..forms import ReferralSettingForm, RoleTargetForm, SoftwarePopupForm
from ..models import ReferralReward, ReferralSetting, Role, RoleTarget, SignupRequest, SignupRequestStatus, SoftwarePopup
from .owner_common import owner_context, owner_render
@login_required
def owner_referrals(request):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    setting, _ = ReferralSetting.objects.get_or_create(company=company)
    form = ReferralSettingForm(request.POST or None, instance=setting, prefix="referral")
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Referral settings updated.")
        return redirect("accounts:owner_referrals")
    rewards = (
        ReferralReward.objects.filter(company=company)
        .select_related("referrer", "referrer__profile", "referred_user", "referred_user__profile", "signup_request")
        .order_by("-activated_at", "-created_at")
    )
    referral_stats = {
        "active_rewards": rewards.filter(status=ReferralReward.Status.ACTIVE).count(),
        "total_referrer_amount": rewards.filter(status=ReferralReward.Status.ACTIVE).aggregate(total=models.Sum("referrer_reward_amount"))["total"] or 0,
        "total_referred_amount": rewards.filter(status=ReferralReward.Status.ACTIVE).aggregate(total=models.Sum("referred_reward_amount"))["total"] or 0,
        "pending_references": SignupRequest.objects.filter(
            channel_partner_reference__gt="",
            status__in=[SignupRequestStatus.OTP_PENDING, SignupRequestStatus.PENDING_APPROVAL],
        ).count(),
    }
    paginator = Paginator(rewards, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    return owner_render(
        request,
        "accounts/owner_referrals.html",
        {
            "form": form,
            "setting": setting,
            "referral_stats": referral_stats,
            "page_obj": page_obj,
            "rewards": page_obj.object_list,
            "user_profile": user_profile,
        },
    )


@login_required
def owner_targets(request):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    form = RoleTargetForm(request.POST or None, company=company, prefix="target")
    if request.method == "POST" and form.is_valid():
        target = form.save(commit=False)
        target.company = company
        target.assigned_by = request.user
        target.save()
        messages.success(request, "Target saved.")
        return redirect("accounts:owner_targets")
    return owner_render(request, "accounts/owner_targets.html", {"form": form, "targets": RoleTarget.objects.filter(company=company), "user_profile": user_profile})


def _set_single_active_popup(company, popup):
    if popup.is_active:
        SoftwarePopup.objects.filter(company=company, is_active=True).exclude(id=popup.id).update(is_active=False)


@login_required
def owner_popups(request):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    if request.method == "POST":
        selected_ids = request.POST.getlist("popup_ids")
        action = request.POST.get("bulk_action", "").strip()
        selected_popups = SoftwarePopup.objects.filter(company=company, id__in=selected_ids)
        if not selected_popups.exists():
            messages.error(request, "Select at least one popup.")
            return redirect("accounts:owner_popups")
        if action == "activate":
            if selected_popups.count() != 1:
                messages.error(request, "Only one popup can be active. Select one popup to activate.")
                return redirect("accounts:owner_popups")
            popup = selected_popups.first()
            SoftwarePopup.objects.filter(company=company).exclude(id=popup.id).update(is_active=False)
            popup.is_active = True
            popup.save(update_fields=["is_active"])
            messages.success(request, "Popup activated. Other popups were deactivated automatically.")
        elif action == "deactivate":
            updated = selected_popups.update(is_active=False)
            messages.success(request, f"{updated} popup(s) deactivated.")
        elif action == "delete":
            deleted_count = selected_popups.count()
            selected_popups.delete()
            messages.success(request, f"{deleted_count} popup(s) deleted.")
        else:
            messages.error(request, "Choose a valid popup action.")
        return redirect("accounts:owner_popups")

    popups = SoftwarePopup.objects.filter(company=company).order_by("-is_active", "-created_at")
    query = request.GET.get("q", "").strip()
    selected_role = request.GET.get("role", "").strip()
    selected_status = request.GET.get("status", "").strip()
    if query:
        popups = popups.filter(models.Q(title__icontains=query) | models.Q(message__icontains=query) | models.Q(deal_label__icontains=query))
    if selected_role:
        popups = [popup for popup in popups if selected_role in (popup.roles or [])]
    if selected_status == "active":
        popups = popups.filter(is_active=True) if hasattr(popups, "filter") else [popup for popup in popups if popup.is_active]
    elif selected_status == "inactive":
        popups = popups.filter(is_active=False) if hasattr(popups, "filter") else [popup for popup in popups if not popup.is_active]
    query_params = request.GET.copy()
    query_params.pop("page", None)
    paginator = Paginator(popups, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return owner_render(
        request,
        "accounts/owner_popups.html",
        {
            "popups": page_obj.object_list,
            "page_obj": page_obj,
            "query": query,
            "selected_role": selected_role,
            "selected_status": selected_status,
            "query_string": query_params.urlencode(),
            "role_choices": Role.choices,
            "status_choices": (("active", "Active"), ("inactive", "Inactive")),
            "user_profile": user_profile,
        },
    )


@login_required
def owner_popup_create(request):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    form = SoftwarePopupForm(request.POST or None, request.FILES or None, prefix="popup")
    if request.method == "POST" and form.is_valid():
        popup = form.save(commit=False)
        popup.company = company
        popup.save()
        _set_single_active_popup(company, popup)
        messages.success(request, "Offer popup created.")
        return redirect("accounts:owner_popups")
    return owner_render(
        request,
        "accounts/owner_popup_form.html",
        {"form": form, "popup": None, "mode": "create", "user_profile": user_profile},
    )


@login_required
def owner_popup_detail(request, popup_id):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    popup = get_object_or_404(SoftwarePopup, id=popup_id, company=company)
    return owner_render(
        request,
        "accounts/owner_popup_detail.html",
        {"popup": popup, "role_choices": Role.choices, "user_profile": user_profile},
    )


@login_required
def owner_popup_edit(request, popup_id):
    user_profile, company, allowed = owner_context(request)
    if not allowed:
        return redirect("properties:dashboard")
    popup = get_object_or_404(SoftwarePopup, id=popup_id, company=company)
    form = SoftwarePopupForm(request.POST or None, request.FILES or None, instance=popup, prefix="popup")
    if request.method == "POST" and form.is_valid():
        popup = form.save()
        _set_single_active_popup(company, popup)
        messages.success(request, "Offer popup updated.")
        return redirect("accounts:owner_popups")
    return owner_render(
        request,
        "accounts/owner_popup_form.html",
        {"form": form, "popup": popup, "mode": "edit", "user_profile": user_profile},
    )
