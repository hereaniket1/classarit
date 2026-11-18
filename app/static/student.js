import "./account-dashboard.js";
import { esc, notice, clearNotice } from "./workspaces/api.js?v=global-loading-20260930";
import { mountStudentCalendar } from "./student-calendar.js?v=student-calendar";
import { mountStudentPlanner } from "./student-planner.js";
import { openStudentPopup } from "./student-popups.js";

const $ = (selector) => document.querySelector(selector);
const empty = (message) => `<p class="student-empty">${esc(message)}</p>`;

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
      enrollments.innerHTML = data.classes.map((item) => `<article class="workspace-card">
        <h3>${esc(item.name)}</h3><small>${esc(item.workspace_name)} · ${esc(item.status)}</small>
      </article>`).join("") || empty("You have not enrolled in any classes yet.");
    }
  } catch (error) {
    report(error);
  }
}

function initSearch(form) {
  const initial = new URLSearchParams(location.search);
  for (const name of ["q", "location", "mode"]) {
    if (initial.has(name)) form.elements[name].value = initial.get(name);
  }
  const root = $("#student-results");
  const previous = $("#student-prev");
  const next = $("#student-next");
  let offset = 0;
  let version = 0;
  let debounce;
  let hasMore = false;

  async function search() {
    clearTimeout(debounce);
    const current = ++version;
    const params = new URLSearchParams(new FormData(form));
    params.set("offset", offset);
    root.innerHTML = '<div class="student-skeleton" role="status" aria-label="Loading classes"></div>';
    previous.disabled = next.disabled = true;
    try {
      const data = await request(`/api/student/classes?${params}`);
      if (current !== version) return;
      hasMore = data.has_more;
      const rows = data.classes.map((item) => `<tr>
        <td><strong>${esc(item.name)}</strong><small>${esc(item.description)}</small></td>
        <td>${esc(item.teachers || "—")}</td>
        <td>${esc(item.default_delivery_mode)}</td>
        <td>${esc(item.location || "Online")}</td>
        <td>${esc(item.seats_available)}</td>
        <td><button class="btn btn-sm btn-primary" type="button" data-enroll="${esc(item.id)}"
          ${item.enrolled || !item.seats_available ? "disabled" : ""}>
          ${item.enrolled ? "Enrolled" : item.seats_available ? "Join class" : "Full"}
        </button></td>
      </tr>`).join("");
      root.innerHTML = rows ? `<div class="student-results-table-wrap"><table class="student-results-table">
        <thead><tr><th>Class</th><th>Teacher</th><th>Mode</th><th>Location</th><th>Seats</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table></div>` : empty("No matching classes.");
    } catch (error) {
      if (current !== version) return;
      hasMore = false;
      root.innerHTML = empty("Could not load class search.");
      report(error);
    } finally {
      if (current === version) {
        previous.disabled = offset === 0;
        next.disabled = !hasMore;
      }
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    offset = 0;
    search();
  });
  form.elements.q.addEventListener("input", () => {
    clearTimeout(debounce);
    offset = 0;
    debounce = setTimeout(search, 250);
  });
  previous.addEventListener("click", () => {
    offset = Math.max(0, offset - 20);
    search();
  });
  next.addEventListener("click", () => {
    offset += 20;
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
  search();
}

const searchForm = $("#student-search");
if (searchForm) initSearch(searchForm);
mountStudentPlanner(request, report).catch(report);
if (searchForm) loadUpcoming();

$("#quick-search-classes").addEventListener("click", () => {
  const popup = openStudentPopup("student-search-popup", "Search classes", `
    <form action="/student/classes" method="get" class="student-popup-search">
      <label>Class or organization<input class="form-control" name="q" maxlength="150" placeholder="What would you like to learn?"></label>
      <label>Location<input class="form-control" name="location" maxlength="150" placeholder="City, area or venue"></label>
      <label>Learning mode<select class="form-select" name="mode"><option value="">All modes</option><option value="ONLINE">Online</option><option value="IN_PERSON">In person</option><option value="HYBRID">Hybrid</option></select></label>
      <button class="btn btn-primary" type="submit">Search classes</button>
    </form>`);
  popup.element.querySelector('input[name="q"]').focus();
});

const dashboard = $("#student-calendar");
const calendar = $("#student-month-calendar");
if (dashboard || calendar) mountStudentCalendar(dashboard || calendar, Boolean(dashboard), request, report);
if ($("#drawing-canvas")) import("./student-draw.js").then(({ mountDraw }) => mountDraw()).catch(report);
if ($("#puzzle-page")) import("./student-games.js").then(({ mountGames }) => mountGames()).catch(report);
