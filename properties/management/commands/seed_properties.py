from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import CompanyProfile, Role, UserProfile
from properties.models import ColonyPlot, Property, PropertyDeveloper
from properties.services import sync_available_plots


CONTACT = {
    "contact_name": "Siya Sales Desk",
    "contact_phone": "+91 9999999999",
    "legal_status": Property.LegalStatus.CLEAR,
    "registry_status": "Registry ready",
    "is_archived": False,
}


class Command(BaseCommand):
    help = "Seed complete property inventory samples for local testing."

    def handle(self, *args, **options):
        company = self._company()
        owner = self._owner(company)
        developer = self._developer(company)

        colony = self._seed_colony(owner, developer)
        self._seed_colony_plots(colony)
        self._seed_flats(owner, developer)
        self._seed_all_categories(owner, developer)

        total_properties = Property.objects.filter(owner=owner, is_archived=False).count()
        total_plots = ColonyPlot.objects.filter(property=colony).count()
        self.stdout.write(self.style.SUCCESS(f"Seeded {total_properties} active properties and {total_plots} colony plot rows."))

    def _company(self):
        company = CompanyProfile.objects.order_by("id").first()
        if company:
            return company
        return CompanyProfile.objects.create(name="Siya Real Build", email="info@siyarealbuild.local")

    def _owner(self, company):
        User = get_user_model()
        owner = User.objects.filter(profile__company=company, profile__role=Role.COMPANY_OWNER).order_by("id").first()
        if owner:
            return owner
        owner, _ = User.objects.get_or_create(
            username="property.owner@siyarealbuild.local",
            defaults={"email": "property.owner@siyarealbuild.local", "first_name": "Property", "last_name": "Owner"},
        )
        profile, _ = UserProfile.objects.get_or_create(user=owner)
        profile.company = company
        profile.role = Role.COMPANY_OWNER
        profile.employee_code = profile.employee_code or "OWN-SEED"
        profile.save()
        return owner

    def _developer(self, company):
        developer, _ = PropertyDeveloper.objects.update_or_create(
            company=company,
            name="Siya Sample Developers",
            defaults={
                "company_name": "Siya Sample Developers Pvt. Ltd.",
                "contact_person": "Amit Sharma",
                "mobile": "+91 9888888888",
                "email": "developer@siyarealbuild.local",
                "office_address": "Vijay Nagar, Indore",
                "rera_number": "RERA-SEED-DEV",
                "notes": "Seed developer for demo property inventory.",
                "is_active": True,
            },
        )
        return developer

    def _base(self, owner, developer, **overrides):
        data = {
            "owner": owner,
            "developer": developer,
            "listing_for": Property.ListingFor.SALE,
            "status": Property.Status.AVAILABLE,
            "city": "Indore",
            "landmark": "Seed demo inventory",
            "rera_number": "RERA-SEED-DEMO",
            "tcp_approval_number": "TCP-SEED-DEMO",
            "nearby_residential": "Developed residential pockets and active townships nearby.",
            "nearby_commercial": "Retail shops, offices, food outlets, and daily needs market nearby.",
            "nearby_connectivity": "Main road, public transport, airport road, and railway connectivity.",
            "nearby_education": "Schools, colleges, and coaching zones within practical distance.",
            "nearby_healthcare": "Clinics, pharmacies, and multi-speciality hospital access.",
            "nearby_landmarks": "Main road, market, garden, and commercial zone.",
            **CONTACT,
        }
        data.update(overrides)
        return data

    def _upsert_property(self, owner, developer, title, **defaults):
        data = self._base(owner, developer, **defaults)
        owner_obj = data.pop("owner")
        return Property.objects.update_or_create(owner=owner_obj, title=title, defaults=data)[0]

    def _seed_colony(self, owner, developer):
        return self._upsert_property(
            owner,
            developer,
            "Green Valley Premium Colony - 30 Plot Inventory",
            category=Property.Category.COLONY,
            locality="Super Corridor",
            address="Near Super Corridor main road, Indore",
            price=Decimal("1850000.00"),
            price_per_sqft=Decimal("1850.00"),
            area_sqft=45000,
            length_ft=Decimal("300.00"),
            width_ft=Decimal("150.00"),
            facing=ColonyPlot.Facing.EAST,
            road_width_ft=Decimal("40.00"),
            colony_name="Green Valley Premium Colony",
            total_plots=30,
            available_plots=30,
            development_status=Property.DevelopmentStatus.UNDER_DEVELOPMENT,
            amenities="Gated entry, boundary wall, garden, kids play area, CCTV, water connection, drainage, cement road, street lights",
            selected_amenities=["boundary_wall", "main_gate", "security", "garden", "kids_play_area", "water_connection", "drainage", "cement_road", "street_lights"],
            custom_amenities="Temple zone\nVisitor parking\nRainwater harvesting",
            amenity_count=12,
            garden_count=2,
            corner_plot_count=6,
            garden_facing_plot_count=8,
            plc_rules="Corner PLC 10%, garden-facing PLC 7%, main-road PLC 12%, wide-road PLC 5%.",
            base_rate_per_sqft=Decimal("1850.00"),
            residential_rate_per_sqft=Decimal("1850.00"),
            commercial_rate_per_sqft=Decimal("2500.00"),
            lig_rate_per_sqft=Decimal("1600.00"),
            mig_rate_per_sqft=Decimal("1750.00"),
            hig_rate_per_sqft=Decimal("2100.00"),
            ews_rate_per_sqft=Decimal("1450.00"),
            electricity_charge=Decimal("5.00"),
            maintenance_charge=Decimal("5.00"),
            development_charge=Decimal("10.00"),
            registry_charge=Decimal("8.00"),
            other_charge=Decimal("2.00"),
            corner_plc_rate=Decimal("5.00"),
            garden_facing_plc_rate=Decimal("3.00"),
            main_road_plc_rate=Decimal("4.00"),
            wide_road_plc_rate=Decimal("2.00"),
            rera_number="RERA-SEED-COLONY-030",
            tcp_approval_number="TCP-SEED-COLONY-030",
        )

    def _seed_colony_plots(self, colony):
        statuses = [
            ColonyPlot.Status.AVAILABLE,
            ColonyPlot.Status.AVAILABLE,
            ColonyPlot.Status.AVAILABLE,
            ColonyPlot.Status.HOLD,
            ColonyPlot.Status.RESERVED,
            ColonyPlot.Status.BOOKED,
            ColonyPlot.Status.SOLD,
        ]
        categories = [
            ColonyPlot.PlotCategory.RESIDENTIAL,
            ColonyPlot.PlotCategory.RESIDENTIAL,
            ColonyPlot.PlotCategory.COMMERCIAL,
            ColonyPlot.PlotCategory.LIG,
            ColonyPlot.PlotCategory.MIG,
            ColonyPlot.PlotCategory.HIG,
            ColonyPlot.PlotCategory.EWS,
            ColonyPlot.PlotCategory.PREMIUM,
        ]
        facings = [
            ColonyPlot.Facing.EAST,
            ColonyPlot.Facing.WEST,
            ColonyPlot.Facing.NORTH,
            ColonyPlot.Facing.SOUTH,
            ColonyPlot.Facing.CORNER,
            ColonyPlot.Facing.GARDEN_FACING,
        ]
        for index in range(1, 31):
            block = chr(64 + ((index - 1) // 10) + 1)
            plot_no = f"{block}-{index:02d}"
            area = 800 + ((index % 6) * 100)
            category = categories[index % len(categories)]
            base_rate = Decimal("2500.00") if category == ColonyPlot.PlotCategory.COMMERCIAL else Decimal("1850.00")
            is_corner = index % 5 == 0
            is_garden = index % 4 == 0
            is_main_road = index % 7 == 0
            road_width = Decimal("25.00") + Decimal((index % 4) * 5)
            plc_rate = Decimal("0.00")
            if is_corner:
                plc_rate += Decimal("5.00")
            if is_garden:
                plc_rate += Decimal("3.00")
            if is_main_road:
                plc_rate += Decimal("4.00")
            ColonyPlot.objects.update_or_create(
                property=colony,
                plot_number=plot_no,
                defaults={
                    "plot_category": category,
                    "custom_category": "Duplex-size plot" if category == ColonyPlot.PlotCategory.CUSTOM else "",
                    "block": block,
                    "area_sqft": area,
                    "length_ft": Decimal("40.00") + Decimal(index % 5),
                    "width_ft": Decimal("20.00") + Decimal(index % 4),
                    "facing": facings[index % len(facings)],
                    "road_width_ft": road_width,
                    "base_rate": base_rate,
                    "plc_rate": plc_rate,
                    "extra_charges": Decimal("45000.00"),
                    "is_corner": is_corner,
                    "is_garden_facing": is_garden,
                    "is_main_road": is_main_road,
                    "is_wide_road": road_width >= Decimal("40.00"),
                    "status": statuses[index % len(statuses)],
                    "notes": "Seeded 30-plot colony inventory.",
                },
            )
        sync_available_plots(colony)

    def _seed_flats(self, owner, developer):
        unit_types = [
            ("1 BHK Compact", 1, 1, 620, 510, Decimal("2800000.00")),
            ("2 BHK Standard", 2, 2, 980, 810, Decimal("4600000.00")),
            ("2 BHK Premium", 2, 2, 1120, 910, Decimal("5400000.00")),
            ("3 BHK Family", 3, 3, 1480, 1210, Decimal("7600000.00")),
            ("3 BHK Premium", 3, 3, 1680, 1360, Decimal("9200000.00")),
            ("4 BHK Penthouse", 4, 4, 2400, 1950, Decimal("15500000.00")),
        ]
        for index in range(1, 31):
            label, bedrooms, bathrooms, builtup, carpet, price = unit_types[(index - 1) % len(unit_types)]
            tower = "A" if index <= 10 else "B" if index <= 20 else "C"
            floor = ((index - 1) % 10) + 1
            self._upsert_property(
                owner,
                developer,
                f"Skyline Heights {label} Flat {tower}-{floor:02d}",
                category=Property.Category.FLAT,
                locality="Vijay Nagar",
                address=f"Skyline Heights Tower {tower}, Floor {floor}, AB Road, Indore",
                price=price + Decimal(index * 25000),
                price_per_sqft=Decimal("4300.00") + Decimal((index % 5) * 100),
                area_sqft=builtup,
                carpet_area_sqft=carpet,
                builtup_area_sqft=builtup,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                balconies=1 if bedrooms <= 2 else 2,
                floor_number=floor,
                total_floors=12,
                parking_count=1 if bedrooms <= 2 else 2,
                furnishing="Semi-furnished" if index % 2 else "Unfurnished",
                construction_status="Ready",
                possession_status="Immediate",
                rera_number=f"RERA-SEED-FLAT-{index:02d}",
                tcp_approval_number=f"TCP-SEED-FLAT-{index:02d}",
            )

    def _seed_all_categories(self, owner, developer):
        samples = [
            {
                "title": "Silver Park Individual Residential Plot",
                "category": Property.Category.PLOT,
                "locality": "Rau Bypass",
                "address": "Silver Park approved layout, Rau Bypass",
                "price": Decimal("3200000.00"),
                "price_per_sqft": Decimal("2000.00"),
                "area_sqft": 1600,
                "length_ft": Decimal("40.00"),
                "width_ft": Decimal("40.00"),
                "facing": "North",
                "road_width_ft": Decimal("30.00"),
            },
            {
                "title": "Scheme 140 Resale Plot",
                "category": Property.Category.RESALE_PLOT,
                "locality": "Scheme 140",
                "address": "Residential resale plot near service road",
                "price": Decimal("5400000.00"),
                "price_per_sqft": Decimal("3000.00"),
                "area_sqft": 1800,
                "length_ft": Decimal("45.00"),
                "width_ft": Decimal("40.00"),
                "facing": "East",
                "road_width_ft": Decimal("40.00"),
            },
            {
                "title": "Saket Nagar Residential House",
                "category": Property.Category.RESIDENTIAL_HOUSE,
                "locality": "Saket Nagar",
                "address": "Independent house near garden",
                "price": Decimal("12500000.00"),
                "area_sqft": 2200,
                "builtup_area_sqft": 2600,
                "carpet_area_sqft": 2100,
                "bedrooms": 4,
                "bathrooms": 4,
                "balconies": 2,
                "parking_count": 2,
                "furnishing": "Fully furnished",
                "construction_status": "Ready",
                "possession_status": "Immediate",
            },
            {
                "title": "MR 10 Prime Commercial Shop",
                "category": Property.Category.COMMERCIAL_SHOP,
                "locality": "MR 10",
                "address": "Main road commercial frontage",
                "price": Decimal("7200000.00"),
                "area_sqft": 480,
                "builtup_area_sqft": 480,
                "road_width_ft": Decimal("60.00"),
                "parking_count": 2,
                "construction_status": "Ready",
            },
            {
                "title": "Nipania Premium Row House",
                "category": Property.Category.ROW_HOUSE,
                "locality": "Nipania",
                "address": "Gated row house campus",
                "price": Decimal("9800000.00"),
                "area_sqft": 1800,
                "builtup_area_sqft": 2200,
                "carpet_area_sqft": 1750,
                "bedrooms": 3,
                "bathrooms": 3,
                "balconies": 2,
                "parking_count": 2,
                "construction_status": "Ready",
            },
            {
                "title": "Bypass Luxury Villa",
                "category": Property.Category.VILLA,
                "locality": "Bypass Road",
                "address": "Luxury villa community near bypass",
                "price": Decimal("24500000.00"),
                "area_sqft": 4200,
                "builtup_area_sqft": 5200,
                "carpet_area_sqft": 4300,
                "bedrooms": 5,
                "bathrooms": 5,
                "balconies": 3,
                "parking_count": 3,
                "furnishing": "Luxury furnished",
            },
            {
                "title": "Mhow Road Farm House",
                "category": Property.Category.FARM_HOUSE,
                "locality": "Mhow Road",
                "address": "Farm house with lawn and pool provision",
                "price": Decimal("18500000.00"),
                "area_sqft": 22000,
                "builtup_area_sqft": 2600,
                "carpet_area_sqft": 2100,
                "bedrooms": 3,
                "bathrooms": 3,
                "balconies": 2,
                "parking_count": 5,
                "furnishing": "Semi-furnished",
            },
            {
                "title": "Vijay Nagar Corporate Office",
                "category": Property.Category.OFFICE,
                "locality": "Vijay Nagar",
                "address": "Commercial tower office space",
                "listing_for": Property.ListingFor.LEASE,
                "price": Decimal("125000.00"),
                "price_per_sqft": Decimal("85.00"),
                "area_sqft": 1450,
                "builtup_area_sqft": 1450,
                "parking_count": 3,
                "construction_status": "Ready",
            },
            {
                "title": "Dewas Naka Warehouse",
                "category": Property.Category.WAREHOUSE,
                "locality": "Dewas Naka",
                "address": "Warehouse with loading bay",
                "listing_for": Property.ListingFor.RENT,
                "price": Decimal("180000.00"),
                "price_per_sqft": Decimal("30.00"),
                "area_sqft": 6000,
                "builtup_area_sqft": 6000,
                "road_width_ft": Decimal("80.00"),
                "construction_status": "Ready",
            },
            {
                "title": "Sanwer Agricultural Land",
                "category": Property.Category.AGRICULTURAL_LAND,
                "locality": "Sanwer",
                "address": "Agricultural land near main village road",
                "price": Decimal("36000000.00"),
                "price_per_sqft": Decimal("450.00"),
                "area_sqft": 80000,
                "length_ft": Decimal("400.00"),
                "width_ft": Decimal("200.00"),
                "facing": "Main road",
                "road_width_ft": Decimal("35.00"),
                "khasra_number": "SANWER-SEED-101",
            },
        ]
        for index, sample in enumerate(samples, start=1):
            sample.setdefault("rera_number", f"RERA-SEED-CAT-{index:02d}")
            sample.setdefault("tcp_approval_number", f"TCP-SEED-CAT-{index:02d}")
            title = sample.pop("title")
            self._upsert_property(owner, developer, title, **sample)
