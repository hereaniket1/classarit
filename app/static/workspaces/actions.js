import { api, notice } from "./api.js";
import { edit, field as f } from "./forms.js";
export function action(s, key, id, refresh) {
  const opts = (values) =>
    values.map((v) => ({ id: v, name: v.replaceAll("_", " ") }));
  const select = (n, l, options, value = "", required = true) =>
    f(n, l, "select", { options, value, required });
  const teachers = s.members
    .filter((m) => m.status === "ACTIVE" && m.roles.includes("TEACHER"))
    .map((m) => ({ id: m.id, name: m.full_name }));
  const locationFields = (prefix = "", values = {}) => [
    select(
      prefix + "delivery_mode",
      "Delivery",
      opts(["ONLINE", "IN_PERSON", "HYBRID"]),
      values[prefix + "delivery_mode"] || "ONLINE",
    ),
    f(prefix + "meeting_url", "Meeting URL (online or hybrid)", "url", {
      value: values[prefix + "meeting_url"],
      visibleWhen: {
        field: prefix + "delivery_mode",
        values: ["ONLINE", "HYBRID"],
      },
    }),
    select(
      prefix + "venue_id",
      "Venue (in person or hybrid)",
      [{ id: "", name: "Choose venue" }, ...s.venues],
      values[prefix + "venue_id"],
      false,
    ),
    select(
      prefix + "space_id",
      "Space (optional)",
      [
        { id: "", name: "Whole venue" },
        ...s.spaces.map((r) => ({
          ...r,
          name: `${s.venues.find((v) => v.id === r.venue_id)?.name} / ${r.name}`,
        })),
      ],
      values[prefix + "space_id"],
      false,
    ),
  ];
  // Delivery-dependent controls are declared here; the form renderer handles visibility.
  const deliveryFields = (...args) => {
    const fields = locationFields(...args),
      prefix = args[0] || "";
    for (const field of fields) {
      if (field.name.endsWith("venue_id") || field.name.endsWith("space_id")) {
        field.visibleWhen = {
          field: prefix + "delivery_mode",
          values: ["IN_PERSON", "HYBRID"],
        };
      }
      if (field.name.endsWith("space_id"))
        field.venueField = prefix + "venue_id";
    }
    return fields;
  };
  const save =
    (path, method = "POST", transform = (x) => x) =>
    async (data) => {
      await api(path, method, transform(data));
      await refresh();
      notice("Saved successfully.");
    };
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: s.workspace.timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const local = (t) => {
    const parts = new Intl.DateTimeFormat("sv-SE", {
      timeZone: s.workspace.timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).format(new Date(t));
    return parts.replace(" ", "T");
  };
  if (key === "student" || key === "edit-student") {
    const st = s.students.find((x) => x.id === id) || {};
    const g =
      s.guardians.find((g) =>
        s.student_guardians.some(
          (l) => l.student_id === id && l.guardian_id === g.id,
        ),
      ) || {};
    edit(
      id ? "Edit student" : "Add student",
      [
        f("full_name", "Full name", "text", { required: true }),
        f("email", "Email", "email"),
        f("phone", "Phone", "tel"),
        f("notes", "Notes"),
        f("guardian_name", "Guardian name (optional)"),
        f("guardian_email", "Guardian email", "email"),
        f("guardian_phone", "Guardian phone", "tel"),
      ].map((field) => ({
        ...field,
        value: field.name.startsWith("guardian_")
          ? g[
              field.name.replace("guardian_", "") === "name"
                ? "full_name"
                : field.name.replace("guardian_", "")
            ]
          : st[field.name],
      })),
      save(id ? `/students/${id}` : "/students", id ? "PATCH" : "POST"),
    );
  }
  if (key === "venue")
    edit(
      "Add venue",
      [
        f("name", "Venue name", "text", { required: true }),
        f("address", "Address", "text", { required: true }),
        f("directions", "Directions"),
        f("map_url", "Map URL", "url"),
        f("space_names", "Rooms, pitches or courts (comma separated)"),
      ],
      save("/venues", "POST", (d) => ({
        ...d,
        directions: d.directions || "",
        space_names: (d.space_names || "")
          .split(",")
          .map((n) => n.trim())
          .filter(Boolean),
      })),
    );
  if (key === "program")
    edit(
      "Create class or event",
      [
        f("name", "Name", "text", { required: true }),
        f("activity_name", "Activity (e.g. piano, maths, soccer)", "text", {
          required: true,
        }),
        select(
          "category",
          "Category",
          opts(["ACADEMIC", "ARTS", "SPORTS", "OTHER"]),
          "ARTS",
        ),
        select("program_kind", "Type", opts(["COURSE", "EVENT"]), "COURSE"),
        select(
          "teaching_format",
          "Format",
          opts(["GROUP", "ONE_TO_ONE"]),
          "GROUP",
        ),
        f("level", "Level (optional)"),
        f("capacity", "Seats", "number", { value: 10, min: 1, required: true }),
        f("default_duration_minutes", "Duration in minutes", "number", {
          value: 60,
          min: 1,
          max: 1440,
          required: true,
        }),
        f("teacher_ids", "Teachers", "multiple", {
          options: teachers,
          value: [s.membership_id],
          required: true,
        }),
        ...deliveryFields("default_"),
      ],
      save("/programs"),
    );
  if (key === "teachers")
    edit(
      "Default teachers for future sessions",
      [
        f(
          "teacher_ids",
          "Teachers (existing sessions remain unchanged)",
          "multiple",
          {
            options: teachers,
            value: s.program_teachers
              .filter((t) => t.program_id === id)
              .map((t) => t.membership_id),
            required: true,
          },
        ),
      ],
      save(`/programs/${id}/teachers`, "PUT"),
    );
  if (key === "end-enrollment")
    edit(
      "End enrollment and release future regular seats",
      [],
      save(`/enrollments/${id}/end`),
    );
  if (key === "enroll")
    edit(
      "Enroll student",
      [
        select(
          "student_id",
          "Student",
          s.students.map((x) => ({ id: x.id, name: x.full_name })),
        ),
        f("starts_on", "Start date", "date", { value: today, required: true }),
        f("ends_on", "End date (optional)", "date"),
      ],
      save(`/programs/${id}/enrollments`),
    );
  if (key === "session")
    edit(
      "Schedule session",
      [
        select(
          "program_id",
          "Class or event",
          s.programs,
          id || s.programs[0]?.id,
        ),
        f("title", "Session title (optional)"),
        f("starts_at", `Start (${s.workspace.timezone})`, "datetime-local", {
          required: true,
        }),
        f("ends_at", "End (optional; uses class duration)", "datetime-local"),
      ],
      save("/sessions"),
    );
  if (key === "reschedule") {
    const ss = s.sessions.find((x) => x.id === id);
    edit(
      "Reschedule session",
      [
        f("starts_at", `Start (${s.workspace.timezone})`, "datetime-local", {
          value: local(ss.starts_at),
          required: true,
        }),
        f("ends_at", "End", "datetime-local", {
          value: local(ss.ends_at),
          required: true,
        }),
        ...deliveryFields("", ss),
      ],
      save(`/sessions/${id}`, "PATCH"),
    );
  }
  if (key === "event")
    edit(
      "Book student into event",
      [
        select(
          "student_id",
          "Student",
          s.students.map((x) => ({ id: x.id, name: x.full_name })),
        ),
      ],
      save(`/sessions/${id}/participants`),
    );
  if (key === "cancel")
    edit(
      "Cancel session",
      [
        f("reason", "Cancellation reason", "text", { required: true }),
        f(
          "grant_makeups",
          "Grant makeup credits to the original students",
          "checkbox",
          { value: s.policy.teacher_cancellation_eligible },
        ),
      ],
      save(`/sessions/${id}/cancel`),
    );
  if (key === "attendance") {
    const att = s.attendance.find((x) => x.participant_id === id);
    edit(
      "Mark attendance",
      [
        select(
          "status",
          "Attendance",
          opts(["PRESENT", "LATE", "ABSENT", "EXCUSED"]),
          att?.status || "PRESENT",
        ),
        f("notes", "Notes", "text", { value: att?.notes }),
      ],
      save(`/participants/${id}/attendance`, "PUT"),
    );
  }
  if (key === "grant")
    edit(
      "Grant makeup credit",
      [
        select(
          "reason",
          "Reason",
          opts([
            "TEACHER_CANCELLED",
            "VENUE_UNAVAILABLE",
            "WEATHER",
            "STUDENT_ABSENT",
            "OTHER",
          ]),
          "STUDENT_ABSENT",
        ),
        f("reason_notes", "Explanation (required for policy exceptions)"),
      ],
      save("/makeup-entitlements", "POST", (d) => ({
        ...d,
        participant_ids: [id],
      })),
    );
  if (key === "makeup") {
    const credit = s.entitlements.find((e) => e.id === id),
      original = s.participants.find(
        (p) => p.id === credit.original_participant_id,
      ),
      source = s.programs.find((p) => p.id === original?.program_id);
    const sessions = s.sessions
      .filter((ss) => {
        const p = s.programs.find((p) => p.id === ss.program_id);
        return (
          ss.status === "SCHEDULED" &&
          ss.id !== original?.session_id &&
          new Date(ss.starts_at) > new Date() &&
          p?.activity_id === source?.activity_id &&
          (p?.level || "") === (source?.level || "")
        );
      })
      .map((ss) => ({
        id: ss.id,
        name: `${ss.title} · ${local(ss.starts_at)}`,
      }));
    if (!sessions.length) {
      notice(
        "Schedule a replacement session with the same activity and level first.",
        true,
      );
      return;
    }
    edit(
      "Book replacement session",
      [select("session_id", "Replacement session", sessions)],
      save(`/makeup-entitlements/${id}/book`),
    );
  }
  if (key === "invite")
    edit(
      "Invite team member",
      [
        f("email", "Their Google email", "email", { required: true }),
        f("roles", "Roles", "multiple", {
          options: opts(["ADMIN", "OPERATOR", "TEACHER"]),
          value: ["TEACHER"],
          required: true,
        }),
      ],
      async (d) => {
        const result = await api("/invitations", "POST", d);
        await refresh();
        notice(
          `Share this private invitation link with ${result.email}: ${result.url} (expires in 7 days).`,
        );
      },
    );
  if (key === "member") {
    const m = s.members.find((m) => m.id === id);
    edit(
      `Manage ${m.full_name}`,
      [
        f("roles", "Roles", "multiple", {
          options: opts(["OWNER", "ADMIN", "OPERATOR", "TEACHER"]),
          value: m.roles,
          required: true,
        }),
        select(
          "status",
          "Membership",
          opts(["ACTIVE", "SUSPENDED", "LEFT"]),
          m.status,
        ),
      ],
      save(`/members/${id}`, "PATCH"),
    );
  }
  if (key === "policy")
    edit(
      "Makeup policy",
      [
        f(
          "teacher_cancellation_eligible",
          "Allow cancellation credits",
          "checkbox",
          { value: s.policy.teacher_cancellation_eligible },
        ),
        f(
          "student_absence_eligible",
          "Allow student absence credits",
          "checkbox",
          { value: s.policy.student_absence_eligible },
        ),
        f(
          "minimum_notice_hours",
          "Required notice hours (staff review when nonzero)",
          "number",
          { value: s.policy.minimum_notice_hours, min: 0, required: true },
        ),
        f(
          "validity_days",
          "Credit validity in days (blank for no expiry)",
          "number",
          { value: s.policy.validity_days, min: 1 },
        ),
        f(
          "included_in_original_fee",
          "Included in original fee (record only)",
          "checkbox",
          { value: s.policy.included_in_original_fee },
        ),
      ],
      save("/makeup-policy", "PUT"),
    );
  if (["revoke", "release", "complete"].includes(key)) {
    const path =
      key === "revoke"
        ? `/invitations/${id}`
        : key === "release"
          ? `/makeup-bookings/${id}`
          : `/sessions/${id}/complete`;
    edit(
      key === "revoke"
        ? "Revoke invitation"
        : key === "release"
          ? "Release replacement booking"
          : "Complete session",
      [],
      save(path, key === "complete" ? "POST" : "DELETE"),
    );
  }
}
