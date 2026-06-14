from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from accounts.models import Role


class PropertyDeveloper(models.Model):
    company = models.ForeignKey("accounts.CompanyProfile", on_delete=models.CASCADE, related_name="property_developers")
    name = models.CharField(max_length=160)
    company_name = models.CharField(max_length=180, blank=True)
    contact_person = models.CharField(max_length=140, blank=True)
    mobile = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    office_address = models.CharField(max_length=260, blank=True)
    rera_number = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("company", "name")

    def __str__(self):
        return self.company_name or self.name


class Property(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        HOLD = "hold", "Hold"
        NEGOTIATION = "negotiation", "Negotiation"
        SOLD = "sold", "Sold"
        RENTED = "rented", "Rented"

    class ListingFor(models.TextChoices):
        SALE = "sale", "Sale"
        RENT = "rent", "Rent"
        LEASE = "lease", "Lease"

    class Category(models.TextChoices):
        COLONY = "colony", "Colony"
        PLOT = "plot", "Plot"
        RESALE_PLOT = "resale_plot", "Resale Plot"
        FLAT = "flat", "Flat"
        RESIDENTIAL_HOUSE = "residential_house", "Residential House"
        COMMERCIAL_SHOP = "commercial_shop", "Commercial Shop"
        ROW_HOUSE = "row_house", "Row House"
        VILLA = "villa", "Villa"
        FARM_HOUSE = "farm_house", "Farm House"
        OFFICE = "office", "Office"
        WAREHOUSE = "warehouse", "Warehouse"
        AGRICULTURAL_LAND = "agricultural_land", "Agricultural Land"

    class LegalStatus(models.TextChoices):
        CLEAR = "clear", "Clear"
        UNDER_REVIEW = "under_review", "Under Review"
        DISPUTED = "disputed", "Disputed"
        MORTGAGED = "mortgaged", "Mortgaged"

    class DevelopmentStatus(models.TextChoices):
        PRE_LAUNCH = "pre_launch", "Pre Launch"
        LAUNCHED = "launched", "Launched"
        UNDER_DEVELOPMENT = "under_development", "Under Development"
        DEVELOPED = "developed", "Developed"
        READY_POSSESSION = "ready_possession", "Ready Possession"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="properties")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_properties")
    developer = models.ForeignKey(PropertyDeveloper, on_delete=models.SET_NULL, null=True, blank=True, related_name="properties")
    title = models.CharField(max_length=160)
    category = models.CharField(max_length=40, choices=Category.choices, default=Category.PLOT)
    property_type = models.CharField(max_length=40, choices=Category.choices, default=Category.PLOT)
    listing_for = models.CharField(max_length=20, choices=ListingFor.choices, default=ListingFor.SALE)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.AVAILABLE)

    city = models.CharField(max_length=80)
    locality = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=260)
    landmark = models.CharField(max_length=160, blank=True)
    map_link = models.URLField(blank=True)

    price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    price_per_sqft = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    area_sqft = models.PositiveIntegerField(default=0)
    carpet_area_sqft = models.PositiveIntegerField(default=0)
    builtup_area_sqft = models.PositiveIntegerField(default=0)
    length_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    width_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    facing = models.CharField(max_length=40, blank=True)
    road_width_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    bedrooms = models.PositiveSmallIntegerField(default=0)
    bathrooms = models.PositiveSmallIntegerField(default=0)
    balconies = models.PositiveSmallIntegerField(default=0)
    floor_number = models.PositiveSmallIntegerField(null=True, blank=True)
    total_floors = models.PositiveSmallIntegerField(null=True, blank=True)
    parking_count = models.PositiveSmallIntegerField(default=0)
    furnishing = models.CharField(max_length=80, blank=True)
    construction_status = models.CharField(max_length=80, blank=True)
    possession_status = models.CharField(max_length=80, blank=True)

    colony_name = models.CharField(max_length=160, blank=True)
    development_name = models.CharField(max_length=160, blank=True)
    total_plots = models.PositiveIntegerField(default=0)
    available_plots = models.PositiveIntegerField(default=0)
    development_status = models.CharField(max_length=120, choices=DevelopmentStatus.choices, blank=True)
    amenities = models.TextField(blank=True)
    selected_amenities = models.JSONField(default=list, blank=True)
    custom_amenities = models.TextField(blank=True)
    amenity_count = models.PositiveIntegerField(default=0)
    garden_count = models.PositiveIntegerField(default=0)
    corner_plot_count = models.PositiveIntegerField(default=0)
    garden_facing_plot_count = models.PositiveIntegerField(default=0)
    plc_rules = models.TextField(blank=True)
    nearby_residential = models.TextField(blank=True)
    nearby_commercial = models.TextField(blank=True)
    nearby_connectivity = models.TextField(blank=True)
    nearby_education = models.TextField(blank=True)
    nearby_healthcare = models.TextField(blank=True)
    nearby_landmarks = models.TextField(blank=True)
    base_rate_per_sqft = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    residential_rate_per_sqft = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    commercial_rate_per_sqft = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    lig_rate_per_sqft = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    mig_rate_per_sqft = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    hig_rate_per_sqft = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    ews_rate_per_sqft = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    electricity_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    maintenance_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    development_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    registry_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    corner_plc_rate = models.DecimalField("Corner PLC (%)", max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    garden_facing_plc_rate = models.DecimalField("Garden facing PLC (%)", max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    main_road_plc_rate = models.DecimalField("Main road PLC (%)", max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    wide_road_plc_rate = models.DecimalField("Wide road PLC (%)", max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])

    rera_number = models.CharField(max_length=80, blank=True)
    tcp_approval_number = models.CharField(max_length=80, blank=True)
    registry_status = models.CharField(max_length=120, blank=True)
    khasra_number = models.CharField(max_length=120, blank=True)
    legal_status = models.CharField(max_length=30, choices=LegalStatus.choices, blank=True)
    legal_notes = models.TextField(blank=True)

    contact_name = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    video_link = models.URLField(blank=True)
    video_links = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    lead_count = models.PositiveIntegerField(default=0)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="archived_properties")
    archive_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.property_type = self.category
        if self.total_plots and not self.available_plots:
            self.available_plots = self.total_plots
        super().save(*args, **kwargs)


class PropertyStatusHistory(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=30, choices=Property.Status.choices, blank=True)
    to_status = models.CharField(max_length=30, choices=Property.Status.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PropertyCommissionRule(models.Model):
    class CalculationType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        PER_SQFT = "per_sqft", "Per sqft"
        FIXED_AMOUNT = "fixed_amount", "Fixed amount"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="commission_rules")
    role = models.CharField(max_length=40, choices=Role.choices)
    calculation_type = models.CharField(max_length=30, choices=CalculationType.choices, default=CalculationType.PERCENTAGE)
    value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = models.CharField(max_length=220, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["role"]
        unique_together = ("property", "role")

    def __str__(self):
        return f"{self.property} - {self.get_role_display()} commission"


class PropertyPhoto(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="properties/photos/")
    caption = models.CharField(max_length=160, blank=True)
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "id"]

    def __str__(self):
        return f"Photo - {self.property}"


class PropertyDocument(models.Model):
    class DocumentType(models.TextChoices):
        RERA = "rera", "RERA"
        TCP = "tcp", "T&CP"
        REGISTRY = "registry", "Registry"
        MAP = "map", "Map / Layout"
        LEGAL = "legal", "Legal Document"
        OTHER = "other", "Other"

    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending Review"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=30, choices=DocumentType.choices, default=DocumentType.OTHER)
    title = models.CharField(max_length=160, blank=True)
    file = models.FileField(upload_to="properties/documents/")
    document_number = models.CharField(max_length=120, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_property_documents")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document_type", "review_status", "id"]

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.property}"


