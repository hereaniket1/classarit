/** Month calendar uses workspace-local dates and API-loaded monthly sessions. */
import { esc } from "./api.js?v=workspace-reporting-20260915";
import { icon } from "./icons.js?v=workspace-reporting-20260915";

const INLINE_SLOT_LIMIT = 2;
const calendarState = { monthKey: "", monthData: null, loading: false };

export function dateKey(value, zone) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(value));
  return ["year", "month", "day"]
    .map((k) => parts.find((p) => p.type === k).value)
    .join("-");
}

function ensureMonth(s, now = new Date()) {
  if (!calendarState.monthKey)
    calendarState.monthKey = dateKey(now, s.workspace.timezone).slice(0, 7);
}

function monthDate(monthKey, day = 1) {
  return new Date(`${monthKey}-${String(day).padStart(2, "0")}T12:00:00Z`);
}

function addMonths(monthKey, offset) {
  const date = monthDate(monthKey);
  date.setUTCMonth(date.getUTCMonth() + offset);
  return date.toISOString().slice(0, 7);
}

function daysInMonth(monthKey) {
  const date = monthDate(monthKey);
  return new Date(date.getUTCFullYear(), date.getUTCMonth() + 1, 0).getDate();
}

function dayKey(monthKey, day) {
  return `${monthKey}-${String(day).padStart(2, "0")}`;
}

function monthTitle(monthKey) {
  return monthDate(monthKey).toLocaleDateString(undefined, {
    timeZone: "UTC",
    month: "long",
    year: "numeric",
  });
}

function dayLabel(key) {
  return new Date(`${key}T12:00:00Z`).toLocaleDateString(undefined, {
    timeZone: "UTC",
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function dayNumber(key) {
  return new Date(`${key}T12:00:00Z`).toLocaleDateString(undefined, {
    timeZone: "UTC",
    day: "numeric",
  });
}

function slot(x, key, zone) {
  const time = (v) =>
    new Date(v).toLocaleTimeString(undefined, {
      timeZone: zone,
      hour: "numeric",
      minute: "2-digit",
    });
  return `${dateKey(x.starts_at, zone) < key ? "00:00" : time(x.starts_at)} - ${
    dateKey(x.ends_at, zone) > key ? "24:00" : time(x.ends_at)
  }`;
}

function monthSessions(s) {
  return calendarState.monthData?.month === calendarState.monthKey
    ? calendarState.monthData.sessions
    : s.sessions;
}

function sessionsForDay(s, key) {
  const zone = s.workspace.timezone;
  return monthSessions(s)
    .filter(
      (x) =>
        ["SCHEDULED", "COMPLETED"].includes(x.status) &&
        dateKey(x.starts_at, zone) <= key &&
        dateKey(new Date(new Date(x.ends_at).getTime() - 1), zone) >= key,
    )
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
}

export function getCalendarMonth(s) {
  ensureMonth(s);
  return calendarState.monthKey;
}

export function setCalendarMonthData(data) {
  calendarState.monthKey = data.month;
  calendarState.monthData = data;
}

export function setCalendarLoading(loading) {
  calendarState.loading = loading;
}

export function updateCalendarView(action, s) {
  ensureMonth(s);
  if (action === "previous")
    calendarState.monthKey = addMonths(calendarState.monthKey, -1);
  if (action === "next")
    calendarState.monthKey = addMonths(calendarState.monthKey, 1);
  if (action === "today") calendarState.monthKey = "";
  ensureMonth(s);
  return calendarState.monthKey;
}

export function calendarDays(s, now = new Date()) {
  ensureMonth(s, now);
  const today = dateKey(now, s.workspace.timezone);
  return Array.from({ length: daysInMonth(calendarState.monthKey) }, (_, i) => {
    const key = dayKey(calendarState.monthKey, i + 1);
    const past = key < today;
    const todayFlag = key === today;
    const sessions = sessionsForDay(s, key);
    return {
      key,
      sessions,
      past,
      today: todayFlag,
      state: past
        ? "past"
        : sessions.length > 4
          ? "full"
          : sessions.length
            ? "busy"
            : "free",
    };
  });
}

function calendarCells(s) {
  ensureMonth(s);
  const blanks = Array.from(
    { length: monthDate(calendarState.monthKey).getUTCDay() },
    () => null,
  );
  return [...blanks, ...calendarDays(s)];
}

export function renderCalendar(s) {
  ensureMonth(s);
  const zone = s.workspace.timezone;
  return `<section class="workspace-card month-calendar ${calendarState.loading ? "is-loading" : ""}" aria-busy="${calendarState.loading ? "true" : "false"}"><div class="calendar-head"><h2>${esc(monthTitle(calendarState.monthKey))}</h2><div class="calendar-controls"><button type="button" class="btn btn-outline-primary labeled-action" data-calendar-control="previous" title="Previous month"><span>Previous</span></button><button type="button" class="btn btn-outline-primary labeled-action" data-calendar-control="today" title="Current month"><span>Current month</span></button><button type="button" class="btn btn-outline-primary labeled-action" data-calendar-control="next" title="Next month"><span>Next</span></button></div></div><div class="calendar-surface"><div class="weekday-row">${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => `<span>${d}</span>`).join("")}</div><div class="month-grid">${calendarCells(s)
    .map((d) =>
      d
        ? `<button type="button" class="calendar-day ${d.state}${d.today ? " today" : ""}" data-calendar-day="${d.key}" aria-label="${esc(dayLabel(d.key))}: ${d.sessions.length} scheduled classes"><strong>${esc(dayNumber(d.key))}</strong><small>${d.past ? `${d.sessions.length ? `${d.sessions.length} class${d.sessions.length === 1 ? "" : "es"}` : "Past day"}` : d.sessions.length ? `${d.sessions.length} class${d.sessions.length === 1 ? "" : "es"}` : "Free day"}</small>${d.sessions.slice(0, INLINE_SLOT_LIMIT).map((x) => `<span class="busy-slot">${esc(slot(x, d.key, zone))}</span>`).join("")}${d.sessions.length > INLINE_SLOT_LIMIT ? `<small>+${d.sessions.length - INLINE_SLOT_LIMIT} more</small>` : ""}</button>`
        : '<span class="calendar-blank" aria-hidden="true"></span>',
    )
    .join("")}</div><div class="calendar-loader" role="status" aria-live="polite"><span class="calendar-spinner" aria-hidden="true"></span><strong>Loading calendar</strong><small>Please wait while the latest schedule loads.</small></div></div></section>`;
}

function closeCalendarPopup() {
  const modal = document.querySelector("#calendar-popup");
  if (modal) modal.hidden = true;
}

function calendarPopup() {
  let modal = document.querySelector("#calendar-popup");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "calendar-popup";
    modal.className = "calendar-popup";
    modal.hidden = true;
    modal.innerHTML = '<div class="calendar-popup-panel" role="dialog" aria-modal="true" aria-labelledby="calendar-day-title"></div>';
    document.body.append(modal);
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeCalendarPopup();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !modal.hidden) closeCalendarPopup();
    });
  }
  return modal;
}

