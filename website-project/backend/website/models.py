from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class OrderedActiveModel(models.Model):
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["sort_order", "id"]


class SiteSettings(models.Model):
    singleton_key = models.PositiveSmallIntegerField(
        default=1, unique=True, editable=False
    )
    company_name = models.CharField(max_length=120, default="Siya Real Build")
    tagline = models.CharField(
        max_length=180, default="Property that builds your future."
    )
    about_title = models.CharField(
        max_length=180, default="Local expertise. Transparent property decisions."
    )
    about_text = models.TextField(
        default="We help buyers, investors and businesses find the right real-estate opportunity."
    )
    about_image = models.ImageField(upload_to="site/about/", blank=True)
    about_banner_image = models.ImageField(upload_to="site/about/banner/", blank=True)
    about_story_title = models.CharField(
        max_length=220, default="Building trust through better property decisions"
    )
    about_story_text = models.TextField(
        default="Siya Real Build helps buyers and investors discover suitable properties with transparent guidance, local expertise and dependable support."
    )
    about_story_image = models.ImageField(upload_to="site/about/story/", blank=True)
    mission_title = models.CharField(max_length=120, default="Our Mission")
    mission_text = models.TextField(
        default="To make every property journey clear, reliable and confidently informed."
    )
    mission_image = models.ImageField(upload_to="site/about/mission/", blank=True)
    vision_title = models.CharField(max_length=120, default="Our Vision")
    vision_text = models.TextField(
        default="To become a trusted real-estate partner known for transparency, quality opportunities and lasting client relationships."
    )
    vision_image = models.ImageField(upload_to="site/about/vision/", blank=True)
    values_title = models.CharField(max_length=120, default="Our Values")
    values_text = models.TextField(
        default="Integrity, client-first guidance, local expertise, clear communication and dependable support."
    )
    values_image = models.ImageField(upload_to="site/about/values/", blank=True)
    founder_name = models.CharField(max_length=120, default="Founder, Siya Real Build")
    founder_designation = models.CharField(
        max_length=120, default="Founder & Managing Director"
    )
    founder_message = models.TextField(
        default="Our purpose is to help every client make a confident property decision through honest guidance, clear information and dependable support."
    )
    founder_image = models.ImageField(upload_to="site/about/founder/", blank=True)
    second_founder_name = models.CharField(
        max_length=120, default="Co-Founder, Siya Real Build"
    )
    second_founder_designation = models.CharField(
        max_length=120, default="Co-Founder & Director"
    )
    second_founder_message = models.TextField(
        default="We are committed to building lasting client relationships through transparent service, quality opportunities and responsive support."
    )
    second_founder_image = models.ImageField(
        upload_to="site/about/founder/", blank=True
    )
    about_eyebrow = models.CharField(max_length=120, default="About Siya Real Build")
    about_button_label = models.CharField(max_length=60, default="Know More About Us")
    services_eyebrow = models.CharField(max_length=120, default="How We Help")
    services_title = models.CharField(
        max_length=180, default="A simpler property journey"
    )
    services_banner_image = models.ImageField(
        upload_to="site/services/banner/", blank=True
    )
    team_banner_image = models.ImageField(upload_to="site/team/banner/", blank=True)
    gallery_banner_image = models.ImageField(
        upload_to="site/gallery/banner/", blank=True
    )
    contact_banner_image = models.ImageField(
        upload_to="site/contact/banner/", blank=True
    )
    post_property_banner_image = models.ImageField(
        upload_to="site/post-property/banner/", blank=True
    )
    office_map_url = models.URLField(blank=True)
    business_hours = models.CharField(
        max_length=180, default="Monday - Saturday, 10:00 AM - 7:00 PM"
    )
    properties_eyebrow = models.CharField(
        max_length=120, default="Featured Opportunities"
    )
    properties_title = models.CharField(
        max_length=180, default="Find your next property"
    )
    properties_banner_image = models.ImageField(
        upload_to="site/properties/banner/", blank=True
    )
    why_choose_eyebrow = models.CharField(max_length=120, default="Why Choose Siya")
    why_choose_title = models.CharField(
        max_length=180, default="Property guidance you can trust"
    )
    why_choose_text = models.CharField(
        max_length=300,
        default="Clear advice, verified opportunities and dependable support at every step.",
    )
    contact_eyebrow = models.CharField(max_length=120, default="Start a Conversation")
    contact_title = models.CharField(
        max_length=180, default="Tell us what you are looking for."
    )
    contact_text = models.CharField(
        max_length=300,
        default="Share your requirement and our property team will contact you.",
    )
    portal_login_label = models.CharField(max_length=60, default="Portal Login")
    portal_login_url = models.CharField(
        max_length=300, default="#", help_text="Add the CRM/portal login URL here."
    )
    post_property_label = models.CharField(max_length=60, default="Post Property")
    footer_explore_title = models.CharField(max_length=80, default="Explore")
    footer_property_types_title = models.CharField(
        max_length=80, default="Property Types"
    )
    footer_contact_title = models.CharField(max_length=80, default="Contact")
    footer_whatsapp_eyebrow = models.CharField(max_length=80, default="Scan & Chat")
    footer_whatsapp_title = models.CharField(
        max_length=120, default="Connect on WhatsApp"
    )
    footer_whatsapp_text = models.CharField(
        max_length=220, default="Get property details and schedule a site visit."
    )
    footer_whatsapp_button = models.CharField(
        max_length=80, default="Start Conversation"
    )
    footer_credit_text = models.CharField(
        max_length=120, default="Design and developed by"
    )
    footer_credit_name = models.CharField(max_length=120, default="The Webfix")
    footer_credit_url = models.URLField(blank=True)
    logo = models.ImageField(upload_to="site/", blank=True)
    favicon = models.ImageField(upload_to="site/", blank=True)
    phone = models.CharField(max_length=30, default="+91 99999 99999")
    whatsapp_number = models.CharField(max_length=30, default="919999999999")
    email = models.EmailField(default="info@siyarealbuild.com")
    address = models.TextField(blank=True)
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    seo_title = models.CharField(
        max_length=180, default="Siya Real Build | Property That Builds Your Future"
    )
    seo_description = models.CharField(
        max_length=300,
        default="Trusted plots, homes and commercial property opportunities.",
    )

    def save(self, *args, **kwargs):
        self.singleton_key = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.company_name


