from django.contrib import admin

from .models import (
    AuthenticationSupportRequest,
    AuditLog,
    CompanyEvent,
    CompanyProfile,
    DesignationCodeRule,
    EmailOTP,
    EmployeeEmailChangeRequest,
    EmployeeRoleChangeRequest,
    EmployeeInvite,
    Meeting,
    NotificationDelivery,
    OfficeLocation,
    ReferralReward,
    ReferralSetting,
    RoleMatrixRule,
    RoleTarget,
    SignupRequest,
    SignupRequestStatus,
    SoftwarePopup,
    TeamEmailMessage,
    UserProfile,
    EmployeeProfileChange,
)

admin.site.register(AuditLog)
admin.site.register(NotificationDelivery)
admin.site.register(OfficeLocation)
admin.site.register(EmployeeProfileChange)


@admin.register(SignupRequest)
class SignupRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "approved_role", "status", "is_email_verified", "created_at")
    list_filter = ("status", "approved_role", "is_email_verified", "created_at")
    search_fields = ("name", "phone", "email", "channel_partner_reference")
    readonly_fields = ("user", "is_email_verified", "created_at", "updated_at")
    actions = ("approve_requests", "reject_requests")
    fieldsets = (
        ("Signup Details", {"fields": ("name", "phone", "email", "channel_partner_reference")}),
        ("Admin Approval", {"fields": ("status", "approved_role", "admin_note", "user")}),
        ("Verification", {"fields": ("is_email_verified", "created_at", "updated_at")}),
    )

    @admin.action(description="Approve selected signup requests")
    def approve_requests(self, request, queryset):
        approved = 0
        for signup in queryset.filter(is_email_verified=True).exclude(approved_role=""):
            signup.approve()
            approved += 1
        self.message_user(request, f"{approved} signup request(s) approved.")

    @admin.action(description="Reject selected signup requests")
    def reject_requests(self, request, queryset):
        rejected = 0
        for signup in queryset.exclude(status=SignupRequestStatus.APPROVED):
            signup.reject()
            rejected += 1
        self.message_user(request, f"{rejected} signup request(s) rejected.")

    def save_model(self, request, obj, form, change):
        if obj.status == SignupRequestStatus.APPROVED:
            obj.approve()
            return
        if obj.status == SignupRequestStatus.REJECTED:
            obj.reject()
            return
        super().save_model(request, obj, form, change)


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("email", "attempts", "is_used", "signup_request", "expires_at", "created_at")
    list_filter = ("is_used", "created_at")
    search_fields = ("email",)


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "website", "gst_number", "rera_number", "city", "state", "updated_at")
    search_fields = ("name", "phone", "phone_2", "phone_3", "email", "email_2", "email_3", "city")
    fieldsets = (
        ("Branding", {"fields": ("logo", "name", "tagline", "description")}),
        ("Contact Details", {"fields": ("phone", "phone_2", "phone_3", "email", "email_2", "email_3", "website")}),
        ("Registration Details", {"fields": ("gst_number", "rera_number", "cin_number", "pan_number")}),
        ("Banking", {"fields": ("bank_name", "bank_account_name", "bank_account_number", "bank_ifsc", "upi_id")}),
        ("Schedule", {"fields": ("opening_time", "closing_time", "weekly_off_days", "holiday_notes")}),
        ("Address", {"fields": ("address", "city", "state", "pincode")}),
    )

    def has_add_permission(self, request):
        return request.user.is_superuser and not CompanyProfile.objects.exists()

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "phone", "designation", "employee_code", "department", "updated_at")
    list_filter = ("role", "company", "gender", "marital_status")
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "phone",
        "employee_code",
        "designation",
        "department",
        "pan_number",
        "aadhaar_number",
    )
    fieldsets = (
        ("Access", {"fields": ("user", "company", "role", "employee_code")}),
        ("Basic", {"fields": ("profile_image", "phone", "designation", "date_of_birth", "gender", "blood_group", "marital_status", "personal_email")}),
        ("Aadhaar & PAN", {"fields": ("aadhaar_number", "aadhaar_document", "pan_number", "pan_document")}),
        ("Work Details", {"fields": ("department", "reporting_manager", "joining_date", "work_location", "territory", "channel_partner_reference")}),
        ("Salary Bank Details", {"fields": ("bank_name", "bank_account_name", "bank_account_number", "bank_ifsc")}),
        ("Emergency & Address", {"fields": ("emergency_contact_name", "emergency_contact_phone", "address", "city", "state", "pincode")}),
    )


@admin.register(EmployeeInvite)
class EmployeeInviteAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "company", "role", "employee_code", "status", "is_email_verified", "invited_by", "approved_by", "approved_at", "created_at")
    list_filter = ("role", "status", "is_email_verified", "company", "created_at")
    search_fields = ("name", "email", "phone", "employee_code")
    readonly_fields = ("approved_by", "approved_at", "last_invite_sent_at", "resend_count", "accepted_user")


