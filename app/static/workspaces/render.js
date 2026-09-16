import { esc } from "./api.js?v=workspace-reporting-20260915";
import { icon } from "./icons.js?v=workspace-reporting-20260915";
import { renderCalendar } from "./calendar.js?v=workspace-reporting-20260915";
export const button = (label, action, id = "", kind = "outline-primary") =>
  `<button type="button" class="btn btn-sm btn-${kind} action-icon" title="${esc(label)}" aria-label="${esc(label)}" data-action="${action}" data-id="${esc(id)}">${icon(action)}</button>`;
const badge = (x) => `<span class="badge-soft">${esc(x)}</span>`;
const table = (heads, rows, empty = "Nothing here yet.") =>
  rows.length
    ? `<div class="workspace-card table-scroll" tabindex="0" role="region" aria-label="Scrollable table"><table class="workspace-table"><thead><tr>${heads.map((x) => `<th>${esc(x)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
    : `<div class="workspace-card empty">${esc(empty)}</div>`;
export function render(s, tab) {
  const manager = s.roles.some((r) =>
      ["OWNER", "ADMIN", "OPERATOR"].includes(r),
    ),
    admin = s.roles.some((r) => ["OWNER", "ADMIN"].includes(r));
  const name = (rows, id) =>
    rows.find((r) => r.id === id)?.name ||
    rows.find((r) => r.id === id)?.full_name ||
    "—";
  const time = (t) =>
    new Date(t).toLocaleString(undefined, {
      timeZone: s.workspace.timezone,
      dateStyle: "medium",
      timeStyle: "short",
    });
  const head = (title, actions = "") =>
    `<div class="section-heading"><h2>${title}</h2></div>${actions ? `<div class="section-actions-inline">${actions}</div>` : ""}`;
  const sessionLocation = (ss) =>
    `${badge(ss.delivery_mode)} ${ss.venue_id ? esc(name(s.venues, ss.venue_id)) : ""} ${s.venues.find((v) => v.id === ss.venue_id)?.map_url ? `<a href="${esc(s.venues.find((v) => v.id === ss.venue_id).map_url)}" target="_blank" rel="noopener noreferrer">View directions ↗</a>` : ""} ${ss.meeting_url ? `<a href="${esc(ss.meeting_url)}" target="_blank" rel="noopener noreferrer">Open meeting ↗</a>` : ""}`;
  const sessionCard = (ss, label = "") => {
    const people = s.participants.filter(
        (p) => p.session_id === ss.id && p.status === "BOOKED",
      ),
      program = s.programs.find((p) => p.id === ss.program_id);
    const future = new Date(ss.starts_at) > new Date();
    return `<section class="workspace-card session-card"><div class="section-heading"><div><h3>${esc(ss.title)} ${label ? badge(label) : ""}</h3><p class="subtext">${esc(time(ss.starts_at))} – ${esc(time(ss.ends_at))} · ${people.length}/${ss.capacity} seats</p></div>${badge(ss.status)}</div><p>${sessionLocation(ss)}</p><div class="row-actions">${manager && ss.status === "SCHEDULED" ? `${future ? button("Reschedule", "reschedule", ss.id) : ""}${button("Cancel", "cancel", ss.id)}${program?.program_kind === "EVENT" && future ? button("Book student", "event", ss.id) : ""}` : ""}${ss.status === "SCHEDULED" && new Date(ss.ends_at) <= new Date() ? button("Complete session", "complete", ss.id) : ""}</div>${
      people.length
        ? `<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable table"><table class="workspace-table"><tbody>${people
            .map((p) => {
              const att = s.attendance.find((x) => x.participant_id === p.id);
              return `<tr><td>${esc(name(s.students, p.student_id))} ${badge(p.participation_kind)}</td><td>${badge(att?.status || "Not marked")}</td><td><div class="row-actions">${!future && ss.status !== "CANCELLED" ? button("Attendance", "attendance", p.id) : ""}${manager && p.participation_kind !== "MAKEUP" ? button("Grant makeup", "grant", p.id) : ""}</div></td></tr>`;
            })
            .join("")}</tbody></table></div>`
        : '<p class="subtext">No students booked yet.</p>'
    }</section>`;
  };
  const reportMetrics = () => {
    const metrics = s.metrics || {};
    return `<div class="metric-grid">${[
      ["Students", metrics.students ?? s.students.length],
      ["Classes", metrics.classes ?? s.programs.length],
      [
        "Upcoming sessions",
        metrics.upcoming_sessions ??
          s.sessions.filter(
            (x) => x.status === "SCHEDULED" && new Date(x.starts_at) > new Date(),
          ).length,
      ],
      [
        "Teachers",
        metrics.teachers ??
          s.members.filter(
            (x) => x.status === "ACTIVE" && x.roles?.includes("TEACHER"),
          ).length,
      ],
    ]
      .map(
        ([label, n]) =>
          `<div class="metric compact-metric">${icon({Students:"student",Classes:"program","Upcoming sessions":"session",Teachers:"teachers"}[label])}<strong>${n}</strong><span>${label}</span></div>`,
      )
      .join("")}</div>`;
  };
  if (tab === "calendar") return renderCalendar(s);
  if (tab === "reporting")
    return (
      head("Reporting") +
      reportMetrics() +
      `<section class="workspace-card"><h3>Workspace reporting</h3><p class="subtext">This section will hold owner reporting. The cards above moved here from the old overview page.</p></section>`
    );
  if (tab === "classes")
    return (
      head(
        "Classes & events",
        manager
          ? button("Create class or event", "program", "", "primary")
          : "",
      ) +
      table(
        ["Name", "Activity", "Format", "Teachers", "Enrollment", ""],
        s.programs.map((p) => [
          `${esc(p.name)}<div class="subtext">${esc(p.level || "All levels")}</div>`,
          esc(name(s.activities, p.activity_id)),
          badge(p.program_kind) + " " + badge(p.default_delivery_mode),
          esc(
            s.program_teachers
              .filter((t) => t.program_id === p.id)
              .map((t) => name(s.members, t.membership_id))
              .join(", "),
          ),
          `${s.enrollments.filter((e) => e.program_id === p.id && e.status === "ACTIVE").length} / ${p.capacity}`,
          manager
            ? `<div class="row-actions">${p.program_kind === "COURSE" ? button("Enroll student", "enroll", p.id) : ""}${button("Schedule", "session", p.id)}${button("Teachers", "teachers", p.id)}</div>`
            : "",
        ]),
        "No classes yet.",
      )
    );
  if (tab === "students")
    return (
      head(
        "Students",
        manager ? button("Add student", "student", "", "primary") : "",
      ) +
      table(
        ["Student", "Contact", "Guardian", "Classes", ""],
        s.students.map((st) => {
          const g = s.guardians.find((g) =>
            s.student_guardians.some(
              (l) => l.student_id === st.id && l.guardian_id === g.id,
            ),
          );
          return [
            esc(st.full_name),
            `${esc(st.email)}<br>${esc(st.phone)}`,
            g
              ? `${esc(g.full_name)}<div class="subtext">${esc(g.phone || g.email)}</div>`
              : "—",
            s.enrollments
              .filter((e) => e.student_id === st.id)
              .map(
                (e) =>
                  `${esc(name(s.programs, e.program_id))} ${badge(e.status)} ${manager && e.status === "ACTIVE" ? button("End", "end-enrollment", e.id) : ""}`,
              )
              .join("<br>"),
            manager ? button("Edit", "edit-student", st.id) : "",
          ];
        }),
      )
    );
  if (tab === "venues")
    return (
      head(
        "Venues",
        manager ? button("Add venue", "venue", "", "primary") : "",
      ) +
      table(
        ["Venue", "Address", "Spaces"],
        s.venues.map((v) => [
          esc(v.name),
          `${esc(v.address)}<div class="subtext">${esc(v.directions)}</div>`,
          esc(
            s.spaces
              .filter((r) => r.venue_id === v.id)
              .map((r) => r.name)
              .join(", "),
          ),
        ]),
        "No venues yet.",
      )
    );
  if (tab === "team")
    return (
      head(
        "Your team",
        admin ? button("Invite member", "invite", "", "primary") : "",
      ) +
      table(
        ["Name", "Roles", "Status", ""],
        s.members.map((m) => [
          esc(m.full_name),
          m.roles.map(badge).join(" "),
          badge(m.status),
          admin ? button("Manage", "member", m.id) : "",
        ]),
      ) +
      (admin
        ? head("Invitations") +
          table(
            ["Email", "Roles", "Status", ""],
            s.invitations.map((i) => [
              esc(i.email),
              i.proposed_roles.map(badge).join(" "),
              badge(
                i.status === "PENDING" && new Date(i.expires_at) < new Date()
                  ? "EXPIRED"
                  : i.status,
              ),
              i.status === "PENDING" ? button("Revoke", "revoke", i.id) : "",
            ]),
          )
        : "")
    );
  if (tab === "sessions") {
    const now = new Date();
    const historyIncluded = Boolean(s.history_included);
    const actionButton = (label, action, id = "", kind = "outline-primary") =>
      `<button type="button" class="btn btn-sm btn-${kind} labeled-action schedule-card-action" title="${esc(label)}" aria-label="${esc(label)}" data-action="${esc(action)}" data-id="${esc(id)}">${icon(action === "cancel" || action === "disable-series" ? "close" : action === "edit-series" ? "edit" : action)}<span>${esc(label)}</span></button>`;
    const peopleFor = (sessions) => {
      const ids = new Set(sessions.map((ss) => ss.id));
      const rows = s.participants.filter(
        (p) => ids.has(p.session_id) && p.status === "BOOKED",
      );
      const unique = [];
      const seen = new Set();
      for (const row of rows) {
        if (seen.has(row.student_id)) continue;
        seen.add(row.student_id);
        unique.push({
          name: name(s.students, row.student_id),
          kind: row.participation_kind,
        });
      }
      return unique;
    };
    const peopleText = (people) =>
      people.length ? people.map((p) => p.name).join(", ") : "No students booked yet";
    const studentChips = (people) =>
      people.length
        ? people
            .map((p) => `<span class="schedule-student-chip">${esc(p.name)} <small>${esc(p.kind)}</small></span>`)
            .join("")
        : '<span class="subtext">No students booked yet.</span>';
    const nextSessions = (sessions, limit = 4) =>
      sessions
        .filter((ss) => ss.status === "SCHEDULED" && new Date(ss.starts_at) > now)
        .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
        .slice(0, limit);
    const sessionCountLeft = (sessions) =>
      sessions.filter((ss) => ss.status === "SCHEDULED" && new Date(ss.starts_at) > now).length;
    const detailGrid = (rows) =>
      `<dl class="schedule-detail-grid">${rows
        .map(
          ([label, value]) =>
            `<div><dt>${esc(label)}</dt><dd>${value}</dd></div>`,
        )
        .join("")}</dl>`;
    const describeSeries = (r, sessions) => {
      const weekdays = (r.repeat_weekdays || []).join(" + ") || "Weekly";
      const startTime = String(r.start_time || "").slice(0, 5);
      const months = Number(r.repeat_months || 0);
      const repeatFor = months ? `${months} month${months === 1 ? "" : "s"}` : "repeat";
      const range = sessions.length
        ? `${esc(time(sessions[0].starts_at))} – ${esc(time(sessions[sessions.length - 1].starts_at))}`
        : `${esc(r.start_date || "")} ${esc(startTime)}`;
      return `${esc(weekdays)} · ${esc(repeatFor)} · ${range}`;
    };
    const recurringCard = (r) => {
      const sessions = s.sessions
        .filter((ss) => ss.recurring_series_id === r.id)
        .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
      const standard = sessions.filter((ss) => !ss.edited_from_series);
      const custom = sessions.filter((ss) => ss.edited_from_series);
      const left = sessionCountLeft(sessions);
      const active = (r.status || "ACTIVE") === "ACTIVE";
      const programName = name(s.programs, r.program_id);
      const people = peopleFor(sessions);
      const upcoming = nextSessions(sessions);
      const cancelledFutureStandard = standard.filter(
        (ss) => ss.status === "CANCELLED" && new Date(ss.starts_at) > now,
      ).length;
      const actions = manager
        ? `<div class="schedule-actions">${active ? actionButton("Edit", "edit-series", r.id) : ""}${active && left ? actionButton("Disable", "disable-series", r.id, "outline-danger") : ""}${!active && cancelledFutureStandard ? actionButton("Restore", "restore-series", r.id, "outline-primary") : ""}</div>`
        : "";
      return `<details class="workspace-card schedule-collapse">
        <summary class="schedule-summary">
          <span class="schedule-caret" aria-hidden="true">▾</span>
          <span class="schedule-title-block"><strong>${esc(programName)}</strong><small>${esc(r.title || programName)}</small></span>
          <span class="schedule-summary-text">${describeSeries(r, standard)}</span>
          <span class="schedule-summary-text">${esc(peopleText(people))}</span>
          <span class="schedule-pill">${esc(active ? "ACTIVE" : "DISABLED")}</span>
          <span class="schedule-left"><strong>${left}</strong><small>sessions left</small></span>
          ${actions}
        </summary>
        <div class="schedule-detail-body">
          ${detailGrid([
            ["Class name", esc(programName)],
            ["Title", esc(r.title || programName)],
            ["Recurring details", describeSeries(r, standard)],
            ["Status", badge(active ? "ACTIVE" : "DISABLED")],
            ["Sessions left", `<strong>${left}</strong>`],
            ["Generated", `${standard.length} standard · ${custom.length} custom`],
            ["Can restore", cancelledFutureStandard ? `${cancelledFutureStandard} future standard sessions` : "No future disabled sessions"],
          ])}
          <section class="schedule-students"><h4>Student(s)</h4><div>${studentChips(people)}</div></section>
          <section class="schedule-students"><h4>Basic info</h4><p class="subtext">Disable cancels future standard occurrences. Custom edited dates stay on the calendar. Restore reactivates future standard occurrences cancelled by this schedule.</p>${upcoming.length ? `<ul class="schedule-mini-list">${upcoming.map((ss) => `<li>${esc(time(ss.starts_at))} · ${esc(ss.status)}</li>`).join("")}</ul>` : '<p class="subtext">No upcoming sessions left.</p>'}</section>
        </div>
      </details>`;
    };
    const occurrenceCard = (ss, label = "One-time") => {
      const program = s.programs.find((p) => p.id === ss.program_id);
      const people = peopleFor([ss]);
      const future = new Date(ss.starts_at) > now;
      const left = ss.status === "SCHEDULED" && future ? 1 : 0;
      const series = s.recurring_series.find((r) => r.id === ss.recurring_series_id);
      const recurring = ss.recurring_series_id
        ? `Custom occurrence from ${esc(series?.title || name(s.programs, series?.program_id))}`
        : "One-time session";
      const actions = manager
        ? `<div class="schedule-actions">${ss.status === "SCHEDULED" && future ? actionButton("Edit", "reschedule", ss.id) : ""}${ss.status === "SCHEDULED" ? actionButton("Delete", "cancel", ss.id, "outline-danger") : ""}</div>`
        : "";
      const operational = `${program?.program_kind === "EVENT" && future ? actionButton("Book student", "event", ss.id) : ""}${ss.status === "SCHEDULED" && new Date(ss.ends_at) <= now ? actionButton("Complete", "complete", ss.id) : ""}`;
      return `<details class="workspace-card schedule-collapse">
        <summary class="schedule-summary">
          <span class="schedule-caret" aria-hidden="true">▾</span>
          <span class="schedule-title-block"><strong>${esc(name(s.programs, ss.program_id))}</strong><small>${esc(ss.title || name(s.programs, ss.program_id))}</small></span>
          <span class="schedule-summary-text">${esc(recurring)}</span>
          <span class="schedule-summary-text">${esc(peopleText(people))}</span>
          <span class="schedule-pill">${esc(ss.status)}</span>
          <span class="schedule-left"><strong>${left}</strong><small>sessions left</small></span>
          ${actions}
        </summary>
        <div class="schedule-detail-body">
          ${detailGrid([
            ["Class name", esc(name(s.programs, ss.program_id))],
            ["Title", esc(ss.title || name(s.programs, ss.program_id))],
            ["Recurring details", esc(recurring)],
            ["Time", `${esc(time(ss.starts_at))} – ${esc(time(ss.ends_at))}`],
            ["Status", badge(ss.status)],
            ["Sessions left", `<strong>${left}</strong>`],
            ["Location", sessionLocation(ss)],
          ])}
          <section class="schedule-students"><h4>Student(s)</h4><div>${studentChips(people)}</div></section>
          ${operational ? `<div class="row-actions schedule-secondary-actions">${operational}</div>` : ""}
          ${people.length
            ? `<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable attendance table"><table class="workspace-table"><tbody>${s.participants
                .filter((p) => p.session_id === ss.id && p.status === "BOOKED")
                .map((p) => {
                  const att = s.attendance.find((x) => x.participant_id === p.id);
                  return `<tr><td>${esc(name(s.students, p.student_id))} ${badge(p.participation_kind)}</td><td>${badge(att?.status || "Not marked")}</td><td><div class="row-actions">${!future && ss.status !== "CANCELLED" ? button("Attendance", "attendance", p.id) : ""}${manager && p.participation_kind !== "MAKEUP" ? button("Grant makeup", "grant", p.id) : ""}</div></td></tr>`;
                })
                .join("")}</tbody></table></div>`
            : ""}
        </div>
      </details>`;
    };
    const series = s.recurring_series || [];
    const activeSeries = series.filter((r) => (r.status || "ACTIVE") === "ACTIVE");
    const disabledSeries = series.filter((r) => (r.status || "ACTIVE") !== "ACTIVE");
    const activeSeriesCards = activeSeries.map(recurringCard).join("");
    const disabledSeriesCards = disabledSeries.map(recurringCard).join("");
    const edited = s.sessions
      .filter((ss) => ss.recurring_series_id && ss.edited_from_series && ss.status !== "CANCELLED")
      .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
    const cancelledEdited = historyIncluded
      ? s.sessions
          .filter((ss) => ss.recurring_series_id && ss.edited_from_series && ss.status === "CANCELLED")
          .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
      : [];
    const oneOff = s.sessions
      .filter((ss) => !ss.recurring_series_id && ss.status !== "CANCELLED")
      .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
    const cancelledOneOff = historyIncluded
      ? s.sessions
          .filter((ss) => !ss.recurring_series_id && ss.status === "CANCELLED")
          .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
      : [];
    const cancelledOccurrences = [...cancelledEdited, ...cancelledOneOff];
    const historyAction = `<button type="button" class="btn btn-outline-primary labeled-action" data-schedule-history="${historyIncluded ? "false" : "true"}" title="${historyIncluded ? "Show active schedules only" : "Fetch previous recurring and one-time schedules"}">${icon(historyIncluded ? "check" : "makeup")}<span>${historyIncluded ? "Show active only" : "View previous schedules"}</span></button>`;
    const scheduleHeader = `<div class="section-heading schedule-page-heading"><h2 class="schedule-page-title">Schedule &amp; attendance</h2></div><div class="section-actions-inline schedule-history-actions">${historyAction}</div>`;
    const body =
      (activeSeriesCards ? head("Recurring schedules") + `<div class="schedule-stack">${activeSeriesCards}</div>` : "") +
      (edited.length
        ? head("Custom changes from recurring schedules") + `<div class="schedule-stack">${edited.map((ss) => occurrenceCard(ss, "Custom occurrence")).join("")}</div>`
        : "") +
      (oneOff.length
        ? head("One-time sessions") + `<div class="schedule-stack">${oneOff.map((ss) => occurrenceCard(ss)).join("")}</div>`
        : "") +
      (historyIncluded && disabledSeriesCards
        ? head("Previous recurring schedules") + `<div class="schedule-stack muted-schedule-stack">${disabledSeriesCards}</div>`
        : "") +
      (historyIncluded && cancelledOccurrences.length
        ? head("Previous one-time or custom sessions") + `<div class="schedule-stack muted-schedule-stack">${cancelledOccurrences.map((ss) => occurrenceCard(ss)).join("")}</div>`
        : "") +
      (!activeSeriesCards && !edited.length && !oneOff.length && (!historyIncluded || (!disabledSeriesCards && !cancelledOccurrences.length))
        ? `<section class="workspace-card empty">${historyIncluded ? "No schedules found." : "No active schedules right now. Use View previous schedules to fetch older or cancelled items."}</section>`
        : "");
    return scheduleHeader + body;
  }
  if (tab === "makeups")
    return (
      head("Makeup classes", admin ? button("Edit policy", "policy") : "") +
      `<section class="workspace-card"><p>Cancellation credits: <strong>${s.policy.teacher_cancellation_eligible ? "Enabled" : "Disabled"}</strong> · Student absence: <strong>${s.policy.student_absence_eligible ? "Enabled" : "Disabled"}</strong> · Valid for: <strong>${s.policy.validity_days || "Unlimited"} days</strong></p><p class="subtext">A credit is fulfilled only when replacement attendance is marked present or late. Prices and payment collection are not connected to makeup credits yet.</p></section>` +
      table(
        ["Student", "Reason", "Expires", "State", ""],
        s.entitlements.map((e) => {
          const b = s.bookings.find(
              (b) =>
                b.entitlement_id === e.id &&
                ["BOOKED", "FULFILLED"].includes(b.status),
            ),
            expired = e.expires_at && new Date(e.expires_at) < new Date();
          return [
            esc(name(s.students, e.student_id)),
            esc(e.reason),
            e.expires_at ? esc(time(e.expires_at)) : "No expiry",
            badge(
              b?.status ||
                (expired && e.status === "OPEN" ? "EXPIRED" : e.status),
            ),
            manager && e.status === "OPEN"
              ? b
                ? button("Release booking", "release", b.id)
                : !expired
                  ? button("Book replacement", "makeup", e.id)
                  : ""
              : "",
          ];
        }),
        "No makeup credits yet.",
      )
    );
  return "";
}
