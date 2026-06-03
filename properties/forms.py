from django import forms

from .models import Property


class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = ["title", "property_type", "city", "address", "price", "area_sqft", "bedrooms", "status"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Property title"}),
            "property_type": forms.Select(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control", "placeholder": "City"}),
            "address": forms.TextInput(attrs={"class": "form-control", "placeholder": "Street, locality, landmark"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Price"}),
            "area_sqft": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Area in sqft"}),
            "bedrooms": forms.NumberInput(attrs={"class": "form-control", "placeholder": "Bedrooms"}),
            "status": forms.Select(attrs={"class": "form-control"}),
        }
