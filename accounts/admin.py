from django.contrib import admin

from .models import CompanyProfile, EmailOTP, EmployeeInvite, SignupRequest, SignupRequestStatus, UserProfile


@admin.register(SignupRequest)
class SignupRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "requested_role", "approved_role", "status", "is_email_verified", "created_at")
    list_filter = ("status", "requested_role", "approved_role", "is_email_verified", "created_at")
    search_fields = ("name", "phone", "email", "channel_partner_reference")
    readonly_fields = ("user", "is_email_verified", "created_at", "updated_at")
    actions = ("approve_requests", "reject_requests")
    fieldsets = (
        ("Signup Details", {"fields": ("name", "phone", "email", "requested_role", "channel_partner_reference")}),
        ("Admin Approval", {"fields": ("status", "approved_role", "admin_note", "user")}),
        ("Verification", {"fields": ("is_email_verified", "created_at", "updated_at")}),
    )

    @admin.action(description="Approve selected signup requests")
    def approve_requests(self, request, queryset):
        approved = 0
        for signup in queryset.filter(is_email_verified=True):
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
    list_display = ("email", "code", "attempts", "is_used", "signup_request", "expires_at", "created_at")
    list_filter = ("is_used", "created_at")
    search_fields = ("email",)


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "phone", "email", "city", "state", "updated_at")
    search_fields = ("name", "owner__email", "phone", "email", "city")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "phone", "designation", "employee_code", "updated_at")
    list_filter = ("role", "company")
    search_fields = ("user__email", "user__first_name", "user__last_name", "phone", "employee_code")


@admin.register(EmployeeInvite)
class EmployeeInviteAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "company", "role", "employee_code", "invited_by", "created_at")
    list_filter = ("role", "company", "created_at")
    search_fields = ("name", "email", "phone", "employee_code")

# Register your models here.