class HeroBanner(OrderedActiveModel):
    eyebrow = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="hero/")
    primary_label = models.CharField(max_length=50, default="Explore Properties")
    primary_url = models.CharField(max_length=200, default="/properties/")

    def __str__(self):
        return self.title


class Project(OrderedActiveModel):
    class Status(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        ONGOING = "ongoing", "Ongoing"
        COMPLETED = "completed", "Completed"

    name = models.CharField(max_length=160)
    slug = models.SlugField(unique=True, blank=True)
    location = models.CharField(max_length=180)
    summary = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    cover_image = models.ImageField(upload_to="projects/")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ONGOING
    )
    starting_price = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    map_url = models.URLField(blank=True)
    is_featured = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("website:project_detail", args=[self.slug])

    def __str__(self):
        return self.name


class ProjectImage(OrderedActiveModel):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="gallery"
    )
    image = models.ImageField(upload_to="projects/gallery/")
    caption = models.CharField(max_length=180, blank=True)

    def __str__(self):
        return f"{self.project} image"


class PropertyCategory(OrderedActiveModel):
    class Icon(models.TextChoices):
        PLOT = "plot", "Plot"
        HOME = "home", "Home"
        BUILDING = "building", "Building"
        COMMERCIAL = "commercial", "Commercial"
        LAND = "land", "Land"

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.CharField(max_length=240, blank=True)
    icon = models.CharField(max_length=30, choices=Icon.choices, default=Icon.HOME)

    def __str__(self):
        return self.name


