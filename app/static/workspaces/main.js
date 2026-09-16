import {
  getCalendarMonth,
  openCalendarDay,
  setCalendarLoading,
  setCalendarMonthData,
  updateCalendarView,
} from "./calendar.js?v=workspace-reporting-20260915";
import { api, clearNotice, request, notice, workspaceId } from "./api.js?v=workspace-reporting-20260915";
import { render } from "./render.js?v=workspace-reporting-20260915";
import { action } from "./actions.js?v=workspace-reporting-20260915";
let snapshot,
  loadVersion = 0,
  tab = document.body.dataset.teacherOnly === "true" ? "classes" : "calendar",
  switchingWorkspace = false,
  scheduleHistory = false;
const allowedTabs =
  document.body.dataset.teacherOnly === "true"
    ? ["classes", "sessions"]
    : [
        "calendar",
        "classes",
        "students",
        "sessions",
        "venues",
        "team",
        "makeups",
        ...(document.body.dataset.ownerView === "true" ? ["reporting"] : []),
      ];
const requestedTab = location.hash.slice(1) === "overview" ? "calendar" : location.hash.slice(1);
if (allowedTabs.includes(requestedTab)) tab = requestedTab;
function activeTabButtons() {
  document
    .querySelectorAll("[data-tab]")
    .forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
}
function content() {
  return document.querySelector("#workspace-content");
}
function showSectionLoading(label = "workspace") {
  const target = content();
  if (!target) return;
  target.innerHTML = `<section class="workspace-card empty"><span class="calendar-spinner" aria-hidden="true"></span><p>Loading ${label}…</p></section>`;
  activeTabButtons();
}
function draw() {
  const target = content();
  if (!target || !snapshot) return;
  target.innerHTML = render(snapshot, tab);
  activeTabButtons();
}
function sectionPath(name, month, options = {}) {
  const params = new URLSearchParams();
  if (name === "calendar" && month) params.set("month", month);
  if (name === "sessions" && options.history) params.set("history", "1");
  const query = params.toString();
  return `/section/${encodeURIComponent(name)}${query ? `?${query}` : ""}`;
}
async function loadTab(next = tab, options = {}) {
  if (!allowedTabs.includes(next)) return;
  if (!options.keepNotice) clearNotice();
  const previousTab = tab;
  if (next === "sessions") {
    if (Object.prototype.hasOwnProperty.call(options, "history")) {
      scheduleHistory = Boolean(options.history);
    } else if (previousTab !== "sessions") {
      scheduleHistory = false;
    }
  } else {
    scheduleHistory = false;
  }
  tab = next;
  const version = ++loadVersion;
  const month = tab === "calendar" && snapshot ? getCalendarMonth(snapshot) : options.month;
  showSectionLoading(tab.replaceAll("-", " "));
  try {
    const data = await api(sectionPath(tab, month, { history: scheduleHistory }));
    if (version !== loadVersion) return;
    snapshot = data;
    if (tab === "calendar" && data.calendar) setCalendarMonthData(data.calendar);
    draw();
  } catch (error) {
    if (version === loadVersion) notice(error.message, true);
  }
}
async function refresh() {
  await loadTab(tab, { keepNotice: true });
}
async function moveCalendar(actionName) {
  if (!snapshot) return;
  clearNotice();
  const month = updateCalendarView(actionName, snapshot);
  setCalendarLoading(true);
  draw();
  const version = ++loadVersion;
  try {
    const data = await api(sectionPath("calendar", month));
    if (version !== loadVersion) return;
    snapshot = data;
    if (data.calendar) setCalendarMonthData(data.calendar);
  } catch (error) {
    notice(error.message, true);
  } finally {
    if (version === loadVersion) {
      setCalendarLoading(false);
      draw();
    }
  }
}
document.querySelector("#logout").onclick = async () => {
  try {
    const response = await fetch("/auth/logout", {
      method: "POST",
      body: new URLSearchParams({
        csrf_token: document.querySelector('meta[name="csrf-token"]').content,
      }),
    });
    if (!response.ok) throw new Error("Could not log out. Please retry.");
    location.href = "/";
  } catch (e) {
    notice(e.message, true);
  }
};
function openWorkspace(value) {
  if (!value || value === workspaceId || switchingWorkspace) return;
  switchingWorkspace = true;
  window.location.assign(`/workspaces/${encodeURIComponent(value)}`);
}
document
  .querySelector("#onboarding-form")
  ?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const button = e.target.querySelector("button");
    button.disabled = true;
    try {
      const row = await request(
        "/api/workspaces",
        "POST",
        Object.fromEntries(new FormData(e.target)),
      );
      location.href = `/workspaces/${row.id}`;
    } catch (e) {
      notice(e.message, true);
    } finally {
      button.disabled = false;
    }
  });
document
  .querySelector("#accept-invitation")
  ?.addEventListener("click", async () => {
    try {
      const row = await request(
        `/api/invitations/${encodeURIComponent(document.body.dataset.invitation)}/accept`,
        "POST",
      );
      location.href = `/workspaces/${row.workspace_id}`;
    } catch (e) {
      notice(e.message, true);
    }
  });
document
  .querySelector("#dismiss-invitation")
  ?.addEventListener("click", async () => {
    try {
      await request("/api/invitations/dismiss", "POST");
      location.href = "/dashboard";
    } catch (e) {
      notice(e.message, true);
    }
  });
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-tab],[data-action],[data-schedule-history]");
  if (!b) return;
  if (b.dataset.scheduleHistory !== undefined) {
    e.preventDefault();
    loadTab("sessions", { history: b.dataset.scheduleHistory === "true" });
  } else if (b.dataset.tab) {
    if (!allowedTabs.includes(b.dataset.tab)) return;
    loadTab(b.dataset.tab);
  } else if (snapshot) {
    e.preventDefault();
    e.stopPropagation();
    clearNotice();
    action(snapshot, b.dataset.action, b.dataset.id, refresh);
  }
});
if (workspaceId) loadTab(tab).catch((e) => notice(e.message, true));

document.addEventListener("change", (event) => {
  if (event.target?.id === "workspace-picker") openWorkspace(event.target.value);
});

document.addEventListener("input", (event) => {
  if (event.target?.id === "workspace-picker") openWorkspace(event.target.value);
});

document.addEventListener("click", e => {
  const control=e.target.closest("[data-calendar-control]");
  const day=e.target.closest("[data-calendar-day]");
  const button=e.target.closest("[data-calendar-action]");
  if (!snapshot || (!control && !day && !button)) return;
  e.preventDefault();
  e.stopPropagation();
  if (control) {
    moveCalendar(control.dataset.calendarControl);
    return;
  }
  if(day) {
    const manager = snapshot.roles.some((r) =>
      ["OWNER", "ADMIN", "OPERATOR"].includes(r),
    );
    openCalendarDay(snapshot,day.dataset.calendarDay,manager);
    return;
  }
  const popup=document.querySelector("#calendar-popup");
  if(popup) popup.hidden = true;
  action(snapshot,button.dataset.calendarAction,button.dataset.id || "",refresh,{
    dateKey: button.dataset.dateKey,
  });
}, true);
