/** DOM-level checks without a browser/server. See README for temporary tooling setup. */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(
  process.env.CLASSARIT_JS_TOOLS
    ? path.join(process.env.CLASSARIT_JS_TOOLS, "package.json")
    : import.meta.url,
);
const { JSDOM } = require("jsdom");
const dom = new JSDOM(
  `<!doctype html><html><head><meta name="csrf-token" content="test-csrf"></head><body data-workspace="workspace"><div id="notice"></div><dialog id="editor"><form id="editor-form"><h2 id="editor-title"></h2><button type="button" id="close-editor"></button><div id="editor-fields"></div><p id="editor-error"></p><button type="button" id="cancel-editor"></button><button type="submit">Save</button></form></dialog></body></html>`,
  { url: "http://localhost:8000" },
);
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.FormData = dom.window.FormData;
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.open = true;
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.open = false;
};
const { action } = await import(
  pathToFileURL(path.join(root, "app/static/workspaces/actions.js"))
);
const { render } = await import(
  pathToFileURL(path.join(root, "app/static/workspaces/render.js"))
);
const future = new Date(Date.now() + 86400000).toISOString();
const data = {
  workspace: {
    id: "workspace",
    name: "Test",
    timezone: "Asia/Kolkata",
    workspace_type: "INDIVIDUAL",
  },
  roles: ["OWNER", "TEACHER"],
  membership_id: "member",
  members: [
    {
      id: "member",
      full_name: "Owner",
      status: "ACTIVE",
      roles: ["OWNER", "TEACHER"],
    },
  ],
  activities: [{ id: "activity", name: "Piano" }],
  venues: [{ id: "venue", name: "Hall", address: "Street" }],
  spaces: [{ id: "space", venue_id: "venue", name: "Room" }],
  programs: [
    {
      id: "program",
      name: "Piano",
      activity_id: "activity",
      program_kind: "COURSE",
      default_delivery_mode: "ONLINE",
      capacity: 10,
    },
  ],
  program_teachers: [{ program_id: "program", membership_id: "member" }],
  students: [
    {
      id: "student",
      full_name: "<img src=x onerror=alert(1)>",
      email: "student@example.com",
    },
  ],
  guardians: [],
  student_guardians: [],
  enrollments: [
    {
      id: "enrollment",
      student_id: "student",
      program_id: "program",
      status: "ACTIVE",
    },
  ],
  recurring_series: [
    {
      id: "series",
      program_id: "program",
      title: "Weekly Lesson",
      start_date: "2026-09-01",
      start_time: "09:00:00",
      repeat_weekdays: ["MON", "WED"],
      repeat_months: 3,
      status: "ACTIVE",
    },
  ],
  sessions: [
    {
      id: "session",
      program_id: "program",
      title: "Lesson",
      starts_at: future,
      ends_at: future,
      status: "SCHEDULED",
      delivery_mode: "ONLINE",
      meeting_url: "https://example.com",
      capacity: 10,
    },
    {
      id: "series-session",
      program_id: "program",
      recurring_series_id: "series",
      edited_from_series: false,
      title: "Weekly Lesson",
      starts_at: future,
      ends_at: future,
      status: "SCHEDULED",
      delivery_mode: "ONLINE",
      meeting_url: "https://example.com",
      capacity: 10,
    },
  ],
  session_teachers: [],
  participants: [
    {
      id: "participant",
      session_id: "session",
      program_id: "program",
      student_id: "student",
      status: "BOOKED",
      participation_kind: "ENROLLMENT",
    },
  ],
  attendance: [],
  invitations: [
    {
      id: "invitation",
      email: "member@example.com",
      proposed_roles: ["TEACHER"],
      status: "PENDING",
      expires_at: future,
    },
  ],
  entitlements: [],
  bookings: [],
  policy: {
    teacher_cancellation_eligible: true,
    student_absence_eligible: false,
    minimum_notice_hours: 0,
    validity_days: 30,
    included_in_original_fee: true,
  },
};
for (const tab of [
  "calendar",
  "classes",
  "students",
  "venues",
  "team",
  "sessions",
  "makeups",
  "reporting",
]) {
  const html = render(structuredClone(data), tab);
  assert.ok(html.length > 0);
  assert.ok(!html.includes("<img src=x"));
  assert.ok(!html.includes("[object Object]"));
}
const form = document.querySelector("#editor-form");
for (const [key, id] of [
  ["student", ""],
  ["edit-student", "student"],
  ["venue", ""],
  ["program", ""],
  ["teachers", "program"],
  ["enroll", "program"],
  ["session", "program"],
  ["reschedule", "session"],
  ["event", "session"],
  ["cancel", "session"],
  ["attendance", "participant"],
  ["grant", "participant"],
  ["invite", ""],
  ["member", "member"],
  ["policy", ""],
  ["revoke", "invitation"],
  ["release", "booking"],
  ["complete", "session"],
  ["end-enrollment", "enrollment"],
  ["disable-series", "series"],
]) {
  action(structuredClone(data), key, id, async () => {});
  assert.ok(document.querySelector("#editor").open, key);
  assert.ok(!form.innerHTML.includes("[object Object]"), key);
  const namedControls = [...form.elements].filter(
    (e) => e.name && !e.closest?.(".weekday-picker"),
  );
  assert.equal(
    new Set(namedControls.map((e) => e.name)).size,
    namedControls.length,
    key,
  );
  document.querySelector("#editor").close();
}
let sent;
globalThis.fetch = async (url, options) => {
  sent = { url, options };
  return { ok: true, json: async () => ({ ok: true }) };
};
action(structuredClone(data), "program", "", async () => {});
assert.equal(form.elements.default_venue_id.disabled, true);
form.elements.default_delivery_mode.value = "IN_PERSON";
form.onchange();
assert.equal(form.elements.default_venue_id.disabled, false);
assert.equal(form.elements.default_meeting_url.disabled, true);
form.elements.default_venue_id.value = "venue";
form.onchange();
assert.equal(form.elements.default_space_id.options[1].disabled, false);
form.elements.name.value = "Test class";
form.elements.activity_name.value = "Piano";
form.elements.teaching_format.value = "ONE_TO_ONE";
form.onchange();
assert.equal(form.elements.capacity.value, "1");
await form.onsubmit({ preventDefault() {} });
assert.ok(document.querySelector("#save-overlay"));
assert.ok(document.querySelector(".editor-save-loader"));
assert.equal(document.body.getAttribute("aria-busy"), "false");
assert.equal(document.querySelector("#editor").classList.contains("is-saving"), false);
assert.equal(sent.url, "/api/workspaces/workspace/programs");
assert.equal(sent.options.headers["X-CSRF-Token"], "test-csrf");
const payload = JSON.parse(sent.options.body);
assert.equal(payload.default_delivery_mode, "IN_PERSON");
assert.equal(payload.default_meeting_url, null);
assert.equal(payload.capacity, 1);
assert.deepEqual(payload.teacher_ids, ["member"]);
action(structuredClone(data), "edit-student", "student", async () => {});
assert.equal(form.elements.full_name.value, data.students[0].full_name);
await form.onsubmit({ preventDefault() {} });
assert.equal(sent.options.method, "PATCH");
action(structuredClone(data), "disable-series", "series", async () => {});
await form.onsubmit({ preventDefault() {} });
assert.equal(sent.url, "/api/workspaces/workspace/recurring-series/series/disable");
assert.equal(sent.options.method, "POST");
sent = undefined;
action(structuredClone(data), "session", "program", async () => {});
form.elements.schedule_type.value = "once";
form.elements.student_ids.options[0].selected = true;
form.onchange();
await form.onsubmit({ preventDefault() {} });
assert.equal(sent.url, "/api/workspaces/workspace/sessions");
assert.equal(sent.options.method, "POST");
const oneTimePayload = JSON.parse(sent.options.body);
assert.equal(oneTimePayload.program_id, "program");
assert.deepEqual(oneTimePayload.student_ids, ["student"]);
assert.ok(!("repeat_weekdays" in oneTimePayload));
assert.ok(!("repeat_months" in oneTimePayload));
assert.equal(document.querySelector("#editor-error").textContent, "");
globalThis.fetch = async () => ({
  ok: false,
  status: 409,
  json: async () => ({ detail: "The session is full." }),
});
action(structuredClone(data), "event", "session", async () => {});
await form.onsubmit({ preventDefault() {} });
assert.equal(
  document.querySelector("#editor-error").textContent,
  "The session is full.",
);
assert.equal(document.querySelector("#editor").open, true);
const { default: mermaid } = await import(
  pathToFileURL(require.resolve("mermaid"))
);
mermaid.initialize({ startOnLoad: false });
const blocks = [
  ...fs
    .readFileSync(path.join(root, "README.md"), "utf8")
    .matchAll(/```mermaid\n([\s\S]*?)```/g),
];
for (const block of blocks) await mermaid.parse(block[1]);
console.log(
  `Passed: seven dashboard sections, twenty dialogs including repeat scheduling, form payloads/CSRF/errors/XSS escaping, and ${blocks.length} Mermaid diagrams.`,
);
