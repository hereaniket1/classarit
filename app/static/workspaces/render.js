import { esc } from "./api.js";
export const button = (label, action, id = "", kind = "outline-primary") =>
  `<button type="button" class="btn btn-sm btn-${kind}" data-action="${action}" data-id="${esc(id)}">${esc(label)}</button>`;
const badge = (x) => `<span class="badge-soft">${esc(x)}</span>`;
const table = (heads, rows, empty = "Nothing here yet.") =>
  rows.length
    ? `<div class="workspace-card table-scroll"><table class="workspace-table"><thead><tr>${heads.map((x) => `<th>${esc(x)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
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
    `<div class="section-heading"><h2>${title}</h2><div class="row-actions">${actions}</div></div>`;
  if (tab === "overview")
    return (
      head(
        "A little more space to teach",
        manager ? button("Schedule a session", "session", "", "primary") : "",
      ) +
      `<div class="metric-grid">${[
        ["Students", s.students.length],
        ["Classes & events", s.programs.length],
        [
          "Upcoming sessions",
          s.sessions.filter(
            (x) =>
              x.status === "SCHEDULED" && new Date(x.starts_at) > new Date(),
          ).length,
        ],
        [
          "Open makeup credits",
          s.entitlements.filter(
            (x) =>
              x.status === "OPEN" &&
              (!x.expires_at || new Date(x.expires_at) > new Date()),
          ).length,
        ],
      ]
        .map(
          ([label, n]) =>
            `<div class="metric"><strong>${n}</strong><span>${label}</span></div>`,
        )
        .join(
          "",
        )}</div><section class="workspace-card"><h3>Build your teaching day</h3><p>Add your students, create a class or sports event, then schedule sessions. Course enrollments automatically fill the session roster.</p>${manager ? `<div class="row-actions">${button("Add student", "student")}${button("Create class or event", "program")}${button("Add venue", "venue")}</div>` : "<p>Your assigned classes and sessions appear in the navigation.</p>"}</section>`
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
        "Create a class for ongoing lessons, or an event for a one-off sports or arts session.",
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
        "Add rooms, grounds, pitches or courts for in-person and hybrid sessions.",
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
  if (tab === "sessions")
    return (
      head(
        "Schedule & attendance",
        manager ? button("Schedule session", "session", "", "primary") : "",
      ) +
      s.sessions
        .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
        .map((ss) => {
          const people = s.participants.filter(
              (p) => p.session_id === ss.id && p.status === "BOOKED",
            ),
            program = s.programs.find((p) => p.id === ss.program_id);
          const future = new Date(ss.starts_at) > new Date();
          return `<section class="workspace-card"><div class="section-heading"><div><h3>${esc(ss.title)}</h3><p class="subtext">${esc(time(ss.starts_at))} – ${esc(time(ss.ends_at))} · ${people.length}/${ss.capacity} seats</p></div>${badge(ss.status)}</div><p>${badge(ss.delivery_mode)} ${ss.venue_id ? esc(name(s.venues, ss.venue_id)) : ""} ${s.venues.find((v) => v.id === ss.venue_id)?.map_url ? `<a href="${esc(s.venues.find((v) => v.id === ss.venue_id).map_url)}" target="_blank" rel="noopener noreferrer">View directions ↗</a>` : ""} ${ss.meeting_url ? `<a href="${esc(ss.meeting_url)}" target="_blank" rel="noopener noreferrer">Open meeting ↗</a>` : ""}</p><div class="row-actions">${manager && ss.status === "SCHEDULED" ? `${future ? button("Reschedule", "reschedule", ss.id) : ""}${button("Cancel", "cancel", ss.id)}${program?.program_kind === "EVENT" && future ? button("Book student", "event", ss.id) : ""}` : ""}${ss.status === "SCHEDULED" && new Date(ss.ends_at) <= new Date() ? button("Complete session", "complete", ss.id) : ""}</div>${
            people.length
              ? `<div class="table-scroll"><table class="workspace-table"><tbody>${people
                  .map((p) => {
                    const att = s.attendance.find(
                      (x) => x.participant_id === p.id,
                    );
                    return `<tr><td>${esc(name(s.students, p.student_id))} ${badge(p.participation_kind)}</td><td>${badge(att?.status || "Not marked")}</td><td><div class="row-actions">${!future && ss.status !== "CANCELLED" ? button("Attendance", "attendance", p.id) : ""}${manager && p.participation_kind !== "MAKEUP" ? button("Grant makeup", "grant", p.id) : ""}</div></td></tr>`;
                  })
                  .join("")}</tbody></table></div>`
              : '<p class="subtext">No students booked yet.</p>'
          }</section>`;
        })
        .join("") +
      (s.sessions.length
        ? ""
        : '<section class="workspace-card empty">Schedule your first session to get started.</section>')
    );
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
        "No makeup credits yet. Grant one from a session roster, or cancel a session with makeup credits enabled.",
      )
    );
  return "";
}
