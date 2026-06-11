import json

from django import forms

from properties.models import Property, PropertyVisit

from .models import AssignmentMode, Lead, LeadAssignmentRule, LeadFollowUp, LeadPriority, LeadSource, LeadStatus, MetaLeadSource
from .policies import can_assign_leads
from .selectors import assignable_users_for


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            "client_name",
            "phone",
            "email",
            "city",
            "locality",
            "budget_min",
            "budget_max",
            "requirement",
            "property_category",
            "listing_for",
            "source",
            "priority",
            "assigned_to",
            "property",
            "notes",
        ]
        widgets = {
            "client_name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control indian-phone-input"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "locality": forms.TextInput(attrs={"class": "form-control"}),
            "budget_min": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "budget_max": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "requirement": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "property_category": forms.Select(attrs={"class": "form-control"}),
            "listing_for": forms.Select(attrs={"class": "form-control"}),
            "source": forms.Select(attrs={"class": "form-control"}),
            "priority": forms.Select(attrs={"class": "form-control"}),
            "assigned_to": forms.Select(attrs={"class": "form-control"}),
            "property": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, user, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["assigned_to"].queryset = assignable_users_for(user)
        self.fields["property"].queryset = Property.objects.filter(owner__profile__company=company)
        if not can_assign_leads(user):
            self.fields.pop("assigned_to")
        else:
            self.fields["assigned_to"].required = False
        self.fields["property"].required = False
        self.fields["property_category"].required = False
        self.fields["listing_for"].required = False

    def clean(self):
        cleaned = super().clean()
        budget_min = cleaned.get("budget_min")
        budget_max = cleaned.get("budget_max")
        if budget_min is not None and budget_max is not None and budget_min > budget_max:
            self.add_error("budget_max", "Maximum budget cannot be less than minimum budget.")
        if not cleaned.get("phone") and not cleaned.get("email"):
            raise forms.ValidationError("Add at least one client contact: phone or email.")
        return cleaned


class LeadStatusForm(forms.Form):
    status = forms.ChoiceField(choices=LeadStatus.choices, widget=forms.Select(attrs={"class": "form-control"}))
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        note = (cleaned.get("note") or "").strip()
        if status == LeadStatus.LOST and not note:
            self.add_error("note", "Add lost reason before marking a lead as lost.")
        if status in {LeadStatus.BOOKED, LeadStatus.CLOSED} and not note:
            self.add_error("note", "Add booking or closure note before conversion.")
        return cleaned


class LeadAssignmentForm(forms.Form):
    assigned_to = forms.ModelChoiceField(queryset=None, required=False, widget=forms.Select(attrs={"class": "form-control"}))
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = assignable_users_for(user)


class LeadNoteForm(forms.Form):
    note = forms.CharField(widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Add call note, WhatsApp update or client feedback"}))


class LeadArchiveForm(forms.Form):
    reason = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Archive reason"}))


class LeadFollowUpForm(forms.ModelForm):
    class Meta:
        model = LeadFollowUp
        fields = ["assigned_to", "due_at", "note"]
        widgets = {
            "assigned_to": forms.Select(attrs={"class": "form-control"}),
            "due_at": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = assignable_users_for(user)


class LeadFollowUpCompleteForm(forms.Form):
    outcome = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Outcome"}))
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))


class LeadBulkActionForm(forms.Form):
    ACTION_ASSIGN = "assign"
    ACTION_STATUS = "status"
    ACTION_PRIORITY = "priority"
    ACTION_CHOICES = (
        (ACTION_ASSIGN, "Assign selected"),
        (ACTION_STATUS, "Update status"),
        (ACTION_PRIORITY, "Update priority"),
    )
    lead_ids = forms.CharField(widget=forms.HiddenInput)
    action = forms.ChoiceField(choices=ACTION_CHOICES, widget=forms.Select(attrs={"class": "form-control"}))
    assigned_to = forms.ModelChoiceField(queryset=None, required=False, widget=forms.Select(attrs={"class": "form-control"}))
    status = forms.ChoiceField(choices=(("", "Select status"),) + tuple(LeadStatus.choices), required=False, widget=forms.Select(attrs={"class": "form-control"}))
    priority = forms.ChoiceField(choices=(("", "Select priority"),) + tuple(LeadPriority.choices), required=False, widget=forms.Select(attrs={"class": "form-control"}))
    note = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Bulk action note"}))

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = assignable_users_for(user)

    def clean_lead_ids(self):
        raw_ids = self.cleaned_data["lead_ids"].replace(" ", "")
        ids = [item for item in raw_ids.split(",") if item]
        if not ids:
            raise forms.ValidationError("Select at least one lead.")
        if not all(item.isdigit() for item in ids):
            raise forms.ValidationError("Invalid lead selection.")
        return [int(item) for item in ids]


class LeadVisitForm(forms.Form):
    property = forms.ModelChoiceField(queryset=Property.objects.none(), widget=forms.Select(attrs={"class": "form-control"}))
    visit_at = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}))
    assigned_employee = forms.ModelChoiceField(queryset=None, required=False, widget=forms.Select(attrs={"class": "form-control"}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))

    def __init__(self, *args, user, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["property"].queryset = Property.objects.filter(owner__profile__company=company).order_by("-created_at")
        self.fields["assigned_employee"].queryset = assignable_users_for(user)


class PropertyMatchForm(forms.Form):
    property = forms.ModelChoiceField(queryset=Property.objects.none(), widget=forms.Select(attrs={"class": "form-control"}))
    note = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Why this property matches"}))

    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["property"].queryset = Property.objects.filter(owner__profile__company=company).order_by("-created_at")


class MetaLeadSourceForm(forms.ModelForm):
    class Meta:
        model = MetaLeadSource
        fields = ["page_id", "page_name", "form_id", "form_name", "is_active", "default_assignee", "default_role", "field_mapping"]
        widgets = {
            "page_id": forms.TextInput(attrs={"class": "form-control"}),
            "page_name": forms.TextInput(attrs={"class": "form-control"}),
            "form_id": forms.TextInput(attrs={"class": "form-control"}),
            "form_name": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "default_assignee": forms.Select(attrs={"class": "form-control"}),
            "default_role": forms.Select(attrs={"class": "form-control"}),
            "field_mapping": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_assignee"].queryset = assignable_users_for(user)
        self.fields["default_assignee"].required = False
        self.fields["default_role"].required = False

    def clean_field_mapping(self):
        mapping = self.cleaned_data.get("field_mapping") or {}
        if isinstance(mapping, str):
            try:
                mapping = json.loads(mapping)
            except json.JSONDecodeError as exc:
                raise forms.ValidationError("Enter valid JSON for field mapping.") from exc
        if not isinstance(mapping, dict):
            raise forms.ValidationError("Field mapping must be a JSON object.")
        return mapping


class LeadAssignmentRuleForm(forms.ModelForm):
    class Meta:
        model = LeadAssignmentRule
        fields = ["name", "mode", "source", "city", "property_category", "default_assignee", "default_role", "priority", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "mode": forms.Select(attrs={"class": "form-control"}),
            "source": forms.Select(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "property_category": forms.Select(attrs={"class": "form-control"}),
            "default_assignee": forms.Select(attrs={"class": "form-control"}),
            "default_role": forms.Select(attrs={"class": "form-control"}),
            "priority": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_assignee"].queryset = assignable_users_for(user)
        self.fields["source"].required = False
        self.fields["city"].required = False
        self.fields["property_category"].required = False
        self.fields["default_assignee"].required = False
        self.fields["default_role"].required = False

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("mode")
        if mode == AssignmentMode.SOURCE and not cleaned.get("source"):
            self.add_error("source", "Select a source for source-based assignment.")
        if mode == AssignmentMode.CITY and not cleaned.get("city"):
            self.add_error("city", "Add a city for city-based assignment.")
        if mode == AssignmentMode.CATEGORY and not cleaned.get("property_category"):
            self.add_error("property_category", "Select a category for category-based assignment.")
        if mode in {AssignmentMode.ROUND_ROBIN, AssignmentMode.WORKLOAD} and not cleaned.get("default_role"):
            self.add_error("default_role", "Select a role for round-robin or workload assignment.")
        if mode not in {AssignmentMode.ROUND_ROBIN, AssignmentMode.WORKLOAD} and not cleaned.get("default_assignee") and not cleaned.get("default_role"):
            raise forms.ValidationError("Select either a default assignee or a default role.")
        return cleaned
