import { api, notice } from "./api.js?v=global-loading-20260930";
import { edit, field as f } from "./forms.js?v=global-loading-20260930";
export function action(s, key, id, refresh, context = {}) {
  const opts = (values) =>
    values.map((v) => ({ id: v, name: v.replaceAll("_", " ") }));
  const timezoneOptions = [
    ["Asia/Kolkata", "India - Asia/Kolkata"],
    ["Asia/Dubai", "UAE - Asia/Dubai"],
    ["Asia/Singapore", "Singapore - Asia/Singapore"],
    ["Europe/London", "UK - Europe/London"],
    ["America/New_York", "US Eastern - America/New_York"],
    ["America/Chicago", "US Central - America/Chicago"],
    ["America/Los_Angeles", "US Pacific - America/Los_Angeles"],
    ["Australia/Sydney", "Australia - Australia/Sydney"],
  ].map(([id, name]) => ({ id, name }));
  const currencyOptions = [
    ["INR", "INR - Indian rupee"],
    ["USD", "USD - US dollar"],
    ["CAD", "CAD - Canadian dollar"],
    ["GBP", "GBP - British pound"],
    ["AUD", "AUD - Australian dollar"],
    ["AED", "AED - UAE dirham"],
    ["SGD", "SGD - Singapore dollar"],
  ].map(([id, name]) => ({ id, name }));
  const individual = s.workspace?.workspace_type === "INDIVIDUAL";
  if (individual && ["invite", "teachers", "member"].includes(key)) return;
  const staffRoleValues =
    s.workspace?.workspace_type === "INDIVIDUAL"
      ? ["TEACHER"]
      : ["ADMIN", "OPERATOR", "TEACHER"];
  const select = (n, l, options, value = "", required = true) =>
    f(n, l, "select", { options, value, required });
  const teachers = s.members
    .filter((m) => m.status === "ACTIVE" && m.roles.includes("TEACHER"))
    .map((m) => ({ id: m.id, name: m.full_name }));
  const students = s.students
    .filter((student) => student.status !== "ARCHIVED")
    .map((student) => ({ id: student.id, name: student.full_name }));
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
  const programFields = (program = {}) => {
    const activity = s.activities.find(
      (item) => item.id === program.activity_id,
    );
    const assignedTeachers = program.id
      ? s.program_teachers
          .filter((row) => row.program_id === program.id)
          .map((row) => row.membership_id)
      : [s.membership_id];
    return [
      f("name", "Name", "text", {
        value: program.name,
        required: true,
      }),
      f("activity_name", "Activity (e.g. piano, maths, soccer)", "text", {
        value: activity?.name,
        required: true,
      }),
      select(
        "category",
        "Category",
        opts(["ACADEMIC", "ARTS", "SPORTS", "OTHER"]),
        activity?.category || "ARTS",
      ),
      select(
        "program_kind",
        "Type",
        opts(["COURSE", "EVENT"]),
        program.program_kind || "COURSE",
      ),
      select(
        "teaching_format",
        "Format",
        opts(["GROUP", "ONE_TO_ONE"]),
        program.teaching_format || "GROUP",
      ),
      f("level", "Level (optional)", "text", { value: program.level }),
      f("description", "Description (optional)", "textarea", {
        value: program.description,
      }),
      f("capacity", "Seats", "number", {
        value: program.capacity || 10,
        min: 1,
        required: true,
      }),
      f("default_duration_minutes", "Duration in minutes", "number", {
        value: program.default_duration_minutes || 60,
        min: 1,
        max: 1440,
        required: true,
      }),
      ...(individual ? [] : [f("teacher_ids", "Teachers", "multiple", {
        options: teachers,
        value: assignedTeachers,
        required: true,
      })]),
      ...deliveryFields("default_", {
        default_delivery_mode: program.default_delivery_mode || "ONLINE",
        default_meeting_url: program.default_meeting_url,
        default_venue_id: program.default_venue_id,
        default_space_id: program.default_space_id,
      }),
    ];
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
  const defaultSessionStart = () => {
    if (!context.dateKey) return "";
    return context.dateKey === today
      ? local(new Date(Date.now() + 60 * 60 * 1000))
      : `${context.dateKey}T09:00`;
  };
  const weekdayOptions = [
    ["MON", "Mon"],
    ["TUE", "Tue"],
    ["WED", "Wed"],
    ["THU", "Thu"],
    ["FRI", "Fri"],
    ["SAT", "Sat"],
    ["SUN", "Sun"],
  ].map(([id, name]) => ({ id, name }));
  const weekdayForDate = (dateKey) =>
    ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"][
      new Date(`${dateKey}T12:00:00`).getDay()
    ];
  const selectedProgram = (programId) =>
    s.programs.find((p) => p.id === programId) || s.programs[0] || {};
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
        f("date_of_birth", "Date of birth", "date"),
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
  if (key === "program" || key === "edit-program") {
    const program = s.programs.find((row) => row.id === id) || {};
    edit(
      id ? "Edit class or event" : "Create class or event",
      [
        ...programFields(program),
        ...(id
          ? [
              f(
                "update_note",
                "These changes become the defaults for future schedules. Existing session dates, teachers and locations keep their saved history.",
                "note",
              ),
            ]
          : []),
      ],
      save(id ? `/programs/${id}` : "/programs", id ? "PATCH" : "POST"),
    );
  }
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
  if (key === "session") {
    const program = selectedProgram(id);
    const startDate =
      context.dateKey || local(new Date(Date.now() + 24 * 60 * 60 * 1000)).slice(0, 10);
    const startTime =
      context.dateKey === today
        ? local(new Date(Date.now() + 60 * 60 * 1000)).slice(11, 16)
        : "09:00";
    const weekly = { field: "schedule_type", values: ["weekly"] };
    const once = { field: "schedule_type", values: ["once"] };
    edit(
      "Schedule classes",
      [
        select(
          "schedule_type",
          "Schedule",
          [
            { id: "once", name: "One class" },
            { id: "weekly", name: "Repeat weekly" },
          ],
          "once",
        ),
        select(
          "program_id",
          "Class or event",
          s.programs,
          id || s.programs[0]?.id,
        ),
        students.length
          ? f("student_ids", "Students for this schedule (optional)", "multiple", {
              options: students,
              value: [],
              help: "Enrolled students are added automatically. Pick extra students here for this one class or every generated repeat.",
            })
          : f(
              "student_note",
              "No students yet. You can save the schedule now and add students later from the Students tab.",
              "note",
            ),
        f("capacity", "Seats for this schedule", "number", {
          value: program.capacity || 1,
          min: 1,
          max: 10000,
          help: "Must cover enrolled students plus any selected students. For example, choose 2 seats when two students should attend.",
        }),
        f("title", "Session title (optional)"),
        f("starts_at", `Start (${s.workspace.timezone})`, "datetime-local", {
          value: defaultSessionStart(),
          required: true,
          visibleWhen: once,
        }),
        f("ends_at", "End (optional; uses class duration)", "datetime-local", {
          visibleWhen: once,
        }),
        f("start_date", "First week starts", "date", {
          value: startDate,
          required: true,
          visibleWhen: weekly,
          help: "The selected weekdays are generated from this date forward.",
        }),
        f("start_time", `Start time (${s.workspace.timezone})`, "time", {
          value: startTime,
          required: true,
          visibleWhen: weekly,
        }),
        f("duration_minutes", "Duration in minutes", "number", {
          value: program.default_duration_minutes || 60,
          min: 1,
          max: 1440,
          visibleWhen: weekly,
          help: "Leave the class default if this repeat follows the usual duration.",
        }),
        f("repeat_weekdays", "Repeat on", "weekday-multiple", {
          options: weekdayOptions,
          value: [weekdayForDate(startDate)],
          required: true,
          visibleWhen: weekly,
          help: "Pick one or more days. Example: Mon + Thu for twice a week.",
        }),
        select(
          "repeat_months",
          "Repeat for",
          [
            { id: "1", name: "1 month" },
            { id: "2", name: "2 months" },
            { id: "3", name: "3 months" },
            { id: "6", name: "6 months" },
            { id: "12", name: "12 months" },
          ],
          "3",
        ),
      ].map((field) =>
        field.name === "repeat_months" ? { ...field, visibleWhen: weekly } : field,
      ),
      async (data) => {
        if (data.schedule_type === "weekly") {
          const result = await api("/sessions/recurring", "POST", {
            program_id: data.program_id,
            title: data.title,
            student_ids: data.student_ids || [],
            start_date: data.start_date,
            start_time: data.start_time,
            duration_minutes: data.duration_minutes,
            capacity: data.capacity,
            repeat_weekdays: data.repeat_weekdays,
            repeat_months: Number(data.repeat_months),
          });
          await refresh();
          notice(`Scheduled ${result.count} classes.`);
          return;
        }
        await api("/sessions", "POST", {
          program_id: data.program_id,
          title: data.title,
          student_ids: data.student_ids || [],
          starts_at: data.starts_at,
          ends_at: data.ends_at,
          capacity: data.capacity,
        });
        await refresh();
        notice("Saved successfully.");
      },
    );
  }
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
        select("role", "Role", opts(staffRoleValues), "TEACHER"),
        f("role_note", s.workspace?.workspace_type === "INDIVIDUAL"
          ? "Individual practices can invite Teachers only."
          : "Admin, Operator and Teacher are separate roles. A person can hold one of them in this workspace.", "note"),
      ],
      async (d) => {
        const result = await api("/invitations", "POST", {
          email: d.email,
          roles: [d.role],
        });
        await refresh();
        notice(
          `Share this private invitation link with ${result.email}: ${result.url} (expires in 72 hours).`,
        );
      },
    );
  if (key === "member") {
    const m = s.members.find((m) => m.id === id);
    const operationalRoles = m.roles.filter(
      (role) => role !== "OWNER" && staffRoleValues.includes(role),
    );
    const isOwner = m.roles.includes("OWNER");
    edit(
      `Manage ${m.full_name}`,
      isOwner
        ? [
            f("teacher_role", "Owner also teaches", "checkbox", {
              value: operationalRoles.includes("TEACHER"),
            }),
            f("owner_note", "Owner access is permanent. An individual practice owner must also remain a Teacher.", "note"),
          ]
        : [
            select("role", "Role", opts(staffRoleValues), operationalRoles[0]),
            select("status", "Membership", opts(["ACTIVE", "SUSPENDED", "LEFT"]), m.status),
          ],
      save(`/members/${id}`, "PATCH", (d) => ({
        roles: isOwner ? (d.teacher_role ? ["TEACHER"] : []) : [d.role],
        status: isOwner ? "ACTIVE" : d.status,
      })),
    );
  }

  if (key === "edit-workspace")
    edit(
      "Edit workspace",
      [
        f("name", "Workspace name", "text", { value: s.workspace.name, required: true }),
        select("timezone", "Timezone", timezoneOptions, s.workspace.timezone),
        select("currency", "Currency", currencyOptions, s.workspace.currency),
      ],
      async (data) => {
        await api("", "PATCH", { ...data, currency: data.currency.toUpperCase() });
        window.ClassaritLoading?.reload("workspace") || location.reload();
      },
    );

  if (key === "delete-workspace")
    edit(
      "Permanently delete workspace",
      [
        f("warning", "This permanently deletes every class, schedule, venue, student, membership and attendance record in this workspace. This cannot be undone.", "note"),
        f("confirmation", `Type ${s.workspace.name} to confirm`, "text", { required: true }),
      ],
      async (data) => {
        await api("", "DELETE", data);
        window.ClassaritLoading?.navigate("/dashboard?overview=1", "dashboard") || (location.href = "/dashboard?overview=1");
      },
      { submitLabel: "Delete workspace", progressLabel: "Deleting…", danger: true },
    );

  const deleteActions = {
    "delete-program": {
      title: "Delete class or event",
      message: "The class will be archived. Active enrollments and future schedules under it will be cancelled.",
      path: `/programs/${id}`,
    },
    "delete-session": {
      title: "Delete schedule",
      message: "This schedule will be cancelled and kept in history.",
      path: `/sessions/${id}`,
    },
    "delete-venue": {
      title: "Delete venue",
      message: "The venue will be archived. Move active classes and upcoming schedules first.",
      path: `/venues/${id}`,
    },
    "delete-student": {
      title: "Delete student",
      message: "The student will be archived and removed from future schedules and active enrollments.",
      path: `/students/${id}`,
    },
    "delete-member": {
      title: "Remove team member",
      message: "Their workspace access will end. Reassign their active classes and upcoming schedules first.",
      path: `/members/${id}`,
    },
  };
  if (deleteActions[key]) {
    const item = deleteActions[key];
    edit(
      item.title,
      [f("warning", item.message, "note")],
      save(item.path, "DELETE"),
      { submitLabel: "Delete", progressLabel: "Deleting…", danger: true },
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
  if (key === "edit-series") {
    const series = s.recurring_series.find((r) => r.id === id);
    if (!series) return notice("Recurring schedule was not found.", true);
    const related = s.sessions
      .filter((ss) => ss.recurring_series_id === id)
      .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
    const futureCount = related.filter(
      (ss) => ss.status === "SCHEDULED" && new Date(ss.starts_at) > new Date(),
    ).length;
    const programName =
      s.programs.find((p) => p.id === series.program_id)?.name || "Class";
    const scheduleLine = `${(series.repeat_weekdays || []).join(" + ") || "Weekly"} · ${series.repeat_months || 0} month(s) · ${futureCount} session(s) left`;
    edit(
      "Edit recurring schedule",
      [
        f("class_name", `Class: ${programName}`, "note"),
        f("schedule", `Recurring: ${scheduleLine}`, "note"),
        f("title", "Schedule title", "text", {
          value: series.title || programName,
          required: true,
        }),
        f(
          "help",
          "This updates the recurring series title and future standard sessions. To change one date, use the calendar. Pattern editing will be added separately.",
          "note",
        ),
      ],
      save(`/recurring-series/${id}`, "PATCH"),
    );
  }
  if (["revoke", "release", "complete", "disable-series", "restore-series"].includes(key)) {
    const path =
      key === "revoke"
        ? `/invitations/${id}`
        : key === "release"
          ? `/makeup-bookings/${id}`
          : key === "disable-series"
            ? `/recurring-series/${id}/disable`
            : key === "restore-series"
              ? `/recurring-series/${id}/restore`
              : `/sessions/${id}/complete`;
    edit(
      key === "revoke"
        ? "Revoke invitation"
        : key === "release"
          ? "Release replacement booking"
          : key === "disable-series"
            ? "Disable recurring schedule"
            : key === "restore-series"
              ? "Restore recurring schedule"
              : "Complete session",
      key === "disable-series"
        ? [
            f("confirm", "Future standard occurrences will be cancelled. Custom edited dates stay on the calendar.", "note"),
          ]
        : key === "restore-series"
          ? [
              f("confirm", "Future standard occurrences cancelled by this recurring schedule will become scheduled again.", "note"),
            ]
          : [],
      save(path, key === "complete" || key === "disable-series" || key === "restore-series" ? "POST" : "DELETE"),
    );
  }
}