class PropertyListing(OrderedActiveModel):
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="properties",
    )
    title = models.CharField(max_length=180)
    slug = models.SlugField(unique=True, blank=True)
    category = models.ForeignKey(
        PropertyCategory, on_delete=models.PROTECT, related_name="properties"
    )
    location = models.CharField(max_length=180)
    summary = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    cover_image = models.ImageField(upload_to="properties/")
    price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    area_sqft = models.PositiveIntegerField(null=True, blank=True)
    bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    bathrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    amenities = models.TextField(blank=True, help_text="Enter one amenity per line.")
    layout_image = models.ImageField(upload_to="properties/layouts/", blank=True)
    map_url = models.URLField(blank=True)
    is_featured = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("website:property_detail", args=[self.slug])

    def __str__(self):
        return self.title


class PropertyImage(OrderedActiveModel):
    property = models.ForeignKey(
        PropertyListing, on_delete=models.CASCADE, related_name="gallery"
    )
    image = models.ImageField(upload_to="properties/gallery/")
    caption = models.CharField(max_length=180, blank=True)


class PropertySubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    owner_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    property_title = models.CharField(max_length=180)
    category = models.ForeignKey(PropertyCategory, on_delete=models.PROTECT)
    location = models.CharField(max_length=180)
    expected_price = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    area_sqft = models.PositiveIntegerField(null=True, blank=True)
    bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    bathrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    description = models.TextField()
    image = models.ImageField(upload_to="property-submissions/", blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.property_title} - {self.owner_name}"


class Service(OrderedActiveModel):
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=300)
    image = models.ImageField(upload_to="services/", blank=True)
    cta_label = models.CharField(max_length=50, default="Learn More")
    cta_url = models.CharField(max_length=200, default="/contact/")

    def __str__(self):
        return self.title


class WhyChooseUs(OrderedActiveModel):
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=300)
    image = models.ImageField(upload_to="why-choose/", blank=True)

    def __str__(self):
        return self.title


class AchievementCounter(OrderedActiveModel):
    value = models.PositiveIntegerField()
    suffix = models.CharField(max_length=12, blank=True, help_text="Examples: +, %, K+")
    label = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.value}{self.suffix} {self.label}"


class Testimonial(OrderedActiveModel):
    client_name = models.CharField(max_length=120)
    client_role = models.CharField(max_length=120, blank=True)
    quote = models.TextField()
    photo = models.ImageField(upload_to="testimonials/", blank=True)

    def __str__(self):
        return self.client_name


class TeamMember(OrderedActiveModel):
    name = models.CharField(max_length=120)
    designation = models.CharField(max_length=120)
    bio = models.TextField(blank=True)
    photo = models.ImageField(upload_to="team/", blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    linkedin_url = models.URLField(blank=True)

    def __str__(self):
        return self.name


class GalleryItem(OrderedActiveModel):
    class Category(models.TextChoices):
        PROJECT = "project", "Project"
        SITE_VISIT = "site_visit", "Site Visit"
        EVENT = "event", "Event"
        OFFICE = "office", "Office"
        OTHER = "other", "Other"

    title = models.CharField(max_length=160)
    category = models.CharField(
        max_length=30, choices=Category.choices, default=Category.PROJECT
    )
    image = models.ImageField(upload_to="gallery/")
    caption = models.CharField(max_length=260, blank=True)

    def __str__(self):
        return self.title


class FAQ(OrderedActiveModel):
    question = models.CharField(max_length=220)
    answer = models.TextField()

    def __str__(self):
        return self.question


class Enquiry(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        CLOSED = "closed", "Closed"

    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    interest = models.CharField(max_length=120, blank=True)
    message = models.TextField(blank=True)
    property = models.ForeignKey(
        PropertyListing, on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} - {self.phone}"


class SiteVisitRequest(models.Model):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    property = models.ForeignKey(
        PropertyListing, on_delete=models.SET_NULL, null=True, blank=True
    )
    preferred_date = models.DateField()
    message = models.TextField(blank=True)
    is_confirmed = models.BooleanField(default=False)
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Visit: {self.name} - {self.preferred_date}"