class ColonyPlot(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        HOLD = "hold", "Hold"
        SOLD = "sold", "Sold"
        RESERVED = "reserved", "Reserved"
        BOOKED = "booked", "Booked"
        CANCELLED = "cancelled", "Cancelled"

    class PlotCategory(models.TextChoices):
        RESIDENTIAL = "residential", "Residential"
        COMMERCIAL = "commercial", "Commercial"
        LIG = "lig", "LIG"
        MIG = "mig", "MIG"
        HIG = "hig", "HIG"
        EWS = "ews", "EWS"
        PREMIUM = "premium", "Premium"
        CUSTOM = "custom", "Custom"

    class Facing(models.TextChoices):
        EAST = "east", "East"
        WEST = "west", "West"
        NORTH = "north", "North"
        SOUTH = "south", "South"
        NORTH_EAST = "north_east", "North East"
        NORTH_WEST = "north_west", "North West"
        SOUTH_EAST = "south_east", "South East"
        SOUTH_WEST = "south_west", "South West"
        PARK_FACING = "park_facing", "Park Facing"
        GARDEN_FACING = "garden_facing", "Garden Facing"
        MAIN_ROAD = "main_road", "Main Road"
        CORNER = "corner", "Corner"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="plots")
    plot_number = models.CharField(max_length=40)
    plot_category = models.CharField(max_length=30, choices=PlotCategory.choices, default=PlotCategory.RESIDENTIAL)
    custom_category = models.CharField(max_length=80, blank=True)
    block = models.CharField(max_length=60, blank=True)
    area_sqft = models.PositiveIntegerField(default=0)
    length_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    width_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    facing = models.CharField(max_length=40, choices=Facing.choices, blank=True)
    road_width_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    base_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    plc_rate = models.DecimalField("PLC (%)", max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    extra_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_corner = models.BooleanField(default=False)
    is_garden_facing = models.BooleanField(default=False)
    is_main_road = models.BooleanField(default=False)
    is_wide_road = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    notes = models.CharField(max_length=220, blank=True)

    class Meta:
        ordering = ["plot_number"]
        unique_together = ("property", "plot_number")

    def __str__(self):
        return f"{self.property} - Plot {self.plot_number}"

    def save(self, *args, **kwargs):
        if self.area_sqft and (self.base_rate or self.plc_rate or self.extra_charges):
            base_amount = self.area_sqft * self.base_rate
            self.price = base_amount + (base_amount * self.plc_rate / 100) + self.extra_charges
        super().save(*args, **kwargs)


class PlotStatusHistory(models.Model):
    plot = models.ForeignKey(ColonyPlot, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=20, choices=ColonyPlot.Status.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=ColonyPlot.Status.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PlotQuotation(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"

    plot = models.ForeignKey(ColonyPlot, on_delete=models.CASCADE, related_name="quotations")
    client_name = models.CharField(max_length=140)
    client_phone = models.CharField(max_length=20, blank=True)
    client_email = models.EmailField(blank=True)
    plot_area_sqft = models.PositiveIntegerField(default=0)
    plot_length_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    plot_width_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    plot_facing = models.CharField(max_length=80, blank=True)
    base_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    plc_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    charges_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valid_until = models.DateField(null=True, blank=True)
    terms = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.total_amount = (self.base_amount or 0) + (self.plc_amount or 0) + (self.charges_amount or 0) - (self.discount_amount or 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Quotation #{self.id or 'new'} - {self.client_name}"


class PlotBooking(models.Model):
    class GovernmentIdType(models.TextChoices):
        AADHAAR = "aadhaar", "Aadhaar Card"
        PAN = "pan", "PAN Card"
        PASSPORT = "passport", "Passport"
        DRIVING_LICENSE = "driving_license", "Driving License"
        VOTER_ID = "voter_id", "Voter ID"
        OTHER = "other", "Other Government ID"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Booking Requested"
        DRAFT = "draft", "Draft"
        BOOKED = "booked", "Booked"
        CANCELLED = "cancelled", "Cancelled"
        CONVERTED = "converted", "Converted to Sale"

    plot = models.ForeignKey(ColonyPlot, on_delete=models.CASCADE, related_name="bookings")
    quotation = models.ForeignKey(PlotQuotation, on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings")
    client_name = models.CharField(max_length=140)
    client_phone = models.CharField(max_length=20, blank=True)
    client_email = models.EmailField(blank=True)
    client_address = models.TextField(blank=True)
    government_id_type = models.CharField(max_length=30, choices=GovernmentIdType.choices, blank=True)
    government_id_number = models.CharField(max_length=80, blank=True)
    government_id_document = models.FileField(upload_to="properties/booking-govt-ids/", blank=True)
    plot_area_sqft = models.PositiveIntegerField(default=0)
    plot_length_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    plot_width_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    plot_facing = models.CharField(max_length=80, blank=True)
    booking_date = models.DateField()
    booking_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    agreed_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    coupon_code = models.CharField(max_length=60, blank=True)
    coupon_discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    plc_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    charges_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    commission_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    commission_snapshot = models.JSONField(default=list, blank=True)
    total_deal_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    balance_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_mode = models.CharField(max_length=80, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True)
    payment_proof = models.ImageField(upload_to="properties/booking-proofs/", blank=True)
    discount_reason = models.CharField(max_length=220, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BOOKED)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_plot_bookings")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_plot_bookings")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-booking_date", "-created_at"]

    def save(self, *args, **kwargs):
        if self.plot_id and self.agreed_rate:
            self.total_deal_value = (
                ((self.plot_area_sqft or self.plot.area_sqft) * self.agreed_rate)
                + (self.plc_amount or 0)
                + (self.charges_amount or 0)
                - (self.discount_amount or 0)
                - (self.coupon_discount_amount or 0)
            )
        self.balance_amount = max((self.total_deal_value or 0) - (self.paid_amount or 0), 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Booking #{self.id or 'new'} - {self.client_name}"

    @property
    def payment_progress_percent(self):
        if not self.total_deal_value:
            return 0
        return min(100, int((self.paid_amount / self.total_deal_value) * 100))


class PropertyCommissionPayout(models.Model):
    class Status(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"
        HOLD = "hold", "On Hold"
        CANCELLED = "cancelled", "Cancelled"

    booking = models.ForeignKey(PlotBooking, on_delete=models.CASCADE, related_name="commission_payouts")
    role = models.CharField(max_length=40, choices=Role.choices)
    calculation_type = models.CharField(max_length=30, choices=PropertyCommissionRule.CalculationType.choices, blank=True)
    rule_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNPAID)
    payout_reference = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="generated_property_commissions")
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="paid_property_commissions")
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["booking_id", "role"]
        unique_together = ("booking", "role")

    def __str__(self):
        return f"{self.booking} - {self.get_role_display()} - {self.amount}"


class BookingInstallment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIAL = "partial", "Partial"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    booking = models.ForeignKey(PlotBooking, on_delete=models.CASCADE, related_name="installments")
    title = models.CharField(max_length=140)
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "id"]

    def __str__(self):
        return f"{self.booking} - {self.title}"

    @property
    def balance_amount(self):
        return max((self.amount or 0) - (self.paid_amount or 0), 0)


class BookingPayment(models.Model):
    class PaymentMode(models.TextChoices):
        CASH = "cash", "Cash"
        UPI = "upi", "UPI"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        CHEQUE = "cheque", "Cheque"
        CARD = "card", "Card"
        OTHER = "other", "Other"

    booking = models.ForeignKey(PlotBooking, on_delete=models.CASCADE, related_name="payments")
    installment = models.ForeignKey(BookingInstallment, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    received_on = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(max_length=30, choices=PaymentMode.choices, default=PaymentMode.CASH)
    reference_number = models.CharField(max_length=120, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="received_booking_payments")
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_on", "-created_at"]

    def __str__(self):
        return f"{self.booking} - {self.amount}"


class BookingAgreement(models.Model):
    class AgreementType(models.TextChoices):
        BOOKING = "booking", "Booking Agreement"
        SALE = "sale", "Sale Agreement"
        REGISTRY = "registry", "Registry Deed"
        POSSESSION = "possession", "Possession Letter"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent to Client"
        SIGNED = "signed", "Signed"
        REGISTERED = "registered", "Registered"
        CANCELLED = "cancelled", "Cancelled"

    booking = models.ForeignKey(PlotBooking, on_delete=models.CASCADE, related_name="agreements")
    agreement_type = models.CharField(max_length=30, choices=AgreementType.choices, default=AgreementType.BOOKING)
    title = models.CharField(max_length=160)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    file = models.FileField(upload_to="properties/agreements/", blank=True)
    agreement_number = models.CharField(max_length=120, blank=True)
    stamp_number = models.CharField(max_length=120, blank=True)
    prepared_on = models.DateField(null=True, blank=True)
    signed_on = models.DateField(null=True, blank=True)
    registered_on = models.DateField(null=True, blank=True)
    registration_office = models.CharField(max_length=160, blank=True)
    next_action_date = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_booking_agreements")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="updated_booking_agreements")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-prepared_on", "-created_at"]

    def __str__(self):
        return f"{self.booking} - {self.title}"


class MISReportSnapshot(models.Model):
    class ReportType(models.TextChoices):
        OWNER = "owner", "Owner MIS"

    company = models.ForeignKey("accounts.CompanyProfile", on_delete=models.CASCADE, related_name="mis_report_snapshots")
    report_type = models.CharField(max_length=30, choices=ReportType.choices, default=ReportType.OWNER)
    title = models.CharField(max_length=160)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    data = models.JSONField(default=dict)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="generated_mis_reports")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class PropertyVisit(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No Show"
        FOLLOW_UP = "follow_up", "Follow-up Required"

    class Outcome(models.TextChoices):
        PENDING = "pending", "Pending"
        INTERESTED = "interested", "Interested"
        NOT_INTERESTED = "not_interested", "Not Interested"
        NEGOTIATION = "negotiation", "Negotiation"
        BOOKED = "booked", "Booked"
        CLOSED = "closed", "Closed"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="visits")
    plot = models.ForeignKey(ColonyPlot, on_delete=models.SET_NULL, related_name="visits", null=True, blank=True)
    scheduled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="scheduled_property_visits",
        null=True,
        blank=True,
    )
    assigned_employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_property_visits",
        null=True,
        blank=True,
    )
    client_name = models.CharField(max_length=140)
    client_phone = models.CharField(max_length=20, blank=True)
    client_email = models.EmailField(blank=True)
    image = models.ImageField(upload_to="properties/visits/", blank=True)
    visit_at = models.DateTimeField()
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.SCHEDULED)
    outcome = models.CharField(max_length=30, choices=Outcome.choices, default=Outcome.PENDING)
    notes = models.TextField(blank=True)
    follow_up_at = models.DateTimeField(null=True, blank=True)
    follow_up_completed_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    conversion_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-visit_at", "-created_at"]

    def __str__(self):
        return f"{self.client_name} - {self.property} - {self.get_status_display()}"
