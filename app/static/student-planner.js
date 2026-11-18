import { esc, notice } from "./workspaces/api.js?v=global-loading-20260930";
import { dateKey } from "./workspaces/calendar.js?v=student-calendar";
import { studentTimeZone } from "./student-calendar.js?v=student-calendar";
import { icon } from "./workspaces/icons.js?v=global-loading-20260930";
import { openStudentPopup } from "./student-popups.js";

export async function mountStudentPlanner(request, report) {
  const { edit, field } = await import("./workspaces/forms.js?v=global-loading-20260930");
  const addButton = document.querySelector("#add-planner-event");
  const list = document.querySelector("#planner-list");
  const weekdays = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];

  async function loadGroups() {
    if (!list) return;
    if (!list.children.length) list.innerHTML = '<div class="student-skeleton" role="status" aria-label="Loading planner"></div>';
    try {
      const { groups } = await request("/api/student/planner");
      list.innerHTML = groups.map(group => `<button type="button" class="planner-group" data-planner-group="${esc(group.id)}">
        <span class="planner-group-icon">${icon(group.count > 1 ? "makeup" : "session")}</span>
        <strong>${esc(group.title)}</strong><span class="planner-group-type">${group.count > 1 ? `Series · ${group.count} events` : "Single event"}</span>
        <time>${esc(new Intl.DateTimeFormat(undefined, { timeZone: group.timezone, dateStyle: "medium" }).format(new Date(group.starts_at)))}</time>
        <span class="planner-group-next">${group.upcoming_count} upcoming</span>
        <span aria-hidden="true">›</span></button>`).join("") ||
        '<p class="student-empty">Your planner is empty. Add a schedule to get started.</p>';
    } catch (error) {
      list.innerHTML = '<p class="student-empty">Could not load your planner. Refresh to try again.</p>';
      report(error);
    }
  }

  function openEditor(tasks = [], slot = {}) {
    const first = tasks[0];
    const zone = first?.timezone || studentTimeZone;
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const startDate = slot.dateKey || dateKey(first?.starts_at || tomorrow, zone);
    const startTime = first ? new Intl.DateTimeFormat("en-GB", {
      timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).format(new Date(first.starts_at)) : slot.startTime || "09:00";
    const scheduleType = tasks.length > 1 ? "existing" : "once";
    const weekly = { field: "schedule_type", values: ["weekly"] };
    const options = [{ id: "once", name: "One event" }, { id: "weekly", name: "Repeat weekly" }];
    if (tasks.length > 1) options.unshift({ id: "existing", name: "Keep existing dates" });
    const fields = [
      field("schedule_type", "Schedule", "select", { options, value: scheduleType, required: true }),
      field("title", "Task or activity", "text", { required: true, value: first?.title }),
      field("start_date", "Start date", "date", {
        value: startDate, required: true,
        help: tasks.length > 1 ? "Changing this date moves the whole group by the same number of days." : undefined,
      }),
      field("start_time", `Start time (${zone})`, "time", { value: startTime, required: true }),
      field("duration_minutes", "Duration in minutes", "number", {
        value: first ? Math.round((new Date(first.ends_at) - new Date(first.starts_at)) / 60000) : slot.durationMinutes || 60,
        min: 1, max: 1440, required: true,
      }),
      field("repeat_weekdays", "Repeat on", "weekday-multiple", {
        options: weekdays.map(day => ({ id: day, name: day[0] + day.slice(1).toLowerCase() })),
        value: first?.recurrence?.repeat_weekdays || [weekdays[(new Date(startDate + "T12:00:00").getDay() + 6) % 7]],
        required: true, visibleWhen: weekly,
      }),
      field("repeat_months", "Repeat for", "select", {
        options: [1, 2, 3, 6, 12].map(months => ({ id: months, name: `${months} ${months === 1 ? "month" : "months"}` })),
        value: first?.recurrence?.repeat_months || 3, required: true, visibleWhen: weekly,
      }),
      field("location", "Location (optional)", "text", { value: first?.location }),
      field("notes", "Notes (optional)", "textarea", { value: first?.notes }),
    ];
    edit(first ? "Edit schedule" : "Schedule event", fields, async data => {
      const payload = {
        title: data.title, starts_at: `${data.start_date}T${data.start_time}`,
        duration_minutes: data.duration_minutes, timezone: zone, location: data.location,
        notes: data.notes, repeat: data.schedule_type === "weekly" ? "WEEKLY" : "NONE",
        preserve_dates: data.schedule_type === "existing",
      };
      if (data.schedule_type === "weekly") {
        payload.repeat_weekdays = data.repeat_weekdays;
        payload.repeat_months = Number(data.repeat_months);
      }
      const path = first ? `/api/student/planner/series/${first.series_id}` : "/api/student/planner/tasks";
      const result = await request(path, first ? "PATCH" : "POST", payload);
      await loadGroups();
      document.dispatchEvent(new Event("student-planner-changed"));
      notice(first ? "Schedule updated." : result.count > 1 ? `Added ${result.count} events to your planner.` : "Added to your planner.");
    }, first ? {
      onDelete: async () => {
        if (!confirm(`Delete ${tasks.length === 1 ? "this event" : `all ${tasks.length} events in this group`}?`)) return;
        const removeButton = document.querySelector("#delete-editor");
        removeButton.disabled = true;
        try {
          await request(`/api/student/planner/series/${first.series_id}`, "DELETE");
          document.querySelector("#editor").close();
          await loadGroups();
          document.dispatchEvent(new Event("student-planner-changed"));
          notice("Schedule deleted.");
        } catch (error) { report(error, true); }
        finally { removeButton.disabled = false; }
      },
    } : {});
  }

  addButton.disabled = false;
  document.addEventListener("student-schedule-slot", event => openEditor([],event.detail));
  addButton.addEventListener("click", () => openEditor());
  list?.addEventListener("click", async event => {
    const row = event.target.closest("[data-planner-group]");
    if (!row || row.disabled) return;
    row.disabled = true;
    try {
      const { tasks } = await request(`/api/student/planner/series/${encodeURIComponent(row.dataset.plannerGroup)}`);
      const first = tasks[0];
      const format = new Intl.DateTimeFormat(undefined, { timeZone: first.timezone, dateStyle: "medium", timeStyle: "short" });
      const popup = openStudentPopup("planner-details", first.title, `
        <div class="planner-detail-summary"><span class="planner-group-type">${tasks.length > 1 ? `Series · ${tasks.length} events` : "Single event"}</span>
          <span>${esc(first.timezone)}</span><button type="button" class="btn btn-outline-primary" data-edit-plan>Edit schedule</button></div>
        ${first.location ? `<p>${esc(first.location)}</p>` : ""}
        ${first.notes ? `<p class="planner-notes">${esc(first.notes)}</p>` : ""}
        <ol class="planner-occurrences">${tasks.map(task => `<li><a href="/student/calendar?date=${dateKey(task.starts_at, first.timezone)}">${esc(format.format(new Date(task.starts_at)))}</a>
          <span>${Math.round((new Date(task.ends_at) - new Date(task.starts_at)) / 60000)} min</span></li>`).join("")}</ol>`);
      popup.element.querySelector("[data-edit-plan]").onclick = () => { popup.close(false); openEditor(tasks); };
    } catch (error) { report(error); }
    finally { row.disabled = false; }
  });
  await loadGroups();
}
