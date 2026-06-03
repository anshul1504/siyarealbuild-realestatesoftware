from django.contrib import admin

from .models import Property


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("title", "city", "property_type", "price", "status", "owner")
    list_filter = ("status", "property_type", "city")
    search_fields = ("title", "city", "address")

# Register your models here.