export function openCalendarDay(s, key, manager = false) {
  const day = calendarDays(s).find((d) => d.key === key);
  if (!day) return;
  const manageable = manager && !day.past;
  const modal = calendarPopup();
  const panel = modal.querySelector(".calendar-popup-panel");
  panel.innerHTML = `<div class="editor-heading"><h2 id="calendar-day-title">${esc(dayLabel(key))}</h2><button type="button" aria-label="Close day schedule" title="Close">x</button></div>${manageable ? `<div class="day-toolbar"><button type="button" class="btn btn-primary labeled-action" data-calendar-action="session" data-date-key="${esc(key)}" title="Add schedule">${icon("session")}<span>Add schedule</span></button></div>` : ""}${day.sessions.length ? day.sessions.map((x) => { const canChange = manageable && x.status === "SCHEDULED" && new Date(x.starts_at) > new Date(); return `<article class="day-session"><div><strong>${esc(x.title)}</strong><p>${esc(slot(x, key, s.workspace.timezone))}</p><small>${esc(x.delivery_mode)} · ${esc(x.status)}${x.venue_id ? " · " + esc(s.venues.find((v) => v.id === x.venue_id)?.name || "") : ""}</small></div>${canChange ? `<div class="row-actions"><button type="button" class="btn btn-outline-primary labeled-action" data-calendar-action="reschedule" data-id="${esc(x.id)}" title="Edit schedule">${icon("edit")}<span>Edit</span></button><button type="button" class="btn btn-outline-danger labeled-action" data-calendar-action="cancel" data-id="${esc(x.id)}" title="Cancel schedule">${icon("close")}<span>Cancel</span></button></div>` : ""}</article>`; }).join("") : '<p class="day-session">No classes or sessions on this day.</p>'}`;
  panel.querySelector('button[aria-label="Close day schedule"]').onclick =
    closeCalendarPopup;
  modal.hidden = false;
}
