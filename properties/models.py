from django.conf import settings
from django.db import models


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

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="properties")
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
    total_plots = models.PositiveIntegerField(default=0)
    available_plots = models.PositiveIntegerField(default=0)
    development_status = models.CharField(max_length=120, blank=True)
    amenities = models.TextField(blank=True)
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

    rera_number = models.CharField(max_length=80, blank=True)
    tcp_approval_number = models.CharField(max_length=80, blank=True)
    registry_status = models.CharField(max_length=120, blank=True)
    khasra_number = models.CharField(max_length=120, blank=True)
    legal_status = models.CharField(max_length=30, choices=LegalStatus.choices, blank=True)
    legal_notes = models.TextField(blank=True)

    contact_name = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    internal_notes = models.TextField(blank=True)
    lead_count = models.PositiveIntegerField(default=0)
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

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=30, choices=DocumentType.choices, default=DocumentType.OTHER)
    title = models.CharField(max_length=160, blank=True)
    file = models.FileField(upload_to="properties/documents/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document_type", "id"]

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.property}"


class ColonyPlot(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        HOLD = "hold", "Hold"
        SOLD = "sold", "Sold"
        RESERVED = "reserved", "Reserved"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="plots")
    plot_number = models.CharField(max_length=40)
    area_sqft = models.PositiveIntegerField(default=0)
    length_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    width_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    facing = models.CharField(max_length=40, blank=True)
    road_width_ft = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    notes = models.CharField(max_length=220, blank=True)

    class Meta:
        ordering = ["plot_number"]
        unique_together = ("property", "plot_number")

    def __str__(self):
        return f"{self.property} - Plot {self.plot_number}"


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
    visit_at = models.DateTimeField()
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.SCHEDULED)
    outcome = models.CharField(max_length=30, choices=Outcome.choices, default=Outcome.PENDING)
    notes = models.TextField(blank=True)
    follow_up_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-visit_at", "-created_at"]

    def __str__(self):
        return f"{self.client_name} - {self.property} - {self.get_status_display()}"
