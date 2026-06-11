import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import models
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from ..forms import ReferralSettingForm, RoleTargetForm, SoftwarePopupForm
from ..models import ReferralReward, ReferralSetting, Role, RoleTarget, SignupRequest, SignupRequestStatus, SoftwarePopup, UserProfile
from ..marketing import MARKETING_MODULE, can_perform_marketing
from ..operations import OPERATIONS_MODULE, can_perform_operations
from ..services import record_audit
from .owner_common import owner_context, owner_render


def _reward_queryset(company):
    return (
        ReferralReward.objects.filter(company=company)
        .select_related("referrer", "referrer__profile", "referred_user", "referred_user__profile", "signup_request")
        .order_by("-activated_at", "-created_at")
    )


def _pending_referral_queryset(company):
    lookup = models.Q()
    for profile in UserProfile.objects.filter(company=company).select_related("user"):
        for value in (profile.employee_code, profile.user.email, profile.user.username):
            if value:
                lookup |= models.Q(channel_partner_reference__iexact=value.strip())
    if not lookup:
        return SignupRequest.objects.none()
    return SignupRequest.objects.filter(
        lookup,
        status__in=[SignupRequestStatus.OTP_PENDING, SignupRequestStatus.PENDING_APPROVAL],
    )


def _marketing_trend(queryset, date_field, days=14):
    since = timezone.now() - timezone.timedelta(days=days - 1)
    rows = (
        queryset.filter(**{f"{date_field}__gte": since})
        .annotate(day=TruncDate(date_field))
        .values("day")
        .annotate(total=models.Count("id"))
        .order_by("day")
    )
    return list(rows)


def _popup_ctr(popups):
    impressions = sum(popup.impressions for popup in popups)
    clicks = sum(popup.clicks for popup in popups)
    return round((clicks / impressions) * 100, 1) if impressions else 0


