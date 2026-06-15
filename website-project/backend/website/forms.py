"""Forms used by public lead-capture workflows."""

from django import forms

from .models import Enquiry, PropertySubmission, SiteVisitRequest


class StyledFormMixin:
    """Apply the shared frontend form-control class to every field."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class EnquiryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Enquiry
        fields = ["name", "phone", "email", "interest", "message", "property"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 4}),
            "property": forms.HiddenInput(),
        }


class SiteVisitRequestForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SiteVisitRequest
        fields = ["name", "phone", "email", "property", "preferred_date", "message"]
        widgets = {
            "preferred_date": forms.DateInput(attrs={"type": "date"}),
            "message": forms.Textarea(attrs={"rows": 3}),
            "property": forms.HiddenInput(),
        }


class HomeSiteVisitForm(SiteVisitRequestForm):
    """Site-visit form variant that lets homepage visitors select a property."""

    class Meta(SiteVisitRequestForm.Meta):
        widgets = {
            "preferred_date": forms.DateInput(attrs={"type": "date"}),
            "message": forms.Textarea(attrs={"rows": 3}),
            "property": forms.Select(),
        }


class PropertySubmissionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PropertySubmission
        fields = [
            "owner_name",
            "phone",
            "email",
            "property_title",
            "category",
            "location",
            "expected_price",
            "area_sqft",
            "bedrooms",
            "bathrooms",
            "description",
            "image",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}
