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

  function operation(label = "Working") {
    return `<div class="inline-operation-card" role="status" aria-live="polite"><span class="global-operation-spinner" aria-hidden="true"></span><strong>${safe(label)}…</strong></div>`;
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

  function busy(target, label = "Working") {
    if (!target) return;
    end(target);
    target.classList.add("loading-region");
    target.setAttribute("aria-busy", "true");
    const overlay = document.createElement("div");
    overlay.className = "loading-region-overlay action-region-overlay";
    overlay.dataset.loadingOverlay = "true";
    overlay.innerHTML = operation(label);
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

  const actionStates = new WeakMap();
  let activeControl = null;
  let activeControlTimer;
  let pageOverlay;

  const interactive =
    'button,a[href],input[type="button"],input[type="submit"],input[type="radio"],input[type="checkbox"],select,[role="button"],[data-action],[data-tab]';

  function actionHost(control) {
    if (!control) return null;
    if (control.matches('input[type="radio"],input[type="checkbox"],select')) {
      return control.closest("label") || control.parentElement;
    }
    return control;
  }

  function actionBegin(control, label = "Working") {
    if (!control || control.matches(":disabled") || control.closest("[data-no-loading]")) return;
    const host = actionHost(control);
    if (!host) return;
    const current = actionStates.get(control) || { depth: 0, host, started: performance.now() };
    current.depth += 1;
    actionStates.set(control, current);
    if (current.depth > 1 && host.querySelector(":scope > [data-action-spinner]")) return;
    host.classList.add("action-is-loading");
    control.setAttribute("aria-busy", "true");
    const spinner = document.createElement("span");
    spinner.className = control === host ? "action-spinner" : "control-action-spinner";
    spinner.dataset.actionSpinner = "true";
    spinner.setAttribute("aria-hidden", "true");
    host.append(spinner);
    const announcement = document.createElement("span");
    announcement.className = "loading-announcement";
    announcement.dataset.actionAnnouncement = "true";
    announcement.textContent = `${label}…`;
    host.append(announcement);
  }

  function actionEnd(control, immediate = false) {
    const state = control && actionStates.get(control);
    if (!state) return;
    state.depth = Math.max(0, state.depth - 1);
    if (state.depth) return;
    const clear = () => {
      state.host.querySelectorAll(":scope > [data-action-spinner],:scope > [data-action-announcement]").forEach((item) => item.remove());
      state.host.classList.remove("action-is-loading");
      control.removeAttribute("aria-busy");
      actionStates.delete(control);
    };
    const remaining = immediate ? 0 : Math.max(0, 260 - (performance.now() - state.started));
    window.setTimeout(clear, remaining);
  }

  function rememberControl(control) {
    activeControl = control;
    window.clearTimeout(activeControlTimer);
    activeControlTimer = window.setTimeout(() => {
      if (activeControl === control) activeControl = null;
    }, 120);
  }

  function controlForEvent(event) {
    const candidate = event.target?.closest?.(interactive);
    return candidate && !candidate.matches(":disabled") ? candidate : null;
  }

  function transientAction(control, label) {
    if (!control) return;
    rememberControl(control);
    actionBegin(control, label);
    window.setTimeout(() => actionEnd(control), 420);
  }

  const nativeFetch = window.fetch.bind(window);
  window.fetch = (...args) => {
    const focused = document.activeElement?.closest?.(interactive);
    const control = activeControl || (focused && !focused.matches(":disabled") ? focused : null);
    if (control) actionBegin(control, "Loading");
    return nativeFetch(...args).finally(() => {
      if (control) actionEnd(control);
    });
  };

  function setPageInert(locked) {
    for (const child of document.body?.children || []) {
      if (child === pageOverlay) continue;
      if (locked) {
        if (child.dataset.loadingWasInert === undefined) {
          child.dataset.loadingWasInert = child.inert ? "true" : "false";
        }
        child.inert = true;
      } else if (child.dataset.loadingWasInert !== undefined) {
        child.inert = child.dataset.loadingWasInert === "true";
        delete child.dataset.loadingWasInert;
      }
    }
  }

  function ensurePageOverlay(mode, label) {
    if (!document.body) return null;
    if (!pageOverlay) {
      pageOverlay = document.createElement("div");
      pageOverlay.className = "global-page-loader";
      pageOverlay.setAttribute("role", "status");
      pageOverlay.setAttribute("aria-live", "assertive");
      document.body.append(pageOverlay);
    }
    pageOverlay.classList.toggle("is-page-transition", mode === "skeleton");
    pageOverlay.classList.toggle("is-operation-lock", mode === "operation");
    pageOverlay.innerHTML = mode === "skeleton"
      ? `<div class="global-skeleton-shell"><div class="global-skeleton-brand"><span class="skeleton-block skeleton-icon"></span>${line("short")}${line("medium")}</div>${page(label)}</div>`
      : `<div class="global-operation-card"><span class="global-operation-spinner" aria-hidden="true"></span><strong>${safe(label)}</strong><small>Please wait while Classarit finishes this action.</small></div>`;
    document.documentElement.classList.add("page-loading");
    document.body.classList.add("page-is-locked");
    document.body.setAttribute("aria-busy", "true");
    setPageInert(true);
    pageOverlay.inert = false;
    return pageOverlay;
  }

  function lockPage(label = "Working") {
    ensurePageOverlay("operation", label);
  }

  function transition(label = "Loading page") {
    ensurePageOverlay("skeleton", label);
  }

  function unlockPage() {
    setPageInert(false);
    pageOverlay?.remove();
    pageOverlay = null;
    document.documentElement.classList.remove("page-loading");
    document.body?.classList.remove("page-is-locked");
    document.body?.setAttribute("aria-busy", "false");
  }

  function navigate(url, label = "next page") {
    transition(label);
    window.requestAnimationFrame(() => window.location.assign(url));
    return true;
  }

  function replace(url, label = "next page") {
    transition(label);
    window.requestAnimationFrame(() => window.location.replace(url));
    return true;
  }

  function reload(label = "page") {
    transition(label);
    window.requestAnimationFrame(() => window.location.reload());
    return true;
  }

  document.addEventListener("click", (event) => {
    const control = controlForEvent(event);
    if (control) transientAction(control, "Loading");
  }, true);
  document.addEventListener("change", (event) => {
    const control = controlForEvent(event);
    if (control) transientAction(control, "Updating");
  }, true);
  document.addEventListener("submit", (event) => {
    const control = event.submitter || event.target.querySelector?.('[type="submit"]');
    if (control) transientAction(control, "Submitting");
  }, true);

  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = event.target.closest?.("a[href]");
    if (!anchor || anchor.target && anchor.target !== "_self" || anchor.hasAttribute("download")) return;
    let destination;
    try { destination = new URL(anchor.href, window.location.href); } catch (_) { return; }
    if (destination.origin !== window.location.origin) return;
    const onlyHashChanges = destination.pathname === window.location.pathname && destination.search === window.location.search && destination.hash;
    if (!onlyHashChanges) transition("next page");
  });
  document.addEventListener("submit", (event) => {
    if (!event.defaultPrevented) transition("next page");
  });
  window.addEventListener("beforeunload", () => transition("next page"));
  window.addEventListener("pageshow", (event) => {
    if (event.persisted || pageOverlay) unlockPage();
  });

  window.ClassaritLoading = {
    actionBegin,
    actionEnd,
    begin,
    busy,
    calendar,
    end,
    lockPage,
    navigate,
    operation,
    page,
    panel,
    reload,
    replace,
    transition,
    unlockPage,
  };
})();
