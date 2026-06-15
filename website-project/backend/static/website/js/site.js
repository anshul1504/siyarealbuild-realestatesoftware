// Mobile navigation
const toggle = document.querySelector(".menu-toggle");
const nav = document.querySelector(".site-nav");

if (toggle && nav) {
  toggle.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", String(open));
  });

  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      nav.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    });
  });
}

// Mobile property filter bottom sheet
const propertyFilter = document.querySelector("[data-property-filter]");
const filterOpen = document.querySelector("[data-filter-open]");
const filterCloseButtons = document.querySelectorAll("[data-filter-close]");

if (propertyFilter && filterOpen) {
  const closeFilter = () => {
    document.body.classList.remove("filter-sheet-open");
    propertyFilter.classList.remove("open");
  };

  filterOpen.addEventListener("click", () => {
    document.body.classList.add("filter-sheet-open");
    propertyFilter.classList.add("open");
  });
  filterCloseButtons.forEach((button) =>
    button.addEventListener("click", closeFilter),
  );
}

// Homepage hero carousel
const slider = document.querySelector("[data-slider]");
if (slider) {
  const slides = [...slider.querySelectorAll(".hero-slide")];
  const previous = slider.querySelector("[data-prev]");
  const next = slider.querySelector("[data-next]");
  let current = 0;
  let timer;

  const show = (index) => {
    current = (index + slides.length) % slides.length;
    slides.forEach((slide, i) =>
      slide.classList.toggle("active", i === current),
    );
  };

  const restart = () => {
    clearInterval(timer);
    timer = setInterval(() => show(current + 1), 5000);
  };

  if (previous && next && slides.length > 1) {
    previous.addEventListener("click", () => {
      show(current - 1);
      restart();
    });
    next.addEventListener("click", () => {
      show(current + 1);
      restart();
    });
    restart();
  }
}

// Animated achievement counters
const counters = document.querySelectorAll("[data-counter]");
if (counters.length) {
  const observer = new IntersectionObserver(
    (entries, instance) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;

        const node = entry.target;
        const target = Number(node.dataset.counter);
        const duration = 1200;
        const start = performance.now();

        const animate = (now) => {
          const progress = Math.min((now - start) / duration, 1);
          node.textContent = Math.floor(target * progress).toLocaleString(
            "en-IN",
          );
          if (progress < 1) requestAnimationFrame(animate);
        };

        requestAnimationFrame(animate);
        instance.unobserve(node);
      });
    },
    { threshold: 0.45 },
  );

  counters.forEach((counter) => observer.observe(counter));
}

// Responsive testimonial carousel
const testimonialSlider = document.querySelector("[data-testimonial-slider]");
if (testimonialSlider) {
  const slides = [...testimonialSlider.querySelectorAll(".testimonial-slide")];

  if (slides.length) {
    const previous = testimonialSlider.querySelector("[data-testimonial-prev]");
    const next = testimonialSlider.querySelector("[data-testimonial-next]");
    let current = 0;
    let timer;

    const visibleCount = () => {
      if (window.innerWidth >= 1500) return 4;
      if (window.innerWidth > 950) return 3;
      if (window.innerWidth > 620) return 2;
      return 1;
    };

    const show = (index) => {
      current = (index + slides.length) % slides.length;
      const visible = visibleCount();
      slides.forEach((slide, i) => {
        const distance = (i - current + slides.length) % slides.length;
        slide.classList.toggle(
          "active",
          distance < Math.min(visible, slides.length),
        );
      });
    };

    const restart = () => {
      clearInterval(timer);
      timer = setInterval(() => show(current + 1), 5500);
    };

    if (previous && next && slides.length > 1) {
      previous.addEventListener("click", () => {
        show(current - 1);
        restart();
      });
      next.addEventListener("click", () => {
        show(current + 1);
        restart();
      });
      restart();
    }

    window.addEventListener("resize", () => show(current));
    show(0);
  }
}

// Gallery lightbox
const galleryLightbox = document.querySelector("[data-gallery-lightbox]");
if (galleryLightbox) {
  const image = galleryLightbox.querySelector("[data-lightbox-image]");
  const title = galleryLightbox.querySelector("[data-lightbox-title]");
  const caption = galleryLightbox.querySelector("[data-lightbox-caption]");

  const close = () => {
    galleryLightbox.classList.remove("open");
    galleryLightbox.setAttribute("aria-hidden", "true");
  };

  document.querySelectorAll("[data-gallery-item]").forEach((item) => {
    item.addEventListener("click", () => {
      image.src = item.dataset.image;
      image.alt = item.dataset.title;
      title.textContent = item.dataset.title;
      caption.textContent = item.dataset.caption;
      galleryLightbox.classList.add("open");
      galleryLightbox.setAttribute("aria-hidden", "false");
    });
  });

  galleryLightbox
    .querySelector("[data-lightbox-close]")
    .addEventListener("click", close);
  galleryLightbox.addEventListener("click", (event) => {
    if (event.target === galleryLightbox) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });
}
