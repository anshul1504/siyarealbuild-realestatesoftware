from pathlib import Path
from django.core.files import File
from django.core.management.base import BaseCommand
from website.models import (
    AchievementCounter,
    FAQ,
    GalleryItem,
    HeroBanner,
    Project,
    PropertyCategory,
    PropertyImage,
    PropertyListing,
    Service,
    SiteSettings,
    TeamMember,
    Testimonial,
    WhyChooseUs,
)


class Command(BaseCommand):
    help = "Seed the standalone Siya public website with editable demo content."

    def handle(self, *args, **options):
        settings, _ = SiteSettings.objects.get_or_create(singleton_key=1)
        settings.phone = "+91 99999 99999"
        settings.whatsapp_number = "919999999999"
        settings.email = "info@siyarealbuild.com"
        settings.address = "Indore, Madhya Pradesh, India"
        settings.facebook_url = "https://www.facebook.com/"
        settings.instagram_url = "https://www.instagram.com/"
        settings.youtube_url = "https://www.youtube.com/"
        settings.save()
        source = (
            Path(__file__).resolve().parents[4]
            / "frontend"
            / "konkit"
            / "assets"
            / "img"
        )
        self.attach(settings, "about_image", source / "hero" / "hero-bg-2.jpg")
        self.attach(settings, "about_banner_image", source / "hero" / "hero-bg-1.jpg")
        self.attach(settings, "about_story_image", source / "hero" / "hero-bg-2.jpg")
        self.attach(settings, "mission_image", source / "menu" / "img-1.jpg")
        self.attach(settings, "vision_image", source / "menu" / "img-3.jpg")
        self.attach(settings, "values_image", source / "menu" / "img-5.jpg")
        self.attach(settings, "founder_image", source / "menu" / "img-6.jpg")
        self.attach(settings, "second_founder_image", source / "menu" / "img-7.jpg")
        self.attach(
            settings, "properties_banner_image", source / "hero" / "hero-bg-2.jpg"
        )
        self.attach(settings, "services_banner_image", source / "menu" / "img-3.jpg")
        self.attach(settings, "team_banner_image", source / "hero" / "hero-bg-1.jpg")
        self.attach(settings, "gallery_banner_image", source / "hero" / "hero-bg-2.jpg")
        self.attach(settings, "contact_banner_image", source / "menu" / "img-5.jpg")

        hero_samples = [
            (
                "Property that builds your future.",
                "Real estate with clarity and confidence",
                "Discover verified plots, homes and commercial opportunities with complete support.",
                source / "hero" / "hero-bg-1.jpg",
            ),
            (
                "Find the right place for your family.",
                "Trusted residential opportunities",
                "Explore selected homes and plots with guided site visits and transparent support.",
                source / "hero" / "hero-bg-2.jpg",
            ),
            (
                "Invest in locations built for growth.",
                "Commercial and investment properties",
                "Speak with our team about opportunities selected for long-term value.",
                source / "menu" / "img-3.jpg",
            ),
        ]
        for order, (title, eyebrow, description, image) in enumerate(hero_samples, 1):
            hero, _ = HeroBanner.objects.get_or_create(
                title=title,
                defaults={
                    "eyebrow": eyebrow,
                    "description": description,
                    "sort_order": order,
                },
            )
            self.attach(hero, "image", image)

        project, _ = Project.objects.get_or_create(
            name="Siya Premium Colony",
            defaults={
                "location": "Indore",
                "summary": "Planned residential plots with clear inventory and guided purchase support.",
                "description": "A thoughtfully planned residential colony for families and investors.",
                "status": Project.Status.ONGOING,
                "is_featured": True,
            },
        )
        self.attach(project, "cover_image", source / "hero" / "hero-bg-2.jpg")

        categories = {}
        for order, (slug, name, icon, description) in enumerate(
            [
                (
                    "residential-plot",
                    "Residential Plot",
                    PropertyCategory.Icon.PLOT,
                    "Verified residential plots and colony inventory.",
                ),
                (
                    "house-villa",
                    "House / Villa",
                    PropertyCategory.Icon.HOME,
                    "Ready and upcoming independent homes and villas.",
                ),
                (
                    "flat-apartment",
                    "Flat / Apartment",
                    PropertyCategory.Icon.BUILDING,
                    "Residential flats and apartment opportunities.",
                ),
                (
                    "commercial-property",
                    "Commercial Property",
                    PropertyCategory.Icon.COMMERCIAL,
                    "Commercial spaces selected for business growth.",
                ),
                (
                    "shop-showroom",
                    "Shop / Showroom",
                    PropertyCategory.Icon.COMMERCIAL,
                    "Retail shops and showroom opportunities.",
                ),
                (
                    "office-space",
                    "Office Space",
                    PropertyCategory.Icon.BUILDING,
                    "Professional office and workspace properties.",
                ),
                (
                    "warehouse",
                    "Warehouse",
                    PropertyCategory.Icon.BUILDING,
                    "Storage and logistics warehouse properties.",
                ),
                (
                    "farm-house",
                    "Farm House",
                    PropertyCategory.Icon.HOME,
                    "Farm houses and lifestyle investment properties.",
                ),
                (
                    "agricultural-land",
                    "Agricultural Land",
                    PropertyCategory.Icon.LAND,
                    "Agricultural land opportunities.",
                ),
                (
                    "industrial-land",
                    "Industrial Land",
                    PropertyCategory.Icon.LAND,
                    "Land suitable for industrial development.",
                ),
            ],
            1,
        ):
            categories[slug], _ = PropertyCategory.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "icon": icon,
                    "description": description,
                    "sort_order": order,
                    "is_active": True,
                },
            )

        samples = [
            (
                "Premium Residential Plots",
                categories["residential-plot"],
                "Indore",
                "Verified plots with planned roads and essential amenities.",
                source / "hero" / "hero-bg-1.jpg",
            ),
            (
                "Ready-to-Move Family Home",
                categories["house-villa"],
                "Indore",
                "A selected family home with strong local connectivity.",
                source / "hero" / "hero-bg-2.jpg",
            ),
            (
                "Commercial Investment Space",
                categories["commercial-property"],
                "Indore",
                "Commercial opportunity selected for visibility and growth.",
                source / "menu" / "img-3.jpg",
            ),
        ]
        for title, category, location, summary, image in samples:
            listing, _ = PropertyListing.objects.get_or_create(
                title=title,
                defaults={
                    "project": project,
                    "category": category,
                    "location": location,
                    "summary": summary,
                    "description": summary,
                    "is_featured": True,
                },
            )
            self.attach(listing, "cover_image", image)
        demo_categories = list(categories.values())
        demo_images = [
            source / "hero" / "hero-bg-1.jpg",
            source / "hero" / "hero-bg-2.jpg",
            source / "menu" / "img-1.jpg",
            source / "menu" / "img-2.jpg",
            source / "menu" / "img-3.jpg",
            source / "menu" / "img-5.jpg",
            source / "menu" / "img-6.jpg",
            source / "menu" / "img-7.jpg",
        ]
        locations = ["Indore", "Ujjain", "Dewas", "Bhopal"]
        for index in range(1, 18):
            category = demo_categories[index % len(demo_categories)]
            title = f"Siya {category.name} Opportunity {index:02d}"
            listing, _ = PropertyListing.objects.get_or_create(
                title=title,
                defaults={
                    "project": project,
                    "category": category,
                    "location": locations[index % len(locations)],
                    "summary": f"A selected {category.name.lower()} opportunity with reliable guidance and property support.",
                    "description": f"Explore this {category.name.lower()} opportunity with Siya Real Build.",
                    "price": 1500000 + (index * 275000),
                    "area_sqft": 750 + (index * 85),
                    "bedrooms": (index % 4) + 1
                    if category.icon
                    in {PropertyCategory.Icon.HOME, PropertyCategory.Icon.BUILDING}
                    else None,
                    "bathrooms": (index % 3) + 1
                    if category.icon
                    in {PropertyCategory.Icon.HOME, PropertyCategory.Icon.BUILDING}
                    else None,
                    "amenities": "Wide approach road\nWater supply\nElectricity connection\nSecure neighbourhood\nNearby schools and markets\nGuided documentation support",
                    "is_featured": index <= 4,
                    "sort_order": 10 + index,
                },
            )
            self.attach(listing, "cover_image", demo_images[index % len(demo_images)])
            self.attach(
                listing, "layout_image", demo_images[(index + 2) % len(demo_images)]
            )
        for listing in PropertyListing.objects.filter(is_active=True):
            for gallery_order, image in enumerate(demo_images[:3], 1):
                gallery, _ = PropertyImage.objects.get_or_create(
                    property=listing,
                    caption=f"{listing.title} view {gallery_order}",
                    defaults={"sort_order": gallery_order},
                )
                self.attach(gallery, "image", image)

        for order, (title, description, image) in enumerate(
            [
                (
                    "Property Advisory",
                    "Get practical recommendations based on your budget, preferred location, purpose and long-term plans.",
                    source / "menu" / "img-1.jpg",
                ),
                (
                    "Verified Property Selection",
                    "Explore shortlisted plots, homes and commercial spaces reviewed by our real-estate team.",
                    source / "menu" / "img-2.jpg",
                ),
                (
                    "Guided Site Visits",
                    "Visit selected properties with a dedicated advisor who explains location, pricing and availability.",
                    source / "menu" / "img-3.jpg",
                ),
                (
                    "Booking & Documentation",
                    "Receive structured support for booking, agreements, payment records and required documentation.",
                    source / "menu" / "img-5.jpg",
                ),
                (
                    "Investment Consultation",
                    "Understand growth potential, rental opportunity and suitable real-estate investment options.",
                    source / "menu" / "img-6.jpg",
                ),
                (
                    "After-Sales Support",
                    "Stay connected with our team for post-booking coordination and property-related assistance.",
                    source / "menu" / "img-7.jpg",
                ),
            ],
            1,
        ):
            service, _ = Service.objects.update_or_create(
                title=title,
                defaults={
                    "description": description,
                    "sort_order": order,
                    "cta_label": "Talk to an Advisor",
                    "cta_url": "/contact/",
                    "is_active": True,
                },
            )
            self.attach(service, "image", image)
        for order, (value, suffix, label) in enumerate(
            [
                (100, "+", "Verified Properties"),
                (500, "+", "Happy Clients"),
                (10, "+", "Years Experience"),
            ],
            1,
        ):
            AchievementCounter.objects.get_or_create(
                label=label,
                defaults={"value": value, "suffix": suffix, "sort_order": order},
            )
        for order, (title, description, image) in enumerate(
            [
                (
                    "Verified Property Options",
                    "Explore carefully reviewed properties with clear information before you make a decision.",
                    source / "menu" / "img-2.jpg",
                ),
                (
                    "Local Market Expertise",
                    "Get practical guidance from a team that understands locations, pricing and growth potential.",
                    source / "menu" / "img-3.jpg",
                ),
                (
                    "Transparent Process",
                    "Receive straightforward support through site visits, booking and documentation.",
                    source / "menu" / "img-5.jpg",
                ),
                (
                    "End-to-End Support",
                    "Stay connected with one dependable team from your first enquiry to after-sales assistance.",
                    source / "menu" / "img-7.jpg",
                ),
            ],
            1,
        ):
            item, _ = WhyChooseUs.objects.update_or_create(
                title=title,
                defaults={
                    "description": description,
                    "sort_order": order,
                    "is_active": True,
                },
            )
            self.attach(item, "image", image)
        for order, (name, role, quote) in enumerate(
            [
                (
                    "Rahul Sharma",
                    "Property Buyer",
                    "The Siya team made property shortlisting and site visits simple, clear and well coordinated.",
                ),
                (
                    "Neha Verma",
                    "Home Buyer",
                    "We received practical guidance at every step and found a property that matched our family needs.",
                ),
                (
                    "Amit Jain",
                    "Real Estate Investor",
                    "Their local market understanding helped me compare opportunities and make a confident investment decision.",
                ),
                (
                    "Priya Mehta",
                    "Plot Buyer",
                    "The team explained every property detail clearly and supported us throughout the booking process.",
                ),
                (
                    "Rohit Singh",
                    "Commercial Buyer",
                    "I appreciated the responsive communication and practical advice while selecting a commercial property.",
                ),
                (
                    "Sanjay Patel",
                    "Property Investor",
                    "Site visits were well planned and the documentation support made the complete process easier.",
                ),
            ],
            1,
        ):
            Testimonial.objects.update_or_create(
                client_name=name,
                defaults={
                    "client_role": role,
                    "quote": quote,
                    "sort_order": order,
                    "is_active": True,
                },
            )
        for order, (question, answer) in enumerate(
            [
                (
                    "How do I book a site visit?",
                    "Open any property page, submit the site visit form, and our team will confirm the schedule.",
                ),
                (
                    "How can I find a property within my budget?",
                    "Share your preferred location, property type and budget. Our advisors will help shortlist suitable options.",
                ),
                (
                    "Are the listed properties verified?",
                    "Our team reviews available property information and helps you understand the relevant details before proceeding.",
                ),
                (
                    "Do you provide booking and documentation support?",
                    "Yes. Our team coordinates the booking process and guides you through the required property documentation.",
                ),
                (
                    "Can I get help choosing between multiple properties?",
                    "Yes. We help compare location, pricing, purpose and long-term potential so you can make a confident decision.",
                ),
            ],
            1,
        ):
            FAQ.objects.update_or_create(
                question=question,
                defaults={"answer": answer, "sort_order": order, "is_active": True},
            )
        team_roles = [
            ("Aarav Sharma", "Senior Property Advisor"),
            ("Diya Verma", "Residential Property Advisor"),
            ("Arjun Patel", "Investment Consultant"),
            ("Meera Jain", "Client Relationship Manager"),
            ("Kabir Singh", "Site Visit Manager"),
            ("Ananya Gupta", "Documentation Specialist"),
            ("Rohan Mehta", "Commercial Property Advisor"),
            ("Isha Kapoor", "Property Research Analyst"),
            ("Vivaan Joshi", "Sales Manager"),
            ("Saanvi Mishra", "Customer Support Lead"),
            ("Aditya Rao", "Plot Sales Advisor"),
            ("Kiara Saxena", "Home Buying Advisor"),
            ("Reyansh Yadav", "Location Specialist"),
            ("Myra Choudhary", "Client Service Executive"),
            ("Atharv Desai", "Real Estate Consultant"),
            ("Aadhya Tiwari", "Booking Coordinator"),
            ("Dhruv Malhotra", "Business Development Manager"),
            ("Sara Khan", "Property Marketing Executive"),
            ("Krish Bansal", "After-Sales Coordinator"),
            ("Navya Agrawal", "Operations Executive"),
        ]
        for order, (name, designation) in enumerate(team_roles, 1):
            member, _ = TeamMember.objects.update_or_create(
                name=name,
                defaults={
                    "designation": designation,
                    "bio": "Committed to transparent property guidance, responsive communication and dependable client support.",
                    "phone": f"91999999{order:04d}",
                    "email": f"team{order}@siyarealbuild.com",
                    "sort_order": order,
                    "is_active": True,
                },
            )
            self.attach(member, "photo", demo_images[(order - 1) % len(demo_images)])
        for order, (title, category, image) in enumerate(
            [
                (
                    "Premium Colony Development",
                    GalleryItem.Category.PROJECT,
                    source / "hero" / "hero-bg-1.jpg",
                ),
                (
                    "Modern Property Opportunity",
                    GalleryItem.Category.PROJECT,
                    source / "hero" / "hero-bg-2.jpg",
                ),
                (
                    "Commercial Property Visit",
                    GalleryItem.Category.SITE_VISIT,
                    source / "menu" / "img-3.jpg",
                ),
            ],
            1,
        ):
            gallery, _ = GalleryItem.objects.get_or_create(
                title=title,
                defaults={
                    "category": category,
                    "caption": "Siya Real Build property experience.",
                    "sort_order": order,
                },
            )
            self.attach(gallery, "image", image)
        gallery_categories = [value for value, _ in GalleryItem.Category.choices]
        for index in range(1, 18):
            title = f"Siya Property Experience {index:02d}"
            gallery, _ = GalleryItem.objects.update_or_create(
                title=title,
                defaults={
                    "category": gallery_categories[index % len(gallery_categories)],
                    "caption": "A glimpse of Siya Real Build properties, visits and client experiences.",
                    "sort_order": 10 + index,
                    "is_active": True,
                },
            )
            self.attach(gallery, "image", demo_images[index % len(demo_images)])
        self.stdout.write(
            self.style.SUCCESS(
                "Website demo content is ready and editable from /superadmin/."
            )
        )

    def attach(self, instance, field_name, source):
        field = getattr(instance, field_name)
        if not field and source.exists():
            with source.open("rb") as handle:
                field.save(source.name, File(handle), save=True)
