from django.contrib import admin
from .models import (
    AchievementCounter,
    FAQ,
    Enquiry,
    GalleryItem,
    HeroBanner,
    Project,
    ProjectImage,
    PropertyCategory,
    PropertyImage,
    PropertyListing,
    PropertySubmission,
    Service,
    SiteSettings,
    SiteVisitRequest,
    TeamMember,
    Testimonial,
    WhyChooseUs,
)

admin.site.site_header = "Siya Real Build Website Superadmin"
admin.site.site_title = "Siya Website CMS"
admin.site.index_title = "Website Content & Lead Management"


class ProjectImageInline(admin.TabularInline):
    model = ProjectImage
    extra = 1


class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 1


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Brand", {"fields": ("company_name", "tagline", "logo", "favicon")}),
        (
            "About",
            {
                "fields": (
                    "about_eyebrow",
                    "about_title",
                    "about_text",
                    "about_image",
                    "about_banner_image",
                    "about_button_label",
                )
            },
        ),
        (
            "About page story",
            {"fields": ("about_story_title", "about_story_text", "about_story_image")},
        ),
        (
            "Mission, Vision & Values",
            {
                "fields": (
                    "mission_title",
                    "mission_text",
                    "mission_image",
                    "vision_title",
                    "vision_text",
                    "vision_image",
                    "values_title",
                    "values_text",
                    "values_image",
                )
            },
        ),
        (
            "Founder messages",
            {
                "fields": (
                    "founder_name",
                    "founder_designation",
                    "founder_message",
                    "founder_image",
                    "second_founder_name",
                    "second_founder_designation",
                    "second_founder_message",
                    "second_founder_image",
                )
            },
        ),
        (
            "Homepage sections",
            {
                "fields": (
                    "services_eyebrow",
                    "services_title",
                    "properties_eyebrow",
                    "properties_title",
                    "why_choose_eyebrow",
                    "why_choose_title",
                    "why_choose_text",
                    "contact_eyebrow",
                    "contact_title",
                    "contact_text",
                )
            },
        ),
        ("Properties page", {"fields": ("properties_banner_image",)}),
        ("Services page", {"fields": ("services_banner_image",)}),
        ("Team page", {"fields": ("team_banner_image",)}),
        ("Gallery page", {"fields": ("gallery_banner_image",)}),
        (
            "Contact page",
            {"fields": ("contact_banner_image", "office_map_url", "business_hours")},
        ),
        ("Post Property page", {"fields": ("post_property_banner_image",)}),
        (
            "Header actions",
            {
                "fields": (
                    "post_property_label",
                    "portal_login_label",
                    "portal_login_url",
                )
            },
        ),
        (
            "Footer content",
            {
                "fields": (
                    "footer_explore_title",
                    "footer_property_types_title",
                    "footer_contact_title",
                    "footer_whatsapp_eyebrow",
                    "footer_whatsapp_title",
                    "footer_whatsapp_text",
                    "footer_whatsapp_button",
                    "footer_credit_text",
                    "footer_credit_name",
                    "footer_credit_url",
                )
            },
        ),
        ("Contact", {"fields": ("phone", "whatsapp_number", "email", "address")}),
        ("Social", {"fields": ("facebook_url", "instagram_url", "youtube_url")}),
        ("SEO", {"fields": ("seo_title", "seo_description")}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(
    HeroBanner,
    Service,
    WhyChooseUs,
    AchievementCounter,
    Testimonial,
    TeamMember,
    GalleryItem,
    FAQ,
)
class OrderedContentAdmin(admin.ModelAdmin):
    list_display = ("__str__", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    list_filter = ("is_active",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "location",
        "status",
        "is_featured",
        "is_active",
        "sort_order",
    )
    list_editable = ("is_featured", "is_active", "sort_order")
    list_filter = ("status", "is_featured", "is_active")
    search_fields = ("name", "location", "summary")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProjectImageInline]


@admin.register(PropertyListing)
class PropertyListingAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "location",
        "price",
        "is_featured",
        "is_active",
    )
    list_editable = ("is_featured", "is_active")
    list_filter = ("category", "is_featured", "is_active", "project")
    search_fields = ("title", "location", "summary")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [PropertyImageInline]


@admin.register(PropertyCategory)
class PropertyCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "icon", "sort_order", "is_active")
    list_editable = ("icon", "sort_order", "is_active")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "interest", "property", "status", "created_at")
    list_editable = ("status",)
    list_filter = ("status", "created_at")
    search_fields = ("name", "phone", "email", "message")
    readonly_fields = ("created_at",)


@admin.register(SiteVisitRequest)
class SiteVisitRequestAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "phone",
        "property",
        "preferred_date",
        "is_confirmed",
        "created_at",
    )
    list_editable = ("is_confirmed",)
    list_filter = ("is_confirmed", "preferred_date")
    search_fields = ("name", "phone", "email")
    readonly_fields = ("created_at",)


@admin.register(PropertySubmission)
class PropertySubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "property_title",
        "owner_name",
        "phone",
        "category",
        "location",
        "status",
        "created_at",
    )
    list_editable = ("status",)
    list_filter = ("status", "category", "created_at")
    search_fields = ("property_title", "owner_name", "phone", "email", "location")
    readonly_fields = ("created_at",)
