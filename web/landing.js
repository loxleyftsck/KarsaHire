document.documentElement.classList.add("js");

const menuButton = document.querySelector(".nav-toggle");
const siteNav = document.querySelector(".site-nav");

function closeMenu() {
  if (!menuButton || !siteNav) return;
  menuButton.setAttribute("aria-expanded", "false");
  menuButton.setAttribute("aria-label", "Buka navigasi");
  siteNav.classList.remove("open");
}

function openMenu() {
  if (!menuButton || !siteNav) return;
  menuButton.setAttribute("aria-expanded", "true");
  menuButton.setAttribute("aria-label", "Tutup navigasi");
  siteNav.classList.add("open");
}

if (menuButton && siteNav) {
  menuButton.addEventListener("click", (event) => {
    event.stopPropagation();
    const isOpen = menuButton.getAttribute("aria-expanded") === "true";
    if (isOpen) {
      closeMenu();
    } else {
      openMenu();
    }
  });

  // Close when clicking nav links on mobile
  siteNav.addEventListener("click", (event) => {
    if (!event.target.closest("a") || window.matchMedia("(min-width: 681px)").matches) return;
    closeMenu();
  });

  // Close on Escape key press and restore focus to toggle button
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menuButton.getAttribute("aria-expanded") === "true") {
      closeMenu();
      menuButton.focus();
    }
  });

  // Close when clicking or tapping outside the menu and toggle button
  document.addEventListener("click", (event) => {
    if (menuButton.getAttribute("aria-expanded") !== "true") return;
    if (!menuButton.contains(event.target) && !siteNav.contains(event.target)) {
      closeMenu();
    }
  });

  // Reset menu state on viewport resize
  window.addEventListener("resize", () => {
    if (window.innerWidth > 680 && menuButton.getAttribute("aria-expanded") === "true") {
      closeMenu();
    }
  });
}

// Reveal animation with reduced-motion awareness
const revealItems = document.querySelectorAll(".reveal");
const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

function handleRevealState() {
  if (motionQuery.matches || !("IntersectionObserver" in window)) {
    revealItems.forEach((item) => item.classList.add("visible"));
    return;
  }

  const observer = new IntersectionObserver((entries, activeObserver) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("visible");
      activeObserver.unobserve(entry.target);
    });
  }, { threshold: 0.12 });

  revealItems.forEach((item) => {
    if (!item.classList.contains("visible")) {
      observer.observe(item);
    }
  });
}

handleRevealState();

if (typeof motionQuery.addEventListener === "function") {
  motionQuery.addEventListener("change", () => {
    if (motionQuery.matches) {
      revealItems.forEach((item) => item.classList.add("visible"));
    }
  });
}
