from django.contrib import admin

from .models import ColonyPlot, Property, PropertyDocument, PropertyPhoto, PropertyVisit


class PropertyPhotoInline(admin.TabularInline):
    model = PropertyPhoto
    extra = 1


class PropertyDocumentInline(admin.TabularInline):
    model = PropertyDocument
    extra = 1


class ColonyPlotInline(admin.TabularInline):
    model = ColonyPlot
    extra = 1


class PropertyVisitInline(admin.TabularInline):
    model = PropertyVisit
    extra = 0
    fields = ("plot", "client_name", "assigned_employee", "visit_at", "status", "outcome")


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("title", "city", "category", "listing_for", "price", "status", "owner", "created_at")
    list_filter = ("status", "category", "listing_for", "city", "legal_status")
    search_fields = (
        "title",
        "city",
        "locality",
        "address",
        "rera_number",
        "tcp_approval_number",
        "khasra_number",
        "amenities",
        "plc_rules",
        "nearby_residential",
        "nearby_commercial",
        "nearby_landmarks",
    )
    inlines = (PropertyPhotoInline, PropertyDocumentInline, ColonyPlotInline, PropertyVisitInline)
    date_hierarchy = "created_at"


@admin.register(PropertyPhoto)
class PropertyPhotoAdmin(admin.ModelAdmin):
    list_display = ("property", "caption", "is_primary", "uploaded_at")
    list_filter = ("is_primary", "uploaded_at")
    search_fields = ("property__title", "caption")


@admin.register(PropertyDocument)
class PropertyDocumentAdmin(admin.ModelAdmin):
    list_display = ("property", "document_type", "title", "uploaded_at")
    list_filter = ("document_type", "uploaded_at")
    search_fields = ("property__title", "title")


@admin.register(ColonyPlot)
class ColonyPlotAdmin(admin.ModelAdmin):
    list_display = ("property", "plot_number", "area_sqft", "facing", "price", "status")
    list_filter = ("status", "facing")
    search_fields = ("property__title", "plot_number", "notes")


@admin.register(PropertyVisit)
class PropertyVisitAdmin(admin.ModelAdmin):
    list_display = ("property", "plot", "client_name", "assigned_employee", "visit_at", "status", "outcome")
    list_filter = ("status", "outcome", "visit_at")
    search_fields = ("property__title", "plot__plot_number", "client_name", "client_phone", "assigned_employee__email")
    date_hierarchy = "visit_at"
