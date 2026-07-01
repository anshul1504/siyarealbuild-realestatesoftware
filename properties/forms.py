from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import BookingAgreement, BookingInstallment, BookingPayment, ColonyPlot, PlotBooking, PlotQuotation, Property, PropertyCommissionRule, PropertyDeveloper, PropertyDocument, PropertyVisit
from .validators import validate_property_document, validate_property_image


DEFAULT_AMENITIES = (
    ("boundary_wall", "Boundary wall"),
    ("main_gate", "Main gate"),
    ("security", "Security"),
    ("garden", "Garden"),
    ("club_house", "Club house"),
    ("kids_play_area", "Kids play area"),
    ("water_connection", "Water connection"),
    ("electricity", "Electricity"),
    ("street_lights", "Street lights"),
    ("drainage", "Drainage"),
    ("cement_road", "Cement road"),
    ("cctv", "CCTV"),
    ("commercial_shops", "Commercial shops"),
    ("open_gym", "Open gym"),
)


User = get_user_model()


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultiFileField(forms.FileField):
    widget = MultiFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultiFileField, self).clean(file, initial) for file in files]


class PropertyForm(forms.ModelForm):
    photos = MultiFileField(
        required=False,
        validators=[validate_property_image],
        widget=MultiFileInput(attrs={"class": "form-control", "accept": "image/*", "multiple": True}),
        help_text="Select and upload multiple site, elevation, or sample unit photos at once.",
    )
    map_layouts = MultiFileField(
        required=False,
        validators=[validate_property_document],
        widget=MultiFileInput(attrs={"class": "form-control", "accept": ".pdf,image/*", "multiple": True}),
        help_text="Upload one or more approved map or layout files (PDF or image).",
    )
    documents = MultiFileField(
        required=False,
        validators=[validate_property_document],
        widget=MultiFileInput(attrs={"class": "form-control", "accept": ".pdf,image/*", "multiple": True}),
        help_text="Upload RERA, T&CP, registry, map/layout, or legal documents.",
    )
    document_type = forms.ChoiceField(
        choices=PropertyDocument.DocumentType.choices,
        required=False,
        initial=PropertyDocument.DocumentType.OTHER,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    cover_photo_index = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1, "placeholder": "1"}),
        help_text="Enter the number of the uploaded photo that should be used as the cover image.",
    )

    class Meta:
        model = Property
        fields = [
            "title",
            "category",
            "listing_for",
            "status",
            "assigned_to",
            "developer",
            "city",
            "locality",
            "address",
            "landmark",
            "map_link",
            "price",
            "price_per_sqft",
            "area_sqft",
            "carpet_area_sqft",
            "builtup_area_sqft",
            "length_ft",
            "width_ft",
            "facing",
            "road_width_ft",
            "bedrooms",
            "bathrooms",
            "balconies",
            "floor_number",
            "total_floors",
            "parking_count",
            "furnishing",
            "construction_status",
            "possession_status",
            "colony_name",
            "development_name",
            "total_plots",
            "available_plots",
            "development_status",
            "selected_amenities",
            "amenities",
            "custom_amenities",
            "amenity_count",
            "garden_count",
            "corner_plot_count",
            "garden_facing_plot_count",
            "plc_rules",
            "nearby_residential",
            "nearby_commercial",
            "nearby_connectivity",
            "nearby_education",
            "nearby_healthcare",
            "nearby_landmarks",
            "base_rate_per_sqft",
            "residential_rate_per_sqft",
            "commercial_rate_per_sqft",
            "lig_rate_per_sqft",
            "mig_rate_per_sqft",
            "hig_rate_per_sqft",
            "ews_rate_per_sqft",
            "electricity_charge",
            "maintenance_charge",
            "development_charge",
            "registry_charge",
            "other_charge",
            "corner_plc_rate",
            "garden_facing_plc_rate",
            "main_road_plc_rate",
            "wide_road_plc_rate",
            "rera_number",
            "tcp_approval_number",
            "registry_status",
            "khasra_number",
            "legal_status",
            "legal_notes",
            "contact_name",
            "contact_phone",
            "video_link",
            "video_links",
            "internal_notes",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Project / listing name"}),
            "category": forms.Select(attrs={"class": "form-control", "data-property-category": "true"}),
            "listing_for": forms.Select(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "assigned_to": forms.Select(attrs={"class": "form-control"}),
            "developer": forms.Select(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control", "placeholder": "City"}),
            "locality": forms.TextInput(attrs={"class": "form-control", "placeholder": "Locality / area"}),
            "address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Street, colony, landmark"}),
            "landmark": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nearby landmark"}),
            "map_link": forms.URLInput(attrs={"class": "form-control", "placeholder": "Google Maps link"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "price_per_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "area_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "carpet_area_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "builtup_area_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "length_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "width_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "facing": forms.Select(
                choices=[("", "Select facing"), *ColonyPlot.Facing.choices],
                attrs={"class": "form-control"},
            ),
            "road_width_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "bedrooms": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "bathrooms": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "balconies": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "floor_number": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "total_floors": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "parking_count": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "furnishing": forms.TextInput(attrs={"class": "form-control", "placeholder": "Unfurnished / Semi / Fully"}),
            "construction_status": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ready / Under construction"}),
            "possession_status": forms.TextInput(attrs={"class": "form-control", "placeholder": "Immediate / date / after registry"}),
            "colony_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Colony / project name"}),
            "development_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Development / phase name"}),
            "total_plots": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "available_plots": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "development_status": forms.Select(
                choices=[("", "Select development status"), *Property.DevelopmentStatus.choices],
                attrs={"class": "form-control"},
            ),
            "selected_amenities": forms.CheckboxSelectMultiple(),
            "amenities": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Water, electricity, security, park, drainage"}),
            "custom_amenities": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Add custom amenities, one per line"}),
            "amenity_count": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "garden_count": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "corner_plot_count": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "garden_facing_plot_count": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "plc_rules": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Corner PLC, garden-facing PLC, main-road PLC, premium block rules"}),
            "nearby_residential": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Nearby apartments, colonies, residential pockets"}),
            "nearby_commercial": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Markets, shops, offices, business areas"}),
            "nearby_connectivity": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Main road, railway station, bus stand, airport, public transport"}),
            "nearby_education": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Schools, colleges, coaching zones"}),
            "nearby_healthcare": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Hospitals, clinics, pharmacies"}),
            "nearby_landmarks": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Parks, temples, malls, landmarks, government offices"}),
            "base_rate_per_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "residential_rate_per_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "commercial_rate_per_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "lig_rate_per_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "mig_rate_per_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "hig_rate_per_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "ews_rate_per_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "electricity_charge": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "maintenance_charge": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "development_charge": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "registry_charge": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "other_charge": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "corner_plc_rate": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 100, "step": "0.01"}),
            "garden_facing_plc_rate": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 100, "step": "0.01"}),
            "main_road_plc_rate": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 100, "step": "0.01"}),
            "wide_road_plc_rate": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 100, "step": "0.01"}),
            "rera_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "RERA number"}),
            "tcp_approval_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "T&CP approval number"}),
            "registry_status": forms.TextInput(attrs={"class": "form-control", "placeholder": "Registry / diversion / mutation"}),
            "khasra_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Khasra / survey number"}),
            "legal_status": forms.Select(attrs={"class": "form-control"}),
            "legal_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "contact_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Owner / broker / developer"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control indian-phone-input", "placeholder": "+91 9876543210"}),
            "video_link": forms.URLInput(attrs={"class": "form-control", "placeholder": "Primary walkthrough video link"}),
            "video_links": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "More YouTube / Drive links, one per line"}),
            "internal_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        if category == Property.Category.COLONY and not cleaned_data.get("total_plots"):
            self.add_error("total_plots", "Total plots are required for colony listings.")
        if category == Property.Category.COLONY:
            required_fields = {
                "colony_name": "Colony name is required.",
                "development_name": "Development name is required.",
                "development_status": "Development status is required.",
                "residential_rate_per_sqft": "Residential rate is required.",
                "commercial_rate_per_sqft": "Commercial rate is required.",
                "lig_rate_per_sqft": "LIG rate is required.",
                "ews_rate_per_sqft": "EWS rate is required.",
            }
            for field_name, message in required_fields.items():
                if not cleaned_data.get(field_name):
                    self.add_error(field_name, message)
        if category in {Property.Category.PLOT, Property.Category.RESALE_PLOT}:
            if not cleaned_data.get("area_sqft"):
                self.add_error("area_sqft", "Plot area is required.")
        if category in {
            Property.Category.FLAT,
            Property.Category.RESIDENTIAL_HOUSE,
            Property.Category.ROW_HOUSE,
            Property.Category.VILLA,
        } and not cleaned_data.get("bedrooms"):
            self.add_error("bedrooms", "Bedrooms are required for residential listings.")
        if cleaned_data.get("available_plots") and cleaned_data.get("total_plots"):
            if cleaned_data["available_plots"] > cleaned_data["total_plots"]:
                self.add_error("available_plots", "Available plots cannot be more than total plots.")
        return cleaned_data

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        company = getattr(getattr(user, "profile", None), "company", None)
        self.fields["assigned_to"].queryset = User.objects.filter(profile__company=company) if company else User.objects.none()
        self.fields["assigned_to"].required = False
        self.fields["area_sqft"].required = False
        self.fields["developer"].queryset = PropertyDeveloper.objects.filter(company=company, is_active=True) if company else PropertyDeveloper.objects.none()
        self.fields["developer"].required = False
        self.fields["selected_amenities"] = forms.MultipleChoiceField(
            choices=DEFAULT_AMENITIES,
            required=False,
            widget=forms.CheckboxSelectMultiple(),
        )
        self.fields["category"].label = "Property Category"
        self.fields["title"].label = "Listing / Project Name"
        self.fields["developer"].label = "Developer"
        self.fields["assigned_to"].label = "Assigned Team Member"
        self.fields["development_name"].label = "Development Name"
        self.fields["corner_plc_rate"].label = "Corner PLC (%)"
        self.fields["garden_facing_plc_rate"].label = "Garden Facing PLC (%)"
        self.fields["main_road_plc_rate"].label = "Main Road PLC (%)"
        self.fields["wide_road_plc_rate"].label = "Wide Road PLC (%)"
        self.fields["base_rate_per_sqft"].label = "Default Base Rate / sqft"
        self.fields["residential_rate_per_sqft"].label = "Residential Base Rate / sqft"
        self.fields["commercial_rate_per_sqft"].label = "Commercial Base Rate / sqft"
        self.fields["lig_rate_per_sqft"].label = "LIG Base Rate / sqft"
        self.fields["mig_rate_per_sqft"].label = "MIG Base Rate / sqft"
        self.fields["hig_rate_per_sqft"].label = "HIG Base Rate / sqft"
        self.fields["ews_rate_per_sqft"].label = "EWS Base Rate / sqft"
        self.fields["electricity_charge"].label = "Electricity / sqft"
        self.fields["maintenance_charge"].label = "Maintenance / sqft"
        self.fields["development_charge"].label = "Development / sqft"
        self.fields["registry_charge"].label = "Registry / sqft"
        self.fields["other_charge"].label = "Other Charges / sqft"
        self.fields["video_link"].label = "Primary Walkthrough Video"
        self.fields["video_links"].label = "Additional Video Links"
        self.fields["photos"].label = "Property Photos"
        self.fields["map_layouts"].label = "Map / Layout Files"
        self.fields["cover_photo_index"].label = "Cover Photo Number"


