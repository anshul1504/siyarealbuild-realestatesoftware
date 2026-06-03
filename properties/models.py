from django.conf import settings
from django.db import models


class Property(models.Model):
    STATUS_CHOICES = [
        ("available", "Available"),
        ("negotiation", "Negotiation"),
        ("sold", "Sold"),
        ("rented", "Rented"),
    ]
    TYPE_CHOICES = [
        ("apartment", "Apartment"),
        ("villa", "Villa"),
        ("plot", "Plot"),
        ("commercial", "Commercial"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="properties")
    title = models.CharField(max_length=160)
    property_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    city = models.CharField(max_length=80)
    address = models.CharField(max_length=220)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    area_sqft = models.PositiveIntegerField()
    bedrooms = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="available")
    lead_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

# Create your models here.
