import { esc, clearNotice } from "./workspaces/api.js?v=global-loading-20260930";
import {
  dateKey, getCalendarMonths, openCalendarDay, prepareCalendar, renderAgendaCalendar, renderCalendar,
  setCalendarAnchor, setCalendarLoading, setCalendarMonthData, updateCalendarView,
} from "./workspaces/calendar.js?v=student-calendar";

export const studentTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata";

function calendarEntries(data) {
  return [
    ...data.sessions,
    ...data.tasks.map((task) => ({
      ...task,
      personalEvent: true,
      session_kind: "EVENT",
      status: task.status === "COMPLETED" ? "COMPLETED" : "SCHEDULED",
    })),
  ];
}

function meetingLink(session) {
  if (session.status !== "SCHEDULED" || !session.meeting_url ||
      !["ONLINE", "HYBRID"].includes(session.delivery_mode) ||
      new Date(session.ends_at) <= new Date()) return "";
  try {
    const url = new URL(session.meeting_url);
    if (!["https:", "http:"].includes(url.protocol)) return "";
    return `<a class="btn btn-sm btn-outline-primary" data-meeting-window href="${esc(url.href)}" target="_blank" rel="noopener noreferrer" title="Join class in a separate window">Join class</a>`;
  } catch {
    return "";
  }
}

const deliveryName = { ONLINE: "Online", IN_PERSON: "In person", HYBRID: "Hybrid" };
const dayOptions = {
  renderActions: meetingLink,
  describeSession(session) {
    if (session.personalEvent) return ["Personal event", session.location].filter(Boolean).join(" · ");
    return [
      deliveryName[session.delivery_mode],
      session.status === "COMPLETED" && "Completed",
      session.venue_name,
      session.workspace_name,
    ].filter(Boolean).join(" · ");
  },
  emptyText: "Nothing scheduled.",
};

function validDay(key) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(key || "") || key.startsWith("0000")) return false;
  const date = new Date(`${key}T12:00:00Z`);
  return Number.isFinite(+date) && date.toISOString().slice(0, 10) === key;
}

export function mountStudentCalendar(root, dashboard, request, report) {
  document.addEventListener("click", (event) => {
    const link = event.target.closest("#calendar-popup [data-meeting-window]");
    if (!link || event.defaultPrevented || event.button !== 0 ||
        event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const width = Math.min(1100, window.screen.availWidth);
    const height = Math.min(760, window.screen.availHeight);
    const features = `popup=yes,width=${width},height=${height},resizable=yes,scrollbars=yes`;
    let meetingWindow;
    try {
      // Keep the handle long enough to detect blocking, then sever opener access.
      meetingWindow = window.open("about:blank", "_blank", features);
      if (!meetingWindow) return;
      meetingWindow.opener = null;
      meetingWindow.location.replace(link.href);
      meetingWindow.focus();
      event.preventDefault();
    } catch {
      meetingWindow?.close();
      // Let the original link work when a browser rejects popup navigation.
    }
  });
  const snapshot = { workspace: { timezone: studentTimeZone }, sessions: [], personalCalendar: true };
  const params = new URLSearchParams(location.search);
  const requestedDate = params.get("date");
  const monthStart = `${params.get("month")}-01`;
  let initialDay = validDay(requestedDate) ? requestedDate : null;
  if (!dashboard) {
    const anchor = initialDay || (validDay(monthStart) ? monthStart : null);
    if (anchor) setCalendarAnchor(anchor);
  }

  let loadVersion = 0;
  async function loadCalendar() {
    const version = ++loadVersion;
    const months = getCalendarMonths(snapshot);
    setCalendarLoading(true);
    root.innerHTML = renderCalendar(snapshot);
    prepareCalendar(root);
    try {
      const results = await Promise.all(months.map((month) => {
        const query = new URLSearchParams({ month, timezone: studentTimeZone });
        return request(`/api/student/calendar?${query}`);
      }));
      if (version !== loadVersion) return;
      const entries = results.flatMap(calendarEntries);
      snapshot.sessions = [...new Map(entries.map((entry) => [
        `${entry.personalEvent ? "personal" : "class"}:${entry.id}`, entry,
      ])).values()];
      setCalendarMonthData({ month: months[0], sessions: snapshot.sessions });
    } catch (error) {
      if (version !== loadVersion) return;
      snapshot.sessions = [];
      setCalendarMonthData({ month: months[0], sessions: [] });
      initialDay = null;
      report(error);
    }
    if (version !== loadVersion) return;
    setCalendarLoading(false);
    root.innerHTML = renderCalendar(snapshot);
    prepareCalendar(root);
    if (initialDay) {
      openCalendarDay(snapshot, initialDay, false, false, dayOptions);
      initialDay = null;
    }
  }

  root.addEventListener("click", (event) => {
    const timeSlot = event.target.closest("[data-calendar-slot]");
    if (timeSlot && !timeSlot.disabled) {
      root.querySelectorAll(".calendar-time-slot.is-selected").forEach(slot => slot.classList.remove("is-selected"));
      timeSlot.classList.add("is-selected");
      document.dispatchEvent(new CustomEvent("student-schedule-slot", { detail: {
        dateKey: timeSlot.dataset.calendarSlot, startTime: timeSlot.dataset.startTime, durationMinutes: 30,
      } }));
      return;
    }
    const timeEvent = event.target.closest("[data-calendar-event]");
    if (timeEvent) {
      openCalendarDay(snapshot, timeEvent.dataset.dateKey, false, false, dayOptions);
      return;
    }
    const control = event.target.closest("[data-calendar-control]");
    if (control) {
      initialDay = null;
      clearNotice();
      updateCalendarView(control.dataset.calendarControl, snapshot);
      loadCalendar();
      return;
    }
    const day = event.target.closest("[data-calendar-day]");
    if (day) openCalendarDay(snapshot, day.dataset.calendarDay, false, dashboard, dayOptions);
  });

  async function loadDashboard() {
    root.innerHTML = window.ClassaritLoading?.calendar("upcoming classes") || '<div class="student-skeleton"></div>';
    await request("/api/student/upcoming").then((data) => {
      snapshot.sessions = calendarEntries(data);
      root.innerHTML = renderAgendaCalendar(snapshot, { hint: false });
    }).catch((error) => {
      root.replaceChildren();
      report(error);
    });
  }
  document.addEventListener("student-planner-changed", () => {
    if (dashboard) loadDashboard();
    else loadCalendar();
  });
  if (dashboard) {
    loadDashboard();
  } else {
    loadCalendar();
  }
}
