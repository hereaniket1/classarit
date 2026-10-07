import {
  getCalendarMonth,
  getCalendarMonths,
  openCalendarDay,
  setCalendarLoading,
  setCalendarMonthData,
  updateCalendarView,
} from "./calendar.js?v=global-loading-20260930";
import { api, clearNotice, request, notice, workspaceId } from "./api.js?v=global-loading-20260930";
import { render } from "./render.js?v=global-loading-20260930";
import { action } from "./actions.js?v=global-loading-20260930";
let snapshot,
  loadVersion = 0,
  tab = "dashboard",
  switchingWorkspace = false,
  scheduleHistory = false;
const allowedTabs =
  document.body.dataset.teacherOnly === "true"
    ? ["dashboard", "classes", "sessions", "settings"]
    : [
        "dashboard",
        "calendar",
        "classes",
        "students",
        "sessions",
        "venues",
        ...(document.body.dataset.ownerView === "true" ? ["reporting"] : []),
        "settings",
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
function setQuickActionsAvailable(available) {
  document.querySelectorAll(".quick-action").forEach((control) => {
    control.disabled = !available;
  });
}
function showSectionLoading(label = "workspace") {
  const target = content();
  if (!target) return;
  setQuickActionsAvailable(false);
  target.setAttribute("aria-busy", "true");
  target.innerHTML = window.ClassaritLoading?.page(label) ||
    `<section class="workspace-card empty"><p>Loading ${label}…</p></section>`;
  activeTabButtons();
}
function showSectionError() {
  const target = content();
  if (!target) return;
  target.setAttribute("aria-busy", "false");
  target.innerHTML = '<section class="workspace-card empty">This section could not be loaded. Choose it again to retry.</section>';
}
function draw() {
  const target = content();
  if (!target || !snapshot) return;
  target.innerHTML = render(snapshot, tab);
  target.setAttribute("aria-busy", "false");
  setQuickActionsAvailable(true);
  activeTabButtons();
}
function sectionPath(name, month, options = {}) {
  const params = new URLSearchParams();
  if (name === "calendar" && month) params.set("month", month);
  if (name === "sessions" && options.history) params.set("history", "1");
  const query = params.toString();
  return `/section/${encodeURIComponent(name)}${query ? `?${query}` : ""}`;
}
async function loadCalendar(month) {
  const data = await api(sectionPath('calendar', month));
  const months = getCalendarMonths(data);
  if (months.length > 1) {
    const extra = await api(sectionPath('calendar', months[1]));
    data.calendar.sessions = [...new Map([...data.calendar.sessions, ...extra.calendar.sessions].map(row=>[row.id,row])).values()];
    data.sessions = data.calendar.sessions;
    data.venues = [...new Map([...data.venues, ...extra.venues].map(row=>[row.id,row])).values()];
  }
  return data;
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
    const data = tab === "calendar" ? await loadCalendar(month) : await api(sectionPath(tab, month, { history: scheduleHistory }));
    if (version !== loadVersion) return;
    snapshot = data;
    if (tab === "calendar" && data.calendar) setCalendarMonthData(data.calendar);
    draw();
  } catch (error) {
    if (version === loadVersion) {
      showSectionError();
      notice(error.message, true);
    }
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
    const data = await loadCalendar(month);
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
    window.ClassaritLoading?.navigate("/", "home") || (location.href = "/");
  } catch (e) {
    notice(e.message, true);
  }
};
function openWorkspace(value) {
  if (!value || value === workspaceId || switchingWorkspace) return;
  switchingWorkspace = true;
  window.ClassaritLoading?.navigate(`/workspaces/${encodeURIComponent(value)}`, "workspace") || window.location.assign(`/workspaces/${encodeURIComponent(value)}`);
}
function syncBusinessProfileFields(form) {
  if (!form) return;
  const type = form.elements.namedItem("workspace_type")?.value;
  const panel = form.querySelector("#business-profile-fields");
  if (!panel) return;
  const needsBusinessProfile = type === "INSTITUTE";
  panel.hidden = !needsBusinessProfile;
  [
    "business_legal_name",
    "business_gstin",
    "owner_aadhaar_number",
    "business_address_line1",
    "business_city",
    "business_state",
    "business_postal_code",
    "business_country",
  ].forEach((name) => {
    const input = form.elements.namedItem(name);
    if (input) input.required = needsBusinessProfile;
  });
}
const onboardingForm = document.querySelector("#onboarding-form");
syncBusinessProfileFields(onboardingForm);
onboardingForm?.elements
  .namedItem("workspace_type")
  ?.addEventListener("change", () => syncBusinessProfileFields(onboardingForm));
document
  .querySelector("#onboarding-form")
  ?.addEventListener("submit", async (e) => {
    e.preventDefault();
    syncBusinessProfileFields(e.target);
    const button = e.target.querySelector("button");
    button.disabled = true;
    try {
      const data = Object.fromEntries(new FormData(e.target));
      if (data.workspace_type !== "INSTITUTE") {
        for (const key of Object.keys(data)) {
          if (key.startsWith("business_")) delete data[key];
        }
        delete data.owner_aadhaar_number;
      }
      if (data.business_gstin) data.business_gstin = data.business_gstin.toUpperCase();
      if (data.owner_aadhaar_number) data.owner_aadhaar_number = data.owner_aadhaar_number.toUpperCase();
      if (data.business_country) data.business_country = data.business_country.toUpperCase();
      const row = await request(
        "/api/workspaces",
        "POST",
        data,
      );
      window.ClassaritLoading?.navigate(`/workspaces/${row.id}`, "workspace") || (location.href = `/workspaces/${row.id}`);
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
      window.ClassaritLoading?.navigate(`/workspaces/${row.workspace_id}`, "workspace") || (location.href = `/workspaces/${row.workspace_id}`);
    } catch (e) {
      notice(e.message, true);
    }
  });
document
  .querySelector("#dismiss-invitation")
  ?.addEventListener("click", async () => {
    try {
      await request("/api/invitations/dismiss", "POST");
      window.ClassaritLoading?.navigate("/dashboard", "dashboard") || (location.href = "/dashboard");
    } catch (e) {
      notice(e.message, true);
    }
  });
async function runAction(key, id, options = {}) {
  const current = snapshot, version = loadVersion;
  try {
    const needsReferences = !key.startsWith('delete-') && !['complete','end-enrollment','disable-series','restore-series','attendance','revoke','release'].includes(key);
    if (needsReferences && current.roles.some(role => ["OWNER", "ADMIN", "OPERATOR"].includes(role))) {
      const refs = await api('/section/action-refs');
      if (version !== loadVersion || current !== snapshot) return;
      for (const field of ['programs','program_teachers','members','venues','spaces','students','business_profile','policy']) current[field] = refs[field];
    }
    await action(current, key, id, refresh, options);
  } catch (error) { notice(error.message, true); }
}

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
    runAction(b.dataset.action, b.dataset.id);
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
  runAction(button.dataset.calendarAction,button.dataset.id || "",{
    dateKey: button.dataset.dateKey,
  });
}, true);

 document.querySelector('#make-default-workspace')?.addEventListener('click', async event => {
   const button = event.currentTarget;
   button.disabled = true;
   try {
     await request('/api/account/default-workspace', 'POST', {workspace_id: workspaceId});
     button.textContent = 'Default workspace';
     notice('This workspace will open by default after login.');
   } catch(error) { button.disabled = false; notice(error.message, true); }
 });
