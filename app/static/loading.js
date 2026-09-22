/** Reusable full-region skeletons for network-backed Classarit surfaces. */
(() => {
  const safe = (value) =>
    String(value ?? "content").replace(
      /[&<>"']/g,
      (character) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[character],
    );

  const announcement = (label) =>
    `<span class="loading-announcement">Loading ${safe(label)}…</span>`;
  const line = (size = "medium") =>
    `<span class="skeleton-block skeleton-line skeleton-line-${size}"></span>`;
  const rows = (count = 4) =>
    Array.from(
      { length: count },
      (_, index) =>
        `<div class="skeleton-row"><span class="skeleton-block skeleton-avatar"></span><div>${line(index % 2 ? "medium" : "long")}${line("short")}</div><span class="skeleton-block skeleton-button"></span></div>`,
    ).join("");
  const card = (rowCount = 3) =>
    `<section class="skeleton-card" aria-hidden="true"><div class="skeleton-card-title">${line("medium")}${line("short")}</div>${rows(rowCount)}</section>`;

  function page(label = "workspace") {
    return `<div class="skeleton-page" role="status" aria-live="polite">${announcement(label)}<div class="skeleton-page-title" aria-hidden="true">${line("medium")}</div><div class="skeleton-metric-grid" aria-hidden="true">${Array.from({ length: 4 }, () => `<div class="skeleton-metric"><span class="skeleton-block skeleton-icon"></span><div>${line("short")}${line("medium")}</div></div>`).join("")}</div><div class="skeleton-content-grid">${card(4)}${card(4)}</div></div>`;
  }

  function panel(label = "content", rowCount = 4) {
    return `<div class="skeleton-panel" role="status" aria-live="polite">${announcement(label)}<div aria-hidden="true">${line("medium")}${line("long")}${rows(rowCount)}</div></div>`;
  }

  function calendar(label = "calendar") {
    return `<div class="skeleton-calendar" role="status" aria-live="polite">${announcement(label)}<div class="skeleton-weekdays" aria-hidden="true">${Array.from({ length: 7 }, () => line("short")).join("")}</div><div class="skeleton-calendar-grid" aria-hidden="true">${Array.from({ length: 35 }, () => `<span class="skeleton-block skeleton-day"></span>`).join("")}</div></div>`;
  }

  function begin(target, label = "content", options = {}) {
    if (!target) return;
    end(target);
    target.classList.add("loading-region");
    target.setAttribute("aria-busy", "true");
    const overlay = document.createElement("div");
    overlay.className = "loading-region-overlay";
    overlay.dataset.loadingOverlay = "true";
    overlay.innerHTML = panel(label, options.rows || 4);
    target.append(overlay);
  }

  function end(target) {
    if (!target) return;
    Array.from(target.children)
      .find((child) => child.hasAttribute("data-loading-overlay"))
      ?.remove();
    target.classList.remove("loading-region");
    target.setAttribute("aria-busy", "false");
  }

  window.ClassaritLoading = { begin, calendar, end, page, panel };
})();