class ColonyPlotForm(forms.ModelForm):
    class Meta:
        model = ColonyPlot
        fields = [
            "plot_number",
            "plot_category",
            "custom_category",
            "block",
            "area_sqft",
            "length_ft",
            "width_ft",
            "facing",
            "road_width_ft",
            "base_rate",
            "plc_rate",
            "extra_charges",
            "price",
            "is_corner",
            "is_garden_facing",
            "is_main_road",
            "is_wide_road",
            "status",
            "notes",
        ]
        widgets = {
            "plot_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "A-01"}),
            "plot_category": forms.Select(attrs={"class": "form-control"}),
            "custom_category": forms.TextInput(attrs={"class": "form-control", "placeholder": "Custom category"}),
            "block": forms.TextInput(attrs={"class": "form-control", "placeholder": "Block / sector"}),
            "area_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "length_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "width_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "facing": forms.Select(choices=[("", "Facing"), *ColonyPlot.Facing.choices], attrs={"class": "form-control"}),
            "road_width_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "base_rate": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "plc_rate": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 100, "step": "0.01"}),
            "extra_charges": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01", "readonly": True}),
            "is_corner": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_garden_facing": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_main_road": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_wide_road": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.TextInput(attrs={"class": "form-control", "placeholder": "Corner / premium / park facing"}),
        }

    def has_changed(self):
        if not (self.data.get(self.add_prefix("plot_number")) or "").strip():
            return False
        return super().has_changed()


