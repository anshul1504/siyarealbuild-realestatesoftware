from django.contrib import admin

from .models import BookingAgreement, BookingInstallment, BookingPayment, ColonyPlot, MISReportSnapshot, PlotBooking, PlotQuotation, PlotStatusHistory, Property, PropertyCommissionPayout, PropertyCommissionRule, PropertyDeveloper, PropertyDocument, PropertyPhoto, PropertyVisit


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
    fields = ("plot", "client_name", "assigned_employee", "image", "visit_at", "status", "outcome")


class PropertyCommissionRuleInline(admin.TabularInline):
    model = PropertyCommissionRule
    extra = 1
    fields = ("role", "calculation_type", "value", "note", "is_active")


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("title", "city", "category", "listing_for", "price", "status", "developer", "owner", "assigned_to", "created_at")
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
    inlines = (PropertyPhotoInline, PropertyDocumentInline, PropertyCommissionRuleInline, ColonyPlotInline, PropertyVisitInline)
    date_hierarchy = "created_at"


@admin.register(PropertyPhoto)
class PropertyPhotoAdmin(admin.ModelAdmin):
    list_display = ("property", "caption", "is_primary", "uploaded_at")
    list_filter = ("is_primary", "uploaded_at")
    search_fields = ("property__title", "caption")


@admin.register(PropertyDocument)
class PropertyDocumentAdmin(admin.ModelAdmin):
    list_display = ("property", "document_type", "title", "document_number", "review_status", "expires_on", "uploaded_at")
    list_filter = ("document_type", "review_status", "expires_on", "uploaded_at")
    search_fields = ("property__title", "title", "document_number", "review_note")


@admin.register(ColonyPlot)
class ColonyPlotAdmin(admin.ModelAdmin):
    list_display = ("property", "plot_number", "plot_category", "block", "area_sqft", "base_rate", "plc_rate", "price", "status")
    list_filter = ("status", "plot_category", "facing", "is_corner", "is_garden_facing", "is_main_road")
    search_fields = ("property__title", "plot_number", "notes")


@admin.register(PropertyDeveloper)
class PropertyDeveloperAdmin(admin.ModelAdmin):
    list_display = ("name", "company_name", "company", "mobile", "email", "is_active")
    list_filter = ("is_active", "company")
    search_fields = ("name", "company_name", "contact_person", "mobile", "email")


@admin.register(PropertyCommissionRule)
class PropertyCommissionRuleAdmin(admin.ModelAdmin):
    list_display = ("property", "role", "calculation_type", "value", "is_active")
    list_filter = ("role", "calculation_type", "is_active")
    search_fields = ("property__title", "note")


@admin.register(PropertyCommissionPayout)
class PropertyCommissionPayoutAdmin(admin.ModelAdmin):
    list_display = ("booking", "role", "amount", "status", "paid_by", "paid_at", "updated_at")
    list_filter = ("status", "role", "paid_at")
    search_fields = ("booking__client_name", "booking__plot__plot_number", "payout_reference", "note")
    readonly_fields = ("booking", "role", "calculation_type", "rule_value", "amount", "generated_by", "created_at", "updated_at")


@admin.register(PlotStatusHistory)
class PlotStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("plot", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status", "created_at")


@admin.register(PlotQuotation)
class PlotQuotationAdmin(admin.ModelAdmin):
    list_display = ("plot", "client_name", "total_amount", "status", "valid_until", "created_by", "created_at")
    list_filter = ("status", "valid_until")
    search_fields = ("plot__plot_number", "plot__property__title", "client_name", "client_phone", "client_email")


@admin.register(PlotBooking)
class PlotBookingAdmin(admin.ModelAdmin):
    list_display = ("plot", "client_name", "booking_date", "booking_amount", "total_deal_value", "paid_amount", "balance_amount", "status", "created_by")
    list_filter = ("status", "booking_date")
    search_fields = ("plot__plot_number", "plot__property__title", "client_name", "client_phone", "client_email")


@admin.register(BookingInstallment)
class BookingInstallmentAdmin(admin.ModelAdmin):
    list_display = ("booking", "title", "due_date", "amount", "paid_amount", "status")
    list_filter = ("status", "due_date")
    search_fields = ("booking__client_name", "booking__plot__plot_number", "title")


@admin.register(BookingPayment)
class BookingPaymentAdmin(admin.ModelAdmin):
    list_display = ("booking", "installment", "received_on", "amount", "mode", "reference_number", "received_by")
    list_filter = ("mode", "received_on")
    search_fields = ("booking__client_name", "booking__plot__plot_number", "reference_number")


@admin.register(BookingAgreement)
class BookingAgreementAdmin(admin.ModelAdmin):
    list_display = ("booking", "agreement_type", "title", "status", "agreement_number", "prepared_on", "signed_on", "registered_on")
    list_filter = ("agreement_type", "status", "prepared_on", "signed_on", "registered_on")
    search_fields = ("booking__client_name", "booking__plot__plot_number", "title", "agreement_number", "stamp_number")


@admin.register(MISReportSnapshot)
class MISReportSnapshotAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "report_type", "period_start", "period_end", "generated_by", "created_at")
    list_filter = ("report_type", "period_start", "period_end", "created_at")
    search_fields = ("title", "company__name", "generated_by__email")


@admin.register(PropertyVisit)
class PropertyVisitAdmin(admin.ModelAdmin):
    list_display = ("property", "plot", "client_name", "assigned_employee", "visit_at", "status", "outcome", "image")
    list_filter = ("status", "outcome", "visit_at")
    search_fields = ("property__title", "plot__plot_number", "client_name", "client_phone", "assigned_employee__email")
    date_hierarchy = "visit_at"