@admin.register(AuthenticationSupportRequest)
class AuthenticationSupportRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "contact", "is_resolved", "created_at")
    list_filter = ("is_resolved", "created_at")
    search_fields = ("name", "contact", "issue", "page_url")
    readonly_fields = ("name", "contact", "issue", "page_url", "created_at")
    fieldsets = (
        ("Request Details", {"fields": ("name", "contact", "issue", "page_url")}),
        ("Status", {"fields": ("is_resolved", "created_at")}),
    )


@admin.register(TeamEmailMessage)
class TeamEmailMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "company", "sent_by", "role", "department", "sent_count", "created_at")
    list_filter = ("company", "role", "department", "created_at")
    search_fields = ("subject", "message", "sent_by__email", "sent_by__first_name", "sent_by__last_name")
    readonly_fields = ("company", "sent_by", "role", "department", "subject", "message", "recipients", "sent_count", "created_at")
    date_hierarchy = "created_at"


@admin.register(DesignationCodeRule)
class DesignationCodeRuleAdmin(admin.ModelAdmin):
    list_display = ("designation", "role", "company", "prefix", "next_number", "is_active")
    list_filter = ("company", "role", "is_active")
    search_fields = ("designation", "prefix", "company__name")


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "created_by", "audience_type", "starts_at", "ends_at", "is_active")
    list_filter = ("company", "audience_type", "is_active", "starts_at")
    search_fields = ("title", "description", "location", "meeting_link", "created_by__email")
    filter_horizontal = ("employees",)
    date_hierarchy = "starts_at"


@admin.register(CompanyEvent)
class CompanyEventAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "created_by", "starts_at", "ends_at", "is_global", "show_as_popup", "is_active")
    list_filter = ("company", "is_global", "show_as_popup", "is_active", "starts_at")
    search_fields = ("title", "caption", "description", "created_by__email")
    date_hierarchy = "starts_at"


@admin.register(ReferralSetting)
class ReferralSettingAdmin(admin.ModelAdmin):
    list_display = ("company", "is_active", "referrer_reward_amount", "referrer_coupon_code", "referred_reward_amount", "referred_coupon_code", "updated_at")
    list_filter = ("is_active", "updated_at")
    search_fields = ("company__name", "referrer_coupon_code", "referred_coupon_code", "coupon_code", "terms")


@admin.register(ReferralReward)
class ReferralRewardAdmin(admin.ModelAdmin):
    list_display = ("referral_code", "referrer", "referred_user", "company", "referrer_reward_amount", "referrer_coupon_code", "referred_reward_amount", "referred_coupon_code", "status", "activated_at")
    list_filter = ("company", "status", "activated_at")
    search_fields = ("referral_code", "referrer__email", "referrer__first_name", "referred_user__email", "referred_user__first_name", "referrer_coupon_code", "referred_coupon_code", "coupon_code")
    readonly_fields = ("company", "setting", "signup_request", "referrer", "referred_user", "referral_code", "referrer_reward_amount", "referrer_coupon_code", "referred_reward_amount", "referred_coupon_code", "coupon_code", "activated_at", "created_at")
    date_hierarchy = "activated_at"


@admin.register(RoleTarget)
class RoleTargetAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "assigned_by", "role", "employee", "target_value", "metric", "starts_on", "ends_on", "is_active")
    list_filter = ("company", "role", "metric", "is_active", "starts_on", "ends_on")
    search_fields = ("title", "metric", "employee__email", "employee__first_name", "employee__last_name", "assigned_by__email")
    date_hierarchy = "starts_on"


@admin.register(SoftwarePopup)
class SoftwarePopupAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "deal_label", "starts_at", "ends_at", "is_active", "created_at")
    list_filter = ("company", "is_active", "starts_at", "ends_at", "created_at")
    search_fields = ("title", "message", "deal_label")
    date_hierarchy = "created_at"


@admin.register(RoleMatrixRule)
class RoleMatrixRuleAdmin(admin.ModelAdmin):
    list_display = ("company", "role", "module", "can_view", "can_create", "can_update", "can_delete")
    list_filter = ("company", "role", "module", "can_view", "can_create", "can_update", "can_delete")
    search_fields = ("company__name", "module")


@admin.register(EmployeeEmailChangeRequest)
class EmployeeEmailChangeRequestAdmin(admin.ModelAdmin):
    list_display = ("employee", "company", "requested_email", "status", "is_email_verified", "requested_by", "approved_by", "created_at")
    list_filter = ("company", "status", "is_email_verified", "created_at", "approved_at")
    search_fields = ("employee__email", "employee__first_name", "employee__last_name", "requested_email", "reason")
    readonly_fields = ("verified_at", "approved_at", "created_at", "updated_at")
    date_hierarchy = "created_at"


@admin.register(EmployeeRoleChangeRequest)
class EmployeeRoleChangeRequestAdmin(admin.ModelAdmin):
    list_display = ("employee", "company", "current_role", "requested_role", "status", "requested_by", "reviewed_by", "created_at")
    list_filter = ("company", "current_role", "requested_role", "status", "created_at", "reviewed_at")
    search_fields = ("employee__email", "employee__first_name", "employee__last_name", "reason", "review_note")
    readonly_fields = ("reviewed_at", "created_at", "updated_at")
    date_hierarchy = "created_at"