class PropertyDeveloperForm(forms.ModelForm):
    class Meta:
        model = PropertyDeveloper
        fields = ["name", "company_name", "contact_person", "mobile", "email", "office_address", "rera_number", "notes", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "company_name": forms.TextInput(attrs={"class": "form-control"}),
            "contact_person": forms.TextInput(attrs={"class": "form-control"}),
            "mobile": forms.TextInput(attrs={"class": "form-control indian-phone-input"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "office_address": forms.TextInput(attrs={"class": "form-control"}),
            "rera_number": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class PlotQuotationForm(forms.ModelForm):
    class Meta:
        model = PlotQuotation
        fields = ["client_name", "client_phone", "client_email", "plot_area_sqft", "plot_length_ft", "plot_width_ft", "plot_facing", "base_amount", "plc_amount", "charges_amount", "discount_amount", "valid_until", "terms", "status"]
        widgets = {
            "client_name": forms.TextInput(attrs={"class": "form-control"}),
            "client_phone": forms.TextInput(attrs={"class": "form-control indian-phone-input"}),
            "client_email": forms.EmailInput(attrs={"class": "form-control"}),
            "plot_area_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "1"}),
            "plot_length_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "plot_width_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "plot_facing": forms.TextInput(attrs={"class": "form-control"}),
            "base_amount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "plc_amount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "charges_amount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "discount_amount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "valid_until": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "terms": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "status": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("plot_area_sqft", "plot_length_ft", "plot_width_ft", "plot_facing"):
            self.fields[field_name].required = False


class PlotBookingForm(forms.ModelForm):
    paid_amount_received = forms.DecimalField(
        label="Paid Amount Received",
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=14,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01", "placeholder": "Amount actually received"}),
        help_text="Creates or updates the initial payment ledger entry.",
    )

    class Meta:
        model = PlotBooking
        fields = [
            "quotation",
            "client_name",
            "client_phone",
            "client_email",
            "client_address",
            "government_id_type",
            "government_id_number",
            "government_id_document",
            "plot_area_sqft",
            "plot_length_ft",
            "plot_width_ft",
            "plot_facing",
            "booking_date",
            "booking_amount",
            "agreed_rate",
            "discount_amount",
            "coupon_code",
            "coupon_discount_amount",
            "plc_amount",
            "charges_amount",
            "payment_mode",
            "payment_reference",
            "payment_proof",
            "discount_reason",
            "status",
            "note",
        ]
        widgets = {
            "quotation": forms.Select(attrs={"class": "form-control"}),
            "client_name": forms.TextInput(attrs={"class": "form-control"}),
            "client_phone": forms.TextInput(attrs={"class": "form-control indian-phone-input"}),
            "client_email": forms.EmailInput(attrs={"class": "form-control"}),
            "client_address": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Complete client address"}),
            "government_id_type": forms.Select(attrs={"class": "form-control"}),
            "government_id_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Government ID number"}),
            "government_id_document": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,image/jpeg,image/png,image/webp"}),
            "plot_area_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "plot_length_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "plot_width_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "plot_facing": forms.TextInput(attrs={"class": "form-control"}),
            "booking_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "booking_amount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "agreed_rate": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "discount_amount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "coupon_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "Referral / offer coupon"}),
            "coupon_discount_amount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "plc_amount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "charges_amount": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "payment_mode": forms.TextInput(attrs={"class": "form-control"}),
            "payment_reference": forms.TextInput(attrs={"class": "form-control", "placeholder": "UTR / cheque / receipt reference"}),
            "payment_proof": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp"}),
            "discount_reason": forms.TextInput(attrs={"class": "form-control", "placeholder": "Reason or approval note for discount"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, plot=None, allow_direct_booking=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.plot = plot
        self.fields["quotation"].queryset = plot.quotations.all() if plot else PlotQuotation.objects.none()
        self.fields["quotation"].required = False
        for field_name in ("plot_area_sqft", "plot_length_ft", "plot_width_ft", "plot_facing"):
            self.fields[field_name].required = False
        if not allow_direct_booking:
            self.fields.pop("status", None)
            self.fields.pop("paid_amount_received", None)
        elif self.instance and self.instance.pk:
            initial_payment = self.instance.payments.filter(note="Initial booking payment.").first()
            self.fields["paid_amount_received"].initial = initial_payment.amount if initial_payment else 0
        else:
            self.fields["paid_amount_received"].initial = self.initial.get("booking_amount", 0)

    def clean_coupon_code(self):
        return (self.cleaned_data.get("coupon_code") or "").upper().strip()

    def clean_government_id_document(self):
        return validate_property_document(self.cleaned_data.get("government_id_document"))

    def clean_payment_proof(self):
        return validate_property_image(self.cleaned_data.get("payment_proof"))

    def clean(self):
        cleaned_data = super().clean()
        coupon_code = cleaned_data.get("coupon_code")
        coupon_discount_amount = cleaned_data.get("coupon_discount_amount") or 0
        if coupon_discount_amount and not coupon_code:
            self.add_error("coupon_code", "Enter the coupon code used for this booking discount.")
        if cleaned_data.get("government_id_type") and not cleaned_data.get("government_id_number"):
            self.add_error("government_id_number", "Enter the selected government ID number.")
        paid_amount_received = cleaned_data.get("paid_amount_received")
        if paid_amount_received is not None:
            area = cleaned_data.get("plot_area_sqft") or getattr(self.plot, "area_sqft", 0) or 0
            deal_value = (
                (area * (cleaned_data.get("agreed_rate") or 0))
                + (cleaned_data.get("plc_amount") or 0)
                + (cleaned_data.get("charges_amount") or 0)
                - (cleaned_data.get("discount_amount") or 0)
                - coupon_discount_amount
            )
            if paid_amount_received > deal_value:
                self.add_error("paid_amount_received", "Paid amount cannot exceed the total deal value.")
        return cleaned_data


class BookingInstallmentForm(forms.ModelForm):
    class Meta:
        model = BookingInstallment
        fields = ["title", "due_date", "amount", "note"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Booking amount / registry / final payment"}),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "min": 1, "step": "0.01"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class BookingPaymentForm(forms.ModelForm):
    class Meta:
        model = BookingPayment
        fields = ["installment", "received_on", "amount", "mode", "reference_number", "note"]
        widgets = {
            "installment": forms.Select(attrs={"class": "form-control"}),
            "received_on": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "min": 1, "step": "0.01"}),
            "mode": forms.Select(attrs={"class": "form-control"}),
            "reference_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "UTR / cheque / receipt no."}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, booking=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.booking = booking
        installments = booking.installments.exclude(status=BookingInstallment.Status.CANCELLED) if booking else BookingInstallment.objects.none()
        self.fields["installment"].queryset = installments
        self.fields["installment"].required = False

    def clean(self):
        cleaned_data = super().clean()
        installment = cleaned_data.get("installment")
        amount = cleaned_data.get("amount") or 0
        if installment and amount > installment.balance_amount:
            self.add_error("amount", "Payment amount cannot be more than selected installment balance.")
        if self.booking and amount > self.booking.balance_amount:
            self.add_error("amount", "Payment amount cannot be more than the booking balance.")
        return cleaned_data


class PropertyDocumentReviewForm(forms.ModelForm):
    class Meta:
        model = PropertyDocument
        fields = ["document_number", "issued_on", "expires_on", "review_status", "review_note"]
        widgets = {
            "document_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "RERA / registry / approval number"}),
            "issued_on": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "expires_on": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "review_status": forms.Select(attrs={"class": "form-control"}),
            "review_note": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class PropertyDocumentUploadForm(forms.Form):
    document_type = forms.ChoiceField(choices=PropertyDocument.DocumentType.choices, widget=forms.Select(attrs={"class": "form-control"}))
    documents = MultiFileField(
        validators=[validate_property_document],
        widget=MultiFileInput(attrs={"class": "form-control", "accept": ".pdf,image/*", "multiple": True}),
        help_text="Select multiple PDF, JPG, PNG, or WebP files. Maximum 10 MB per file.",
    )


class BookingAgreementForm(forms.ModelForm):
    def clean_file(self):
        return validate_property_document(self.cleaned_data.get("file"))

    class Meta:
        model = BookingAgreement
        fields = [
            "agreement_type",
            "title",
            "status",
            "file",
            "agreement_number",
            "stamp_number",
            "prepared_on",
            "signed_on",
            "registered_on",
            "registration_office",
            "next_action_date",
            "note",
        ]
        widgets = {
            "agreement_type": forms.Select(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Booking agreement / registry deed"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,image/*"}),
            "agreement_number": forms.TextInput(attrs={"class": "form-control"}),
            "stamp_number": forms.TextInput(attrs={"class": "form-control"}),
            "prepared_on": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "signed_on": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "registered_on": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "registration_office": forms.TextInput(attrs={"class": "form-control"}),
            "next_action_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        if status == BookingAgreement.Status.SIGNED and not cleaned_data.get("signed_on"):
            self.add_error("signed_on", "Signed date is required when agreement is marked signed.")
        if status == BookingAgreement.Status.REGISTERED and not cleaned_data.get("registered_on"):
            self.add_error("registered_on", "Registered date is required when agreement is marked registered.")
        return cleaned_data


ColonyPlotFormSet = inlineformset_factory(
    Property,
    ColonyPlot,
    form=ColonyPlotForm,
    extra=0,
    can_delete=True,
)


class PropertyCommissionRuleForm(forms.ModelForm):
    class Meta:
        model = PropertyCommissionRule
        fields = ["role", "calculation_type", "value", "note", "is_active"]
        widgets = {
            "role": forms.Select(attrs={"class": "form-control"}),
            "calculation_type": forms.Select(attrs={"class": "form-control"}),
            "value": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "note": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional condition / note"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def has_changed(self):
        if not self.data.get(self.add_prefix("role")):
            return False
        return super().has_changed()


PropertyCommissionRuleFormSet = inlineformset_factory(
    Property,
    PropertyCommissionRule,
    form=PropertyCommissionRuleForm,
    extra=5,
    can_delete=True,
)


class PropertyVisitForm(forms.ModelForm):
    class Meta:
        model = PropertyVisit
        fields = [
            "plot",
            "assigned_employee",
            "client_name",
            "client_phone",
            "client_email",
            "image",
            "visit_at",
            "status",
            "outcome",
            "notes",
            "follow_up_at",
            "follow_up_completed_at",
            "conversion_note",
        ]
        widgets = {
            "plot": forms.Select(attrs={"class": "form-control"}),
            "assigned_employee": forms.Select(attrs={"class": "form-control"}),
            "client_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Client name"}),
            "client_phone": forms.TextInput(attrs={"class": "form-control indian-phone-input", "placeholder": "+91 9876543210"}),
            "client_email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "client@example.com"}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/*"}),
            "visit_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "outcome": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Visit notes, client requirement, site feedback"}),
            "follow_up_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "follow_up_completed_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "conversion_note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, property_obj=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.property_obj = property_obj or getattr(self.instance, "property", None)
        if self.property_obj:
            self.fields["plot"].queryset = self.property_obj.plots.all()
        else:
            self.fields["plot"].queryset = ColonyPlot.objects.none()
        self.fields["plot"].required = False

        company = getattr(getattr(user, "profile", None), "company", None)
        employees = User.objects.all().order_by("first_name", "last_name", "email")
        if company:
            employees = employees.filter(profile__company=company)
        self.fields["assigned_employee"].queryset = employees
        self.fields["assigned_employee"].required = False

        for field_name in ("visit_at", "follow_up_at", "follow_up_completed_at"):
            value = self.initial.get(field_name) or getattr(self.instance, field_name, None)
            if value:
                self.initial[field_name] = value.strftime("%Y-%m-%dT%H:%M")

    def clean_image(self):
        return validate_property_image(self.cleaned_data.get("image"))

    def clean(self):
        cleaned_data = super().clean()
        plot = cleaned_data.get("plot")
        if plot and self.property_obj and plot.property_id != self.property_obj.id:
            self.add_error("plot", "Selected plot does not belong to this property.")
        return cleaned_data


class PropertyShareEmailForm(forms.Form):
    emails = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "client@example.com, second-client@example.com",
            }
        ),
        help_text="Add one or more email addresses separated by comma, space, or new line.",
    )
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Optional message for the client",
            }
        ),
    )

    def clean_emails(self):
        raw_value = self.cleaned_data["emails"]
        candidates = [item.strip() for item in raw_value.replace("\n", ",").replace(" ", ",").split(",") if item.strip()]
        valid_emails = []
        for email in candidates:
            try:
                validate_email(email)
            except ValidationError as exc:
                raise forms.ValidationError(f"{email} is not a valid email address.") from exc
            if email.lower() not in [existing.lower() for existing in valid_emails]:
                valid_emails.append(email)
        if not valid_emails:
            raise forms.ValidationError("Add at least one client email address.")
        return valid_emails
