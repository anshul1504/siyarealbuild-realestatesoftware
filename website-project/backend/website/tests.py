from datetime import date
from django.test import TestCase
from django.urls import reverse
from .models import (
    AchievementCounter,
    Enquiry,
    GalleryItem,
    HeroBanner,
    PropertyCategory,
    PropertyListing,
    PropertySubmission,
    Service,
    SiteSettings,
    SiteVisitRequest,
    TeamMember,
    WhyChooseUs,
)


class WebsiteFlowTests(TestCase):
    def setUp(self):
        SiteSettings.objects.create()
        HeroBanner.objects.create(title="Admin controlled hero", image="hero/demo.jpg")
        HeroBanner.objects.create(title="Second hero", image="hero/demo-2.jpg")
        HeroBanner.objects.create(title="Third hero", image="hero/demo-3.jpg")
        AchievementCounter.objects.create(value=250, suffix="+", label="Happy Clients")
        Service.objects.create(
            title="Admin Service",
            description="Admin managed service",
            cta_label="Open Service",
            cta_url="/contact/",
        )
        WhyChooseUs.objects.create(
            title="Transparent Guidance", description="Clear property support"
        )
        self.category = PropertyCategory.objects.create(
            name="Residential Plot",
            slug="residential-plot",
            icon=PropertyCategory.Icon.PLOT,
        )
        self.property = PropertyListing.objects.create(
            title="Admin Property",
            category=self.category,
            location="Indore",
            summary="Admin summary",
            cover_image="properties/demo.jpg",
            is_featured=True,
        )

    def test_home_uses_admin_content(self):
        response = self.client.get(reverse("website:home"))
        self.assertContains(response, "Admin controlled hero")
        self.assertContains(response, "Admin Property")
        self.assertEqual(response.context["heroes"].count(), 3)
        self.assertContains(response, "Happy Clients")
        self.assertContains(response, 'data-counter="250"')
        self.assertContains(response, "Admin Service")
        self.assertContains(response, "Open Service")
        self.assertContains(
            response, "Everything you need to know before choosing a property"
        )
        self.assertContains(response, "Trusted by property buyers and investors")

    def test_home_limits_services_to_six_cards(self):
        for index in range(8):
            Service.objects.create(
                title=f"Extra Service {index}",
                description="Extra",
                sort_order=20 + index,
            )
        response = self.client.get(reverse("website:home"))
        self.assertEqual(len(response.context["services"]), 6)
        for label in ("Home", "About", "Properties", "Services", "Contact"):
            self.assertContains(response, label)
        self.assertContains(response, "Portal Login")
        self.assertNotContains(response, "Call Us")
        self.assertNotContains(response, "Enquire Now")

    def test_header_and_footer_use_admin_managed_content(self):
        settings = SiteSettings.objects.get()
        settings.post_property_label = "List Your Property"
        settings.footer_whatsapp_title = "WhatsApp Property Desk"
        settings.footer_credit_name = "Website Partner"
        settings.save()
        response = self.client.get(reverse("website:home"))
        self.assertContains(response, "List Your Property")
        self.assertContains(response, "WhatsApp Property Desk")
        self.assertContains(response, "Website Partner")
        self.assertContains(response, "Connect with us")
        self.assertNotContains(response, '{% include "website/partials/whatsapp_button.html" %}')
        self.assertNotContains(response, "{{ site_settings.company_name")

    def test_favicon_uses_admin_managed_image(self):
        settings = SiteSettings.objects.get()
        settings.favicon = "site/favicon.png"
        settings.save()
        response = self.client.get(reverse("website:home"))
        self.assertContains(response, 'rel="icon" href="/media/site/favicon.png"')

    def test_post_property_page_uses_admin_banner_image(self):
        settings = SiteSettings.objects.get()
        settings.post_property_banner_image = "site/post-property/banner/demo.jpg"
        settings.save()
        response = self.client.get(reverse("website:post_property"))
        self.assertContains(response, "site/post-property/banner/demo.jpg")

    def test_multi_page_routes_render(self):
        for route in (
            "website:about",
            "website:services",
            "website:project_list",
            "website:team",
            "website:gallery",
            "website:contact",
            "website:post_property",
        ):
            self.assertEqual(self.client.get(reverse(route)).status_code, 200)

    def test_public_property_submission_is_saved_for_review(self):
        response = self.client.post(
            reverse("website:post_property"),
            {
                "owner_name": "Property Owner",
                "phone": "9999999999",
                "email": "owner@example.com",
                "property_title": "Owner Residential Plot",
                "category": self.category.id,
                "location": "Indore",
                "expected_price": "2500000",
                "area_sqft": "1200",
                "description": "Clear title residential plot available for sale.",
            },
        )
        self.assertRedirects(response, reverse("website:post_property"))
        submission = PropertySubmission.objects.get(
            property_title="Owner Residential Plot"
        )
        self.assertEqual(submission.status, PropertySubmission.Status.PENDING)

    def test_services_page_renders_professional_sections(self):
        response = self.client.get(reverse("website:services"))
        self.assertContains(response, "Real-estate support built around your goals")
        self.assertContains(
            response, "A clear path from requirement to property decision"
        )
        self.assertContains(response, "Common questions about our property support")

    def test_team_page_renders_professional_sections(self):
        for index in range(13):
            TeamMember.objects.create(
                name=f"Team Member {index}", designation="Advisor", sort_order=index
            )
        response = self.client.get(reverse("website:team"))
        self.assertContains(response, "Property expertise at every step")
        self.assertNotContains(response, "team-contact")
        self.assertNotContains(response, "Team member biography")
        self.assertEqual(len(response.context["members"]), 12)
        self.assertTrue(response.context["page_obj"].has_next())

    def test_gallery_page_renders_professional_sections(self):
        for index in range(11):
            GalleryItem.objects.create(
                title=f"Gallery {index}", image="gallery/demo.jpg", sort_order=index
            )
        response = self.client.get(reverse("website:gallery"))
        self.assertContains(response, "Explore our work and property experiences")
        self.assertContains(response, "data-gallery-lightbox")
        self.assertEqual(len(response.context["items"]), 9)
        self.assertTrue(response.context["page_obj"].has_next())

    def test_contact_page_renders_professional_sections(self):
        response = self.client.get(reverse("website:contact"))
        self.assertNotContains(
            response, "Property guidance starts with a clear conversation"
        )
        self.assertContains(response, "Tell us your property requirement")
        self.assertContains(response, "Chat with us on WhatsApp")

    def test_about_page_renders_company_sections(self):
        response = self.client.get(reverse("website:about"))
        self.assertContains(response, "Purpose built around trust")
        self.assertContains(response, "Our Story")
        self.assertContains(response, "Messages From Our Founders")

    def test_home_handles_missing_property_image(self):
        self.property.cover_image = ""
        self.property.save(update_fields=["cover_image"])
        response = self.client.get(reverse("website:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin Property")

    def test_property_search_and_detail(self):
        response = self.client.get(reverse("website:property_list"), {"q": "Indore"})
        self.assertContains(response, "Admin Property")
        detail = self.client.get(self.property.get_absolute_url())
        self.assertContains(detail, "Admin summary")
        self.assertContains(detail, "Request Property Details")
        self.assertNotContains(detail, "Schedule a Site Visit")

    def test_property_detail_enquiry_is_saved(self):
        response = self.client.post(
            self.property.get_absolute_url(),
            {
                "enquiry_submit": "1",
                "name": "Detail Buyer",
                "phone": "9999999999",
                "interest": "Home",
                "message": "Send details",
                "property": self.property.id,
            },
        )
        self.assertRedirects(response, self.property.get_absolute_url())
        self.assertTrue(
            Enquiry.objects.filter(name="Detail Buyer", property=self.property).exists()
        )

    def test_property_listing_filters_and_paginates(self):
        for index in range(10):
            PropertyListing.objects.create(
                title=f"Property {index}",
                category=self.category,
                location="Indore",
                summary="Listing",
                cover_image="properties/demo.jpg",
                price=100000 + index,
                bedrooms=2,
            )
        response = self.client.get(
            reverse("website:property_list"),
            {"location": "Indore", "bedrooms": "2", "sort": "price_high"},
        )
        self.assertEqual(response.context["result_count"], 10)
        self.assertContains(response, "data-filter-open")
        self.assertContains(response, "data-property-filter")
        self.assertEqual(len(response.context["properties"]), 9)
        self.assertTrue(response.context["page_obj"].has_next())
        second_page = self.client.get(
            reverse("website:property_list"), {"location": "Indore", "page": 2}
        )
        self.assertEqual(len(second_page.context["properties"]), 2)

    def test_home_category_browser_links_to_filtered_properties(self):
        response = self.client.get(reverse("website:home"))
        self.assertNotContains(response, "Browse By Category")
        filtered = self.client.get(
            reverse("website:property_list"), {"category": self.category.slug}
        )
        self.assertContains(filtered, "Admin Property")

    def test_enquiry_is_saved_from_contact_page(self):
        response = self.client.post(
            reverse("website:contact"),
            {
                "name": "Buyer",
                "phone": "9999999999",
                "interest": "Plot",
                "message": "Call me",
            },
        )
        self.assertRedirects(response, reverse("website:contact"))
        self.assertTrue(Enquiry.objects.filter(name="Buyer").exists())

    def test_site_visit_request_is_saved(self):
        response = self.client.post(
            reverse("website:site_visit_request", args=[self.property.slug]),
            {
                "name": "Visitor",
                "phone": "9999999999",
                "preferred_date": date.today(),
                "property": self.property.id,
            },
        )
        self.assertRedirects(response, self.property.get_absolute_url())
        self.assertTrue(
            SiteVisitRequest.objects.filter(
                name="Visitor", property=self.property
            ).exists()
        )

    def test_home_site_visit_request_is_saved(self):
        response = self.client.post(
            reverse("website:home"),
            {
                "site_visit_submit": "1",
                "name": "Home Visitor",
                "phone": "9999999999",
                "preferred_date": date.today(),
                "property": self.property.id,
            },
        )
        self.assertRedirects(response, reverse("website:home"))
        self.assertTrue(
            SiteVisitRequest.objects.filter(
                name="Home Visitor", property=self.property
            ).exists()
        )
