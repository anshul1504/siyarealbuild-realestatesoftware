from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import CompanyProfile, Role, UserProfile
from properties.models import ColonyPlot, Property


class Command(BaseCommand):
    help = "Seed professional property inventory for local testing."

    def handle(self, *args, **options):
        User = get_user_model()
        company = CompanyProfile.objects.order_by("id").first()
        if not company:
            company = CompanyProfile.objects.create(name="Siya Real Build", email="info@siyarealbuild.local")

        owner = (
            User.objects.filter(profile__company=company, profile__role=Role.COMPANY_OWNER)
            .order_by("id")
            .first()
        )
        if not owner:
            owner, _ = User.objects.get_or_create(
                username="property.owner@siyarealbuild.local",
                defaults={"email": "property.owner@siyarealbuild.local", "first_name": "Property", "last_name": "Owner"},
            )
            profile, _ = UserProfile.objects.get_or_create(user=owner)
            profile.company = company
            profile.role = Role.COMPANY_OWNER
            profile.employee_code = profile.employee_code or "OWN-SEED"
            profile.save()

        colony, _ = Property.objects.update_or_create(
            owner=owner,
            title="Green Valley Premium Colony",
            defaults={
                "category": Property.Category.COLONY,
                "listing_for": Property.ListingFor.SALE,
                "status": Property.Status.AVAILABLE,
                "city": "Indore",
                "locality": "Super Corridor",
                "address": "Near Super Corridor main road",
                "landmark": "Metro Station Zone",
                "price": Decimal("1850000.00"),
                "price_per_sqft": Decimal("1850.00"),
                "area_sqft": 1000,
                "length_ft": Decimal("50.00"),
                "width_ft": Decimal("20.00"),
                "facing": "East",
                "road_width_ft": Decimal("30.00"),
                "colony_name": "Green Valley",
                "total_plots": 8,
                "available_plots": 8,
                "development_status": "Boundary wall, road, drainage, electricity poles",
                "amenities": "Gated entry, garden, street lights, water line",
                "amenity_count": 4,
                "garden_count": 1,
                "corner_plot_count": 2,
                "garden_facing_plot_count": 1,
                "plc_rules": "Corner plots include 10% PLC. Garden-facing plots include 7% PLC. Main road plots include 12% PLC.",
                "nearby_residential": "Premium apartments, row house projects, and developed residential colonies within 2 km.",
                "nearby_commercial": "Daily needs market, commercial shops, offices, and food court zone nearby.",
                "nearby_connectivity": "Super Corridor main road, proposed metro station, airport approach, and public transport access.",
                "nearby_education": "Schools, coaching centers, and college corridor within practical travel distance.",
                "nearby_healthcare": "Clinics, pharmacy stores, and multi-speciality hospital connectivity.",
                "nearby_landmarks": "Metro Station Zone, Super Corridor, airport road, and public garden belt.",
                "rera_number": "RERA-SEED-001",
                "tcp_approval_number": "TCP-SEED-001",
                "registry_status": "Registry ready",
                "legal_status": Property.LegalStatus.CLEAR,
                "contact_name": "Sales Desk",
                "contact_phone": "+91 9999999999",
            },
        )
        plot_specs = [
            ("A-01", 1000, "50", "20", "East", "30", "1850000", ColonyPlot.Status.AVAILABLE),
            ("A-02", 1200, "60", "20", "North", "30", "2220000", ColonyPlot.Status.AVAILABLE),
            ("A-03", 1500, "50", "30", "Corner", "40", "3000000", ColonyPlot.Status.HOLD),
            ("B-01", 900, "45", "20", "West", "25", "1575000", ColonyPlot.Status.AVAILABLE),
            ("B-02", 1000, "50", "20", "South", "25", "1750000", ColonyPlot.Status.SOLD),
            ("B-03", 1250, "50", "25", "Park Facing", "30", "2500000", ColonyPlot.Status.AVAILABLE),
            ("C-01", 1800, "60", "30", "Corner", "40", "3780000", ColonyPlot.Status.AVAILABLE),
            ("C-02", 1000, "50", "20", "East", "30", "1850000", ColonyPlot.Status.RESERVED),
        ]
        for plot_number, area, length, width, facing, road, price, status in plot_specs:
            ColonyPlot.objects.update_or_create(
                property=colony,
                plot_number=plot_number,
                defaults={
                    "area_sqft": area,
                    "length_ft": Decimal(length),
                    "width_ft": Decimal(width),
                    "facing": facing,
                    "road_width_ft": Decimal(road),
                    "price": Decimal(price),
                    "status": status,
                },
            )

        sample_properties = [
            {
                "title": "Skyline Heights 2 BHK Flat",
                "category": Property.Category.FLAT,
                "locality": "Vijay Nagar",
                "address": "Tower A, Ring Road",
                "price": Decimal("4600000.00"),
                "area_sqft": 1050,
                "carpet_area_sqft": 850,
                "builtup_area_sqft": 1050,
                "bedrooms": 2,
                "bathrooms": 2,
                "balconies": 1,
                "floor_number": 4,
                "total_floors": 10,
                "parking_count": 1,
                "furnishing": "Semi-furnished",
            },
            {
                "title": "Prime Corner Commercial Shop",
                "category": Property.Category.COMMERCIAL_SHOP,
                "locality": "MR 10",
                "address": "Main market frontage",
                "price": Decimal("7200000.00"),
                "area_sqft": 480,
                "builtup_area_sqft": 480,
                "road_width_ft": Decimal("60.00"),
                "parking_count": 2,
                "construction_status": "Ready",
            },
            {
                "title": "Resale Plot Near Bypass",
                "category": Property.Category.RESALE_PLOT,
                "locality": "Rau Bypass",
                "address": "Approved residential layout",
                "price": Decimal("3200000.00"),
                "price_per_sqft": Decimal("2000.00"),
                "area_sqft": 1600,
                "length_ft": Decimal("40.00"),
                "width_ft": Decimal("40.00"),
                "facing": "North",
                "road_width_ft": Decimal("30.00"),
            },
        ]
        for item in sample_properties:
            Property.objects.update_or_create(
                owner=owner,
                title=item["title"],
                defaults={
                    "listing_for": Property.ListingFor.SALE,
                    "status": Property.Status.AVAILABLE,
                    "city": "Indore",
                    "legal_status": Property.LegalStatus.CLEAR,
                    "registry_status": "Ready",
                    "contact_name": "Sales Desk",
                    "contact_phone": "+91 9999999999",
                    **item,
                },
            )

        self.stdout.write(self.style.SUCCESS("Seeded property inventory with colony plots and sample listings."))