@login_required
def owner_marketing_dashboard(request):
    user_profile, company, allowed = owner_context(request, module=MARKETING_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    rewards = _reward_queryset(company)
    popups = list(SoftwarePopup.objects.filter(company=company).order_by("-created_at"))
    referral_stats = {
        "active_rewards": rewards.filter(status=ReferralReward.Status.ACTIVE).count(),
        "unpaid_payouts": rewards.filter(payout_status=ReferralReward.PayoutStatus.UNPAID).count(),
        "paid_payouts": rewards.filter(payout_status=ReferralReward.PayoutStatus.PAID).count(),
        "redeemed_coupons": rewards.filter(
            models.Q(referrer_coupon_redeemed_at__isnull=False) | models.Q(referred_coupon_redeemed_at__isnull=False)
        ).count(),
        "pending_references": _pending_referral_queryset(company).count(),
    }
    popup_stats = {
        "total_popups": len(popups),
        "active_popups": sum(1 for popup in popups if popup.is_active),
        "impressions": sum(popup.impressions for popup in popups),
        "clicks": sum(popup.clicks for popup in popups),
        "closes": sum(popup.closes for popup in popups),
        "ctr": _popup_ctr(popups),
    }
    return owner_render(
        request,
        "accounts/owner_marketing_dashboard.html",
        {
            "referral_stats": referral_stats,
            "popup_stats": popup_stats,
            "reward_trend": _marketing_trend(rewards, "activated_at"),
            "popup_trend": _marketing_trend(SoftwarePopup.objects.filter(company=company), "created_at"),
            "recent_rewards": rewards[:5],
            "recent_popups": popups[:5],
            "user_profile": user_profile,
        },
    )


@login_required
def owner_referrals(request):
    user_profile, company, allowed = owner_context(request, module=MARKETING_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    setting, _ = ReferralSetting.objects.get_or_create(company=company)
    form = ReferralSettingForm(request.POST or None, instance=setting, prefix="referral")
    if request.method == "POST" and request.POST.get("reward_action"):
        if not can_perform_marketing(user_profile, "update"):
            messages.error(request, "You do not have permission to update referral rewards.")
            return redirect("accounts:owner_referrals")
        reward = get_object_or_404(ReferralReward, company=company, id=request.POST.get("reward_id"))
        action = request.POST.get("reward_action")
        if action in dict(ReferralReward.PayoutStatus.choices):
            reward.payout_status = action
            reward.payout_note = request.POST.get("payout_note", "").strip()
            reward.paid_at = timezone.now() if action == ReferralReward.PayoutStatus.PAID else None
            reward.save(update_fields=["payout_status", "payout_note", "paid_at"])
            record_audit(actor=request.user, action="marketing.reward_payout_updated", target=reward, company=company, details={"payout_status": action})
            messages.success(request, "Referral payout status updated.")
        elif action == "redeem_referrer_coupon":
            reward.referrer_coupon_redeemed_at = timezone.now()
            reward.save(update_fields=["referrer_coupon_redeemed_at"])
            record_audit(actor=request.user, action="marketing.referrer_coupon_redeemed", target=reward, company=company)
            messages.success(request, "Referrer coupon marked as redeemed.")
        elif action == "redeem_referred_coupon":
            reward.referred_coupon_redeemed_at = timezone.now()
            reward.save(update_fields=["referred_coupon_redeemed_at"])
            record_audit(actor=request.user, action="marketing.referred_coupon_redeemed", target=reward, company=company)
            messages.success(request, "Referred coupon marked as redeemed.")
        else:
            messages.error(request, "Choose a valid referral action.")
        return redirect("accounts:owner_referrals")
    if request.method == "POST" and not can_perform_marketing(user_profile, "update"):
        messages.error(request, "You do not have permission to update referral settings.")
        return redirect("accounts:owner_referrals")
    if request.method == "POST" and form.is_valid():
        form.save()
        record_audit(actor=request.user, action="marketing.referral_settings_updated", target=setting, company=company)
        messages.success(request, "Referral settings updated.")
        return redirect("accounts:owner_referrals")
    rewards = _reward_queryset(company)
    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    selected_payout = request.GET.get("payout", "").strip()
    if query:
        rewards = rewards.filter(
            models.Q(referral_code__icontains=query)
            | models.Q(referrer__email__icontains=query)
            | models.Q(referred_user__email__icontains=query)
            | models.Q(referrer__first_name__icontains=query)
            | models.Q(referred_user__first_name__icontains=query)
        )
    if selected_status:
        rewards = rewards.filter(status=selected_status)
    if selected_payout:
        rewards = rewards.filter(payout_status=selected_payout)
    referral_stats = {
        "active_rewards": rewards.filter(status=ReferralReward.Status.ACTIVE).count(),
        "total_referrer_amount": rewards.filter(status=ReferralReward.Status.ACTIVE).aggregate(total=models.Sum("referrer_reward_amount"))["total"] or 0,
        "total_referred_amount": rewards.filter(status=ReferralReward.Status.ACTIVE).aggregate(total=models.Sum("referred_reward_amount"))["total"] or 0,
        "unpaid_payouts": rewards.filter(payout_status=ReferralReward.PayoutStatus.UNPAID).count(),
        "paid_payouts": rewards.filter(payout_status=ReferralReward.PayoutStatus.PAID).count(),
        "pending_references": _pending_referral_queryset(company).count(),
    }
    if request.GET.get("export") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="referral-rewards.csv"'
        writer = csv.writer(response)
        writer.writerow(["Referral Code", "Referrer", "Referred", "Payout Status", "Status", "Activated At"])
        for reward in rewards:
            writer.writerow([reward.referral_code, reward.referrer.email, reward.referred_user.email, reward.get_payout_status_display(), reward.get_status_display(), f"{reward.activated_at:%Y-%m-%d}"])
        return response
    paginator = Paginator(rewards, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return owner_render(
        request,
        "accounts/owner_referrals.html",
        {
            "form": form,
            "setting": setting,
            "referral_stats": referral_stats,
            "page_obj": page_obj,
            "rewards": page_obj.object_list,
            "query": query,
            "selected_status": selected_status,
            "selected_payout": selected_payout,
            "status_choices": ReferralReward.Status.choices,
            "payout_choices": ReferralReward.PayoutStatus.choices,
            "reward_trend": _marketing_trend(rewards, "activated_at"),
            "query_string": query_params.urlencode(),
            "user_profile": user_profile,
        },
    )


@login_required
def owner_targets(request):
    user_profile, company, allowed = owner_context(request, module=OPERATIONS_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    form = RoleTargetForm(request.POST or None, company=company, prefix="target")
    if request.method == "POST" and form.is_valid():
        if not can_perform_operations(user_profile, "create"):
            messages.error(request, "You do not have permission to create targets.")
            return redirect("accounts:owner_targets")
        target = form.save(commit=False)
        target.company = company
        target.assigned_by = request.user
        target.save()
        record_audit(actor=request.user, action="operations.target_created", target=target, company=company)
        messages.success(request, "Target saved.")
        return redirect("accounts:owner_targets")
    targets = RoleTarget.objects.filter(company=company).select_related("employee", "assigned_by")
    status = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip()
    if status:
        targets = targets.filter(status=status)
    if query:
        targets = targets.filter(models.Q(title__icontains=query) | models.Q(metric__icontains=query) | models.Q(employee__email__icontains=query))
    return owner_render(request, "accounts/owner_targets.html", {"form": form, "targets": targets, "status_choices": RoleTarget.Status.choices, "selected_status": status, "query": query, "user_profile": user_profile})


@login_required
def owner_target_detail(request, target_id):
    user_profile, company, allowed = owner_context(request, module=OPERATIONS_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    target = get_object_or_404(RoleTarget.objects.select_related("employee", "assigned_by"), company=company, id=target_id)
    if request.method == "POST":
        if not can_perform_operations(user_profile, "update"):
            messages.error(request, "You do not have permission to update targets.")
            return redirect("accounts:owner_target_detail", target_id=target.id)
        target.current_value = int(request.POST.get("current_value") or 0)
        target.status = request.POST.get("status") if request.POST.get("status") in dict(RoleTarget.Status.choices) else target.status
        target.note = request.POST.get("note", "").strip()
        target.is_active = target.status == RoleTarget.Status.ACTIVE
        target.save(update_fields=["current_value", "status", "note", "is_active"])
        record_audit(actor=request.user, action="operations.target_progress_updated", target=target, company=company, details={"current_value": target.current_value, "status": target.status})
        messages.success(request, "Target progress updated.")
        return redirect("accounts:owner_target_detail", target_id=target.id)
    return owner_render(request, "accounts/owner_target_detail.html", {"target": target, "status_choices": RoleTarget.Status.choices, "user_profile": user_profile})


@login_required
def owner_target_edit(request, target_id):
    user_profile, company, allowed = owner_context(request, module=OPERATIONS_MODULE, permission="update")
    if not allowed:
        return redirect("properties:dashboard")
    target = get_object_or_404(RoleTarget, company=company, id=target_id)
    form = RoleTargetForm(request.POST or None, instance=target, company=company, prefix="target")
    if request.method == "POST" and form.is_valid():
        target = form.save()
        record_audit(actor=request.user, action="operations.target_updated", target=target, company=company)
        messages.success(request, "Target updated.")
        return redirect("accounts:owner_target_detail", target_id=target.id)
    return owner_render(request, "accounts/owner_target_form.html", {"form": form, "target": target, "user_profile": user_profile})


@login_required
def owner_target_delete(request, target_id):
    user_profile, company, allowed = owner_context(request, module=OPERATIONS_MODULE, permission="delete")
    if not allowed:
        return redirect("properties:dashboard")
    target = get_object_or_404(RoleTarget, company=company, id=target_id)
    if request.method == "POST":
        record_audit(actor=request.user, action="operations.target_deleted", target=target, company=company)
        target.delete()
        messages.success(request, "Target deleted.")
    return redirect("accounts:owner_targets")


def _set_single_active_popup(company, popup):
    if popup.is_active:
        popup_roles = set(popup.roles or [])
        for existing in SoftwarePopup.objects.filter(company=company, is_active=True).exclude(id=popup.id):
            if popup_roles.intersection(set(existing.roles or [])):
                existing.is_active = False
                existing.save(update_fields=["is_active"])


@login_required
def owner_popups(request):
    user_profile, company, allowed = owner_context(request, module=MARKETING_MODULE)
    if not allowed:
        return redirect("properties:dashboard")
    if request.method == "POST":
        if not can_perform_marketing(user_profile, "update"):
            messages.error(request, "You do not have permission to update popups.")
            return redirect("accounts:owner_popups")
        selected_ids = request.POST.getlist("popup_ids")
        action = request.POST.get("bulk_action", "").strip()
        selected_popups = SoftwarePopup.objects.filter(company=company, id__in=selected_ids)
        if not selected_popups.exists():
            messages.error(request, "Select at least one popup.")
            return redirect("accounts:owner_popups")
        if action == "activate":
            if selected_popups.count() != 1:
                messages.error(request, "Select one popup to activate.")
                return redirect("accounts:owner_popups")
            popup = selected_popups.first()
            popup.is_active = True
            popup.save(update_fields=["is_active"])
            _set_single_active_popup(company, popup)
            record_audit(actor=request.user, action="marketing.popup_activated", target=popup, company=company)
            messages.success(request, "Popup activated. Overlapping role popups were deactivated automatically.")
        elif action == "deactivate":
            updated = selected_popups.update(is_active=False)
            for popup in selected_popups:
                record_audit(actor=request.user, action="marketing.popup_deactivated", target=popup, company=company)
            messages.success(request, f"{updated} popup(s) deactivated.")
        elif action == "delete":
            deleted_count = selected_popups.count()
            for popup in selected_popups:
                record_audit(actor=request.user, action="marketing.popup_deleted", target=popup, company=company)
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
    all_popups = list(popups) if not hasattr(popups, "filter") else list(popups)
    query_params = request.GET.copy()
    query_params.pop("page", None)
    paginator = Paginator(all_popups, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return owner_render(
        request,
        "accounts/owner_popups.html",
        {
            "popups": page_obj.object_list,
            "page_obj": page_obj,
            "popup_stats": {
                "total": len(all_popups),
                "active": sum(1 for popup in all_popups if popup.is_active),
                "impressions": sum(popup.impressions for popup in all_popups),
                "clicks": sum(popup.clicks for popup in all_popups),
                "ctr": _popup_ctr(all_popups),
            },
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
    user_profile, company, allowed = owner_context(request, module=MARKETING_MODULE, permission="create")
    if not allowed:
        return redirect("properties:dashboard")
    form = SoftwarePopupForm(request.POST or None, request.FILES or None, prefix="popup")
    if request.method == "POST" and form.is_valid():
        popup = form.save(commit=False)
        popup.company = company
        popup.save()
        _set_single_active_popup(company, popup)
        record_audit(actor=request.user, action="marketing.popup_created", target=popup, company=company)
        messages.success(request, "Offer popup created.")
        return redirect("accounts:owner_popups")
    return owner_render(
        request,
        "accounts/owner_popup_form.html",
        {"form": form, "popup": None, "mode": "create", "user_profile": user_profile},
    )


@login_required
def owner_popup_detail(request, popup_id):
    user_profile, company, allowed = owner_context(request, module=MARKETING_MODULE)
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
    user_profile, company, allowed = owner_context(request, module=MARKETING_MODULE, permission="update")
    if not allowed:
        return redirect("properties:dashboard")
    popup = get_object_or_404(SoftwarePopup, id=popup_id, company=company)
    form = SoftwarePopupForm(request.POST or None, request.FILES or None, instance=popup, prefix="popup")
    if request.method == "POST" and form.is_valid():
        popup = form.save()
        _set_single_active_popup(company, popup)
        record_audit(actor=request.user, action="marketing.popup_updated", target=popup, company=company)
        messages.success(request, "Offer popup updated.")
        return redirect("accounts:owner_popups")
    return owner_render(
        request,
        "accounts/owner_popup_form.html",
        {"form": form, "popup": popup, "mode": "edit", "user_profile": user_profile},
    )


@login_required
def popup_track(request, popup_id, action):
    popup = get_object_or_404(SoftwarePopup, id=popup_id, company=getattr(request.user.profile, "company", None))
    field = {"impression": "impressions", "click": "clicks", "close": "closes"}.get(action)
    if request.method != "POST" or not field:
        return JsonResponse({"ok": False}, status=400)
    SoftwarePopup.objects.filter(id=popup.id).update(**{field: models.F(field) + 1})
    popup.refresh_from_db(fields=[field])
    return JsonResponse({"ok": True, field: getattr(popup, field)})
