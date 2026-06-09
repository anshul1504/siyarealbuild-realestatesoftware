from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import ColonyPlot, Property, PropertyDocument, PropertyVisit


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
        widget=MultiFileInput(attrs={"class": "form-control", "accept": "image/*", "multiple": True}),
        help_text="Upload site photos, elevation, layout, or sample unit images.",
    )
    documents = MultiFileField(
        required=False,
        widget=MultiFileInput(attrs={"class": "form-control", "accept": ".pdf,image/*", "multiple": True}),
        help_text="Upload RERA, T&CP, registry, map/layout, or legal documents.",
    )
    document_type = forms.ChoiceField(
        choices=PropertyDocument.DocumentType.choices,
        required=False,
        initial=PropertyDocument.DocumentType.OTHER,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = Property
        fields = [
            "title",
            "category",
            "listing_for",
            "status",
            "assigned_to",
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
            "total_plots",
            "available_plots",
            "development_status",
            "amenities",
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
            "rera_number",
            "tcp_approval_number",
            "registry_status",
            "khasra_number",
            "legal_status",
            "legal_notes",
            "contact_name",
            "contact_phone",
            "internal_notes",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Project / listing name"}),
            "category": forms.Select(attrs={"class": "form-control", "data-property-category": "true"}),
            "listing_for": forms.Select(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "assigned_to": forms.Select(attrs={"class": "form-control"}),
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
            "facing": forms.TextInput(attrs={"class": "form-control", "placeholder": "East / West / Corner"}),
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
            "total_plots": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "available_plots": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "development_status": forms.TextInput(attrs={"class": "form-control", "placeholder": "Road, drainage, garden, gate, etc."}),
            "amenities": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Water, electricity, security, park, drainage"}),
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
            "rera_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "RERA number"}),
            "tcp_approval_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "T&CP approval number"}),
            "registry_status": forms.TextInput(attrs={"class": "form-control", "placeholder": "Registry / diversion / mutation"}),
            "khasra_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Khasra / survey number"}),
            "legal_status": forms.Select(attrs={"class": "form-control"}),
            "legal_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "contact_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Owner / broker / developer"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control indian-phone-input", "placeholder": "+91 9876543210"}),
            "internal_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        if category == Property.Category.COLONY and not cleaned_data.get("total_plots"):
            self.add_error("total_plots", "Total plots are required for colony listings.")
        if category in {Property.Category.PLOT, Property.Category.RESALE_PLOT, Property.Category.COLONY}:
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


class ColonyPlotForm(forms.ModelForm):
    class Meta:
        model = ColonyPlot
        fields = ["plot_number", "area_sqft", "length_ft", "width_ft", "facing", "road_width_ft", "price", "status", "notes"]
        widgets = {
            "plot_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "A-01"}),
            "area_sqft": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "length_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "width_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "facing": forms.TextInput(attrs={"class": "form-control", "placeholder": "East"}),
            "road_width_ft": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": "0.01"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.TextInput(attrs={"class": "form-control", "placeholder": "Corner / premium / park facing"}),
        }

    def has_changed(self):
        if not (self.data.get(self.add_prefix("plot_number")) or "").strip():
            return False
        return super().has_changed()


ColonyPlotFormSet = inlineformset_factory(
    Property,
    ColonyPlot,
    form=ColonyPlotForm,
    extra=0,
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
