const notice = document.querySelector("#notice");
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
const loading = window.ClassaritLoading;
let dashboardData = {};
const registrationMetrics = document.querySelector("#registration-metrics");
const settingsCard = document.querySelector("#executive-settings-card");
const latencyCard = document.querySelector("#executive-latency-card");
const routesCard = document.querySelector("#executive-routes-card");
const flushForm = document.querySelector("#flush-data-form");
const dashboardRegions = [
  [registrationMetrics, "registration metrics", 2],
  [settingsCard, "product controls", 3],
  [latencyCard, "API latency", 4],
  [routesCard, "route performance", 4],
];

const labels = {
  invite_request_enabled: [
    "Invitation only",
    "",
  ],
  email_verification_enabled: [
    "Email verification",
    "When on, new password accounts must confirm the email OTP before their first login.",
  ],
  notification_emails_enabled: [
    "Operational emails",
    "Controls schedule and operational notifications. Access-request, verification and approval emails are always sent.",
  ],
};

function setDashboardLoading(active) {
  for (const [region, label, rows] of dashboardRegions) {
    if (active) loading?.begin(region, label, { rows });
    else loading?.end(region);
  }
}

function show(message, error = false) {
  notice.hidden = false;
  notice.textContent = message;
  notice.classList.toggle("error", error);
  if (!error) {
    setTimeout(() => {
      notice.hidden = true;
      notice.textContent = "";
    }, 2500);
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Request failed.");
  return payload;
}

function metric(label, value) {
  return `<div class="metric"><span class="metric-icon">•</span><div><strong>${value ?? 0}</strong><span>${label}</span></div></div>`;
}

function render(data) {
  dashboardData = data;
  const registrations = data.registrations || {};
  registrationMetrics.innerHTML = [
    metric("Students", registrations.students),
    metric("Individual", registrations.individual_workspaces),
    metric("Institutes", registrations.institute_workspaces),
    metric("Teachers", registrations.teachers),
    metric("Active users", registrations.active_users),
  ].join("");
  document.querySelector("#settings-grid").innerHTML = Object.entries(labels)
    .map(
      ([key, [title, help]]) =>
        `<label class="setting-toggle"><span><strong>${title}</strong><small>${key === 'invite_request_enabled' ? (data.settings?.[key] ? 'Invitation only is enabled. Open signup is disabled; new users need an approved request or a valid team invitation. Existing users can still log in.' : 'Invitation only is disabled. User signup is enabled with Google or email and password. Existing users can still log in.') : help}</small></span><span class="switch"><input type="checkbox" data-setting="${key}" ${data.settings?.[key] ? "checked" : ""}><span class="slider"></span></span></label>`,
    )
    .join("");
  const apiData = data.api || {};
  const totals = apiData.totals || {};
  const daily = apiData.daily || [];
  document.querySelector("#api-total").textContent =
    `${totals.calls || 0} calls · ${totals.avg_latency_ms || 0}ms avg · ${totals.errors || 0} server errors`;
  const max = Math.max(1, ...daily.map((item) => item.max_latency_ms || 0));
  document.querySelector("#latency-chart").innerHTML = daily.length
    ? daily
        .map(
          (item) =>
            `<div class="latency-bar"><span style="height:${Math.max(4, Math.round(((item.avg_latency_ms || 0) / max) * 140))}px"></span><strong>${item.avg_latency_ms || 0}ms</strong><small>${item.day}</small><small>${item.calls} calls</small></div>`,
        )
        .join("")
    : '<p class="subtext">No API samples yet.</p>';
  document.querySelector("#route-table").innerHTML =
    (apiData.routes || [])
      .map(
        (item) =>
          `<tr><td>${item.route_template}</td><td>${item.calls}</td><td>${item.avg_latency_ms || 0}ms</td><td>${item.max_latency_ms || 0}ms</td></tr>`,
      )
      .join("") || '<tr><td colspan="4">No route samples yet.</td></tr>';
}

async function load() {
  setDashboardLoading(true);
  try {
    render(await api("/api/executive/dashboard"));
  } catch (error) {
    show(error.message, true);
  } finally {
    setDashboardLoading(false);
  }
}

document.addEventListener("change", async (event) => {
  const input = event.target.closest("[data-setting]");
  if (!input) return;
  input.disabled = true;
  loading?.busy(settingsCard, "Updating product controls");
  try {
    const payload = { [input.dataset.setting]: input.checked };
    const result = await api("/api/executive/settings", {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
      },
      body: JSON.stringify(payload),
    });
    render({ ...dashboardData, settings: result.settings });
    show("Setting updated.");
  } catch (error) {
    input.checked = !input.checked;
    show(error.message, true);
  } finally {
    input.disabled = false;
    loading?.end(settingsCard);
  }
});

const resetDialog = document.querySelector('#reset-confirmation');
let resetting = false;
flushForm?.addEventListener('submit', event => {
  event.preventDefault();
  if (resetting || resetDialog.open) return;
  resetDialog.returnValue = 'no';
  resetDialog.showModal();
});
resetDialog?.addEventListener('cancel', () => { resetDialog.returnValue = 'no'; });
resetDialog?.addEventListener('close', async () => {
  if (resetDialog.returnValue !== 'yes' || resetting) return;
  resetting = true;
  const button = flushForm.querySelector('button');
  button.disabled = true;
  loading?.lockPage('Resetting application data');
  let leaving = false;
  try {
    const result = await api("/api/executive/flush-data", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
      },
      body: JSON.stringify({
        confirmation: "DELETE ALL DATA",
      }),
    });
    await load();
    show(result.failed_upload_deletions ? 'Database reset complete. Some uploaded files could not be removed; retry the reset.' : 'All application data and audit records deleted. Your executive login is preserved.', Boolean(result.failed_upload_deletions));
    if (!result.failed_upload_deletions) {
      leaving = true;
      window.setTimeout(() => {
        loading?.navigate('/executive', 'executive dashboard') || (location.href = '/executive');
      }, 800);
    }
  } catch (error) {
    show(error.message, true);
  } finally {
    if (!leaving) {
      resetting = false;
      button.disabled = false;
      loading?.unlockPage();
    }
  }
});

document.querySelector("#logout")?.addEventListener("click", async () => {
  try {
    const form = new URLSearchParams({ csrf_token: csrf });
    const response = await fetch("/auth/logout", { method: "POST", body: form });
    if (response.ok) loading?.navigate("/", "home") || (location.href = "/");
    else show("Could not log out.", true);
  } catch (error) { show(error.message, true); }
});

load();
