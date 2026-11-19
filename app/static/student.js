import "./account-dashboard.js";
import { esc, notice, clearNotice } from "./workspaces/api.js?v=global-loading-20260930";
import { mountStudentCalendar } from "./student-calendar.js?v=student-calendar";
import { mountStudentPlanner } from "./student-planner.js";
import { openStudentPopup } from "./student-popups.js";

const $ = (selector) => document.querySelector(selector);
const empty = (message) => `<p class="student-empty">${esc(message)}</p>`;
const dateLabel = (value) => {
  if (!value) return "—";
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, {
    month: "short", day: "numeric", year: "numeric",
  }).format(date);
};

async function request(path, method = "GET", data) {
  const response = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": $('meta[name="csrf-token"]').content,
    },
    body: data === undefined ? undefined : JSON.stringify(data),
    signal: AbortSignal.timeout(25000),
  });
  const result = await response.json().catch(() => ({}));
  if (response.status === 401) location.assign("/login");
  if (!response.ok) {
    throw new Error(typeof result.detail === "string" ? result.detail : "Unable to complete this request.");
  }
  return result;
}

function report(error, saving = false) {
  const timeout = saving
    ? "The request timed out. Check whether your change was saved before trying again."
    : "The request timed out. Refresh and try again.";
  notice(error.name === "TimeoutError" ? timeout : error.message, true);
}

async function loadUpcoming() {
  try {
    const data = await request("/api/student/upcoming");
    const enrollments = $("#student-enrollments");
    if (enrollments) {
      const rows = data.classes.map((item) => `<tr>
        <td><strong>${esc(item.name)}</strong></td>
        <td>${esc(item.workspace_name || "—")}</td>
        <td>${esc(dateLabel(item.starts_on))}${item.ends_on ? ` – ${esc(dateLabel(item.ends_on))}` : ""}</td>
        <td><span class="registration-status">${esc(item.status || "ACTIVE")}</span></td>
      </tr>`).join("");
      enrollments.innerHTML = rows ? `<div class="student-results-table-wrap student-registration-table-wrap student-results-reveal">
        <table class="student-results-table student-registration-table">
          <thead><tr><th>Class</th><th>Organization</th><th>Registration dates</th><th>Status</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>` : empty("You are not registered for any classes yet.");
    }
  } catch (error) {
    report(error);
  }
}

function initSearch(form) {
  const initial = new URLSearchParams(location.search);
  if (initial.has("q")) form.elements.q.value = initial.get("q");
  const root = $("#student-results");
  let offset = 0;
  let version = 0;

  async function search() {
    const current = ++version;
    const params = new URLSearchParams(new FormData(form));
    params.set("offset", offset);
    if (!params.get("q")?.trim()) {
      root.replaceChildren();
      return;
    }
    root.innerHTML = '<div class="student-skeleton" role="status" aria-label="Loading classes"></div>';
    try {
      const data = await request(`/api/student/classes?${params}`);
      if (current !== version) return;
      const rows = data.classes.map((item) => `<tr>
        <td><strong>${esc(item.name)}</strong><small>${esc([item.activity_name, item.level, item.description].filter(Boolean).join(" · ") || "Class")}</small></td>
        <td><strong>${esc(item.workspace_name || "—")}</strong><small>${esc(item.teachers || "Teacher not listed")}</small></td>
        <td><span class="class-mode">${esc(item.default_delivery_mode)}</span><small>${esc(item.location || "Online")}</small></td>
        <td>${esc(item.seats_available)}<small>seats</small></td>
        <td><button class="btn btn-sm btn-primary" type="button" data-enroll="${esc(item.id)}"
          ${item.enrolled || !item.seats_available ? "disabled" : ""}>
          ${item.enrolled ? "Enrolled" : item.seats_available ? "Join class" : "Full"}
        </button></td>
      </tr>`).join("");
      root.innerHTML = rows ? `<div class="student-results-table-wrap student-results-reveal"><table class="student-results-table">
        <thead><tr><th>Class</th><th>Organization / teacher</th><th>Format / location</th><th>Seats</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>` : "";
    } catch (error) {
      if (current !== version) return;
      root.innerHTML = empty("Could not load class search.");
      report(error);
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    offset = 0;
    search();
  });
  root.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-enroll]");
    if (!button || button.disabled) return;
    clearNotice();
    button.disabled = true;
    button.textContent = "Joining…";
    try {
      await request(`/api/student/classes/${encodeURIComponent(button.dataset.enroll)}/enroll`, "POST");
      button.textContent = "Enrolled";
      notice("You are enrolled.");
      loadUpcoming();
    } catch (error) {
      button.disabled = false;
      button.textContent = "Join class";
      report(error, true);
    }
  });
  if (form.elements.q.value.trim()) search();
  else root.replaceChildren();
}

const searchForm = $("#student-search");
if (searchForm) initSearch(searchForm);
mountStudentPlanner(request, report).catch(report);
if (searchForm) loadUpcoming();

$("#quick-search-classes").addEventListener("click", () => {
  const popup = openStudentPopup("student-search-popup", "Search classes", `
    <form action="/student/classes" method="get" class="student-popup-search">
      <label>Search classes<input class="form-control" name="q" maxlength="150" placeholder="Class, teacher, subject, organization, location…"></label>
      <button class="btn btn-primary" type="submit">Search</button>
    </form>`);
  popup.element.querySelector('input[name="q"]').focus();
});

const dashboard = $("#student-calendar");
const calendar = $("#student-month-calendar");
if (dashboard || calendar) mountStudentCalendar(dashboard || calendar, Boolean(dashboard), request, report);
if ($("#drawing-canvas")) import("./student-draw.js").then(({ mountDraw }) => mountDraw()).catch(report);
if ($("#puzzle-page")) import("./student-games.js").then(({ mountGames }) => mountGames()).catch(report);
if ($("#entertainment-page")) import("./student-entertainment.js").then(({ mountEntertainment }) => mountEntertainment()).catch(report);
