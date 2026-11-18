/** Month calendar uses workspace-local dates and API-loaded monthly sessions. */
import { esc } from "./api.js?v=global-loading-20260930";
import { icon } from "./icons.js?v=global-loading-20260930";

const INLINE_SLOT_LIMIT = 5;
const calendarState = { monthKey: "", monthData: null, loading: false, view: "month", anchor: "" };

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
  if (!calendarState.anchor) calendarState.anchor = dateKey(now, s.workspace.timezone);
}

function shiftDay(key, offset) {
  const value = new Date(`${key}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + offset);
  return value.toISOString().slice(0,10);
}

export function getCalendarMonths(s) {
  ensureMonth(s);
  const last = calendarState.view === 'week' ? shiftDay(calendarState.anchor, 6).slice(0,7) : calendarState.monthKey;
  return [...new Set([calendarState.monthKey, last])];
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

export function setCalendarAnchor(key) {
  calendarState.anchor = key;
  calendarState.monthKey = key.slice(0, 7);
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
  if (action.startsWith('view-')) calendarState.view = action.slice(5);
  if (action === 'today') {
    setCalendarAnchor(dateKey(new Date(), s.workspace.timezone));
  }
  if (action === 'previous' || action === 'next') {
    const direction = action === 'next' ? 1 : -1;
    if (calendarState.view === 'month') {
      calendarState.monthKey = addMonths(calendarState.monthKey, direction);
      calendarState.anchor = `${calendarState.monthKey}-01`;
    } else {
      calendarState.anchor = shiftDay(calendarState.anchor, direction * (calendarState.view === 'week' ? 7 : 1));
      calendarState.monthKey = calendarState.anchor.slice(0,7);
    }
  }
  return calendarState.monthKey;
}

export function calendarDays(s, now = new Date()) {
  ensureMonth(s, now);
  const today = dateKey(now, s.workspace.timezone);
  const length = calendarState.view === 'month' ? daysInMonth(calendarState.monthKey) : calendarState.view === 'week' ? 7 : 1;
  return Array.from({ length }, (_, i) => {
    const key = calendarState.view === 'month' ? dayKey(calendarState.monthKey, i + 1) : shiftDay(calendarState.anchor, i);
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
  if (calendarState.view !== 'month') return calendarDays(s);
  const blanks = Array.from(
    { length: (monthDate(calendarState.monthKey).getUTCDay() + 6) % 7 },
    () => null,
  );
  return [...blanks, ...calendarDays(s)];
}

const kind = x => x.status === "COMPLETED" ? ["check","Completed"] : x.session_kind === "EVENT" ? ["session","Event"] : ["program","Class"];

function labelHue(session) {
  const identity = String(session.program_id || session.series_id || session.title || session.name || "Untitled");
  let hash = 2166136261;
  for (const character of identity) hash = Math.imul(hash ^ character.codePointAt(0), 16777619) >>> 0;
  return hash % 360;
}

function clockLabel(minutes) {
  const hour = Math.floor(minutes / 60) % 24;
  const minute = minutes % 60;
  return `${hour % 12 || 12}${minute ? ":" + String(minute).padStart(2, "0") : ""}${hour < 12 ? "AM" : "PM"}`;
}

function minuteOfDay(value, zone) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(value));
  return Number(parts.find(part => part.type === "hour").value) * 60 +
    Number(parts.find(part => part.type === "minute").value);
}

function compactTimeRange(session, key, zone) {
  const start = dateKey(session.starts_at, zone) < key ? 0 : minuteOfDay(session.starts_at, zone);
  const end = dateKey(session.ends_at, zone) > key ? 1440 : minuteOfDay(session.ends_at, zone);
  return [clockLabel(start), clockLabel(end)];
}

function durationLabel(session) {
  const minutes = Math.round((new Date(session.ends_at) - new Date(session.starts_at)) / 60000);
  const hours = Math.floor(minutes / 60), remainder = minutes % 60;
  return hours ? `${hours}h${remainder ? " " + remainder + "m" : ""}` : `${minutes} min`;
}

function renderDayLabels(sessions, key, zone) {
  const labels = sessions.slice(0, INLINE_SLOT_LIMIT).map(session => {
    const [type, label] = kind(session);
    const name = String(session.title || session.name || "Untitled");
    // Use the course or personal series so its color stays consistent across dates and views.
    const hue = labelHue(session);
    const characters = Array.from(name);
    const shortened = characters.length > 10 ? characters.slice(0, 10).join("") + "…" : name;
    const description = `${label}: ${name} · ${slot(session, key, zone)}`;
    const [start, end] = compactTimeRange(session, key, zone);
    return `<span class="day-marker calendar-label kind-${type}" style="--label-hue:${hue}"
      title="${esc(description)}" aria-label="${esc(description)}"><span class="calendar-label-text" aria-hidden="true">${esc(shortened)}</span>
      <span class="calendar-label-time" aria-hidden="true"><span>${start}</span><span>to</span><span>${end}</span></span></span>`;
  }).join("");
  const more = sessions.length - INLINE_SLOT_LIMIT;
  return labels + (more > 0 ? `<small class="calendar-more">+${more} more</small>` : "");
}

function timelineEvents(sessions, key, zone) {
  const entries = sessions.map(session => {
    const start = dateKey(session.starts_at, zone) < key ? 0 : minuteOfDay(session.starts_at, zone);
    let end = dateKey(session.ends_at, zone) > key ? 1440 : minuteOfDay(session.ends_at, zone);
    if (end <= start) end = Math.min(1440, start + (new Date(session.ends_at) - new Date(session.starts_at)) / 60000);
    return { session, start, end, lane: 0, lanes: 1 };
  }).sort((a,b) => a.start - b.start || b.end - a.end);
  let group = [], laneEnds = [], groupEnd = -1;
  const finishGroup = () => { for (const entry of group) entry.lanes = laneEnds.length; };
  for (const entry of entries) {
    if (entry.start >= groupEnd) {
      finishGroup(); group = []; laneEnds = []; groupEnd = -1;
    }
    let lane = laneEnds.findIndex(end => end <= entry.start);
    if (lane < 0) lane = laneEnds.length;
    entry.lane = lane;
    laneEnds[lane] = entry.end;
    group.push(entry);
    groupEnd = Math.max(groupEnd,entry.end);
  }
  finishGroup();
  return entries.map(({session, start, end, lane, lanes}) => {
    const [type, label] = kind(session);
    const [begins, ends] = compactTimeRange(session, key, zone);
    const duration = durationLabel(session);
    const description = `${session.title} · ${begins} to ${ends} · ${duration} · ${label}`;
    return `<button type="button" class="calendar-time-event kind-${type}"
      data-calendar-event="${esc(session.id)}" data-date-key="${key}" title="${esc(description)}" aria-label="${esc(description)}"
      style="--label-hue:${labelHue(session)};top:${start / 1440 * 100}%;height:${(end-start) / 1440 * 100}%;left:calc(${lane / lanes * 100}% + 2px);width:calc(${100 / lanes}% - 4px)">
      <strong>${esc(session.title)}</strong><span class="timeline-event-info"><span class="calendar-event-times">${begins}–${ends}</span><small>${duration}</small></span></button>`;
  }).join("");
}

function renderTimeline(s) {
  const days = calendarDays(s), zone = s.workspace.timezone;
  const today = dateKey(new Date(), zone), currentMinute = minuteOfDay(new Date(), zone);
  const canSchedule = s.personalCalendar || s.roles?.some(role => ["OWNER","ADMIN","OPERATOR"].includes(role));
  const headers = days.map(day => `<button type="button" class="timeline-day-header${day.today ? " today" : ""}" data-calendar-day="${day.key}">
    ${esc(dayLabel(day.key))}</button>`).join("");
  const hours = Array.from({length:24}, (_,hour) => `<span style="top:${hour / 24 * 100}%">${clockLabel(hour*60)}</span>`).join("");
  const columns = days.map(day => {
    const slots = Array.from({length:48}, (_,index) => {
      const minutes = index * 30;
      const time = `${String(Math.floor(minutes / 60)).padStart(2,"0")}:${String(minutes % 60).padStart(2,"0")}`;
      const past = !s.personalCalendar && (day.key < today || (day.key === today && minutes <= currentMinute));
      return `<button type="button" class="calendar-time-slot${index % 2 ? " half-hour" : ""}"
        data-calendar-slot="${day.key}" data-start-time="${time}"
        style="top:${index / 48 * 100}%" ${!canSchedule || past ? "disabled" : ""}
        aria-label="Add event ${esc(dayLabel(day.key))} at ${clockLabel(minutes)}, 30 minutes"
        title="${clockLabel(minutes)}–${clockLabel(minutes+30)}"><span aria-hidden="true">+</span></button>`;
    }).join("");
    return `<div class="calendar-time-column${day.today ? " today" : ""}">${slots}${timelineEvents(day.sessions,day.key,zone)}</div>`;
  }).join("");
  return `<div class="calendar-timeline-scroll" tabindex="0" aria-label="Hourly calendar, ${esc(zone)}">
    <div class="calendar-timeline" style="--timeline-days:${days.length}">
      <div class="timeline-corner" title="${esc(zone)}" aria-label="Time zone ${esc(zone)}">Time</div>${headers}
      <div class="calendar-hours" aria-hidden="true">${hours}</div>${columns}
    </div></div>`;
}

let timelineScrollTop = 8 * 64, timelineScrollLeft = 0;
export function prepareCalendar(root) {
  const scroller = root.querySelector(".calendar-timeline-scroll");
  if (!scroller) return;
  scroller.scrollTop = timelineScrollTop;
  scroller.scrollLeft = timelineScrollLeft;
  scroller.addEventListener("scroll", () => {
    timelineScrollTop = scroller.scrollTop;
    timelineScrollLeft = scroller.scrollLeft;
  }, {passive:true});
  scroller.addEventListener("keydown", event => {
    const slot = event.target.closest("[data-calendar-slot]");
    if (!slot) return;
    const slots = [...scroller.querySelectorAll("[data-calendar-slot]")];
    const offset = {ArrowUp:-1, ArrowDown:1, ArrowLeft:-48, ArrowRight:48}[event.key];
    if (!offset) return;
    const next = slots[slots.indexOf(slot)+offset];
    if (next && !next.disabled) { event.preventDefault(); next.focus(); }
  });
}
export function renderCalendar(s) {
  ensureMonth(s);
  const zone = s.workspace.timezone;
  const view = calendarState.view;
  const title = view === 'month' ? monthTitle(calendarState.monthKey) : view === 'day' ? dayLabel(calendarState.anchor) : `${dayLabel(calendarState.anchor)} – ${dayLabel(shiftDay(calendarState.anchor,6))}`;
  const surface = view === "month" ? `
    <div class="weekday-row">${['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(day=>`<span>${day}</span>`).join("")}</div>
    <div class="month-grid">${calendarCells(s).map(day => day ? `
      <button class="calendar-day${day.today ? " today" : ""}${day.past ? " past" : ""}" data-calendar-day="${day.key}" aria-label="${esc(dayLabel(day.key))}: ${day.sessions.length} activities">
        <strong>${esc(dayNumber(day.key))}</strong><span class="day-markers">${renderDayLabels(day.sessions,day.key,zone)}</span>
      </button>` : '<span class="calendar-blank" aria-hidden="true"></span>').join("")}</div>` : renderTimeline(s);
  return `<section class="workspace-card month-calendar compact-calendar calendar-view-${view} ${calendarState.loading ? "is-loading" : ""}" aria-busy="${calendarState.loading}">
    <div class="calendar-head">
      <div class="month-selector"><button data-calendar-control="previous" aria-label="Previous ${view === 'week' ? '7 days' : view}">‹</button><h2>${esc(title)}</h2><button data-calendar-control="next" aria-label="Next ${view === 'week' ? '7 days' : view}">›</button></div>
      <div class="calendar-legend">${[['program','Class'],['session','Event'],['check','Completed']].map(([glyph,label])=>`<span class="calendar-key kind-${glyph}">${icon(glyph)} ${label}</span>`).join("")}</div>
      <div class="calendar-toolbar"><div class="calendar-view-switch" role="group" aria-label="Calendar view">
        ${[["day","Day"],["week","7 days"],["month","Month"]].map(([key,label])=>`<button type="button" data-calendar-control="view-${key}" aria-pressed="${view===key}">${label}</button>`).join("")}
      </div><button class="btn btn-outline-primary" data-calendar-control="today">Today</button></div>
    </div>
    <div class="calendar-surface">${surface}<div class="calendar-loader">${window.ClassaritLoading?.calendar('calendar') || 'Loading calendar…'}</div></div>
  </section>`;
}

export function renderAgendaCalendar(s, {hint = true} = {}) {
  const zone=s.workspace.timezone, today=dateKey(new Date(),zone);
  const days=Array.from({length:7},(_,i)=>shiftDay(today,i));
  const grid = (keys,label,css) => `<section class="workspace-card compact-calendar agenda-calendar ${css}"><div class="calendar-head"><h2>${label}</h2><small>${esc(zone)}</small></div><div class="weekday-row">${keys.map(key=>`<span>${esc(new Date(`${key}T12:00:00Z`).toLocaleDateString(undefined,{timeZone:'UTC',weekday:'short'}))}</span>`).join('')}</div><div class="month-grid">${keys.map(key=>{
    const sessions=agendaSessions(s,key);
    return `<button type="button" class="calendar-day agenda-day${key===today?' today':''}" data-calendar-day="${key}" aria-label="${esc(dayLabel(key))}: ${sessions.length} activities"><strong>${esc(new Date(`${key}T12:00:00Z`).toLocaleDateString(undefined,{timeZone:'UTC',month:'short',day:'numeric'}))}</strong><span class="day-markers">${renderDayLabels(sessions,key,zone)}</span>${sessions.length?'':'<small class="agenda-free">Free</small>'}</button>`;
  }).join('')}</div></section>`;
  return `<div class="calendar-legend agenda-legend">${[['program','Class'],['session','Event']].map(([glyph,label])=>`<span class="calendar-key kind-${glyph}">${icon(glyph)} ${label}</span>`).join('')}${hint ? '<small>Click a date to see all schedules</small>' : ''}</div>`+grid(days,'Upcoming classes','agenda-week');
}
function agendaSessions(s,key) {
  const zone=s.workspace.timezone;
  return s.sessions.filter(x=>x.status==='SCHEDULED' && new Date(x.ends_at)>new Date() && dateKey(x.starts_at,zone)<=key && dateKey(new Date(new Date(x.ends_at)-1),zone)>=key).sort((a,b)=>new Date(a.starts_at)-new Date(b.starts_at));
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

export function openCalendarDay(s, key, manager = false, agenda = false, {
  renderActions,
  describeSession = (session) => {
    const venue = session.venue_id ? s.venues.find((row) => row.id === session.venue_id)?.name : '';
    return `${session.delivery_mode} · ${session.status}${session.venue_id ? ` · ${venue || ''}` : ''}`;
  },
  emptyText = 'No classes or sessions on this day.',
} = {}) {
  const day = agenda ? {key, sessions:agendaSessions(s,key),past:key<dateKey(new Date(),s.workspace.timezone)} : calendarDays(s).find((d) => d.key === key);
  if (!day) return;
  if (!agenda && calendarState.view === 'month') calendarState.anchor = key;
  const manageable = manager && !day.past;
  const modal = calendarPopup();
  const panel = modal.querySelector(".calendar-popup-panel");
  panel.innerHTML = `<div class="editor-heading day-popup-heading"><h2 id="calendar-day-title">${esc(dayLabel(key))}</h2><div class="day-popup-actions">${manageable ? `<button type="button" class="btn btn-primary day-icon-button" data-calendar-action="session" data-date-key="${esc(key)}" title="Add schedule" aria-label="Add schedule">${icon("session")}</button>` : ""}<button type="button" class="day-icon-button day-popup-close" aria-label="Close day schedule" title="Close">${icon("cross")}</button></div></div>${day.sessions.length ? day.sessions.map((x) => {
    const canChange = manageable && x.status === "SCHEDULED" && new Date(x.starts_at) > new Date();
    const actions = renderActions ? renderActions(x, key) : canChange
      ? `<button type="button" class="btn btn-outline-primary day-icon-button" data-calendar-action="reschedule" data-id="${esc(x.id)}" title="Edit schedule" aria-label="Edit schedule: ${esc(x.title)}">${icon("edit")}</button>`
      : '';
    return `<article class="day-session compact-day-session"><div class="day-session-details" tabindex="0" role="group" aria-label="Schedule details for ${esc(x.title)}"><strong>${esc(x.title)}</strong><span class="day-session-time">${esc(slot(x,key,s.workspace.timezone))}</span><small>${esc(describeSession(x, key))}</small></div>${actions ? `<div class="row-actions">${actions}</div>` : ''}</article>`;
  }).join("") : `<p class="day-empty">${esc(emptyText)}</p>`}`;
  panel.querySelector('button[aria-label="Close day schedule"]').onclick =
    closeCalendarPopup;
  modal.hidden = false;
}
