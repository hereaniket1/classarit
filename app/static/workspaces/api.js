export const workspaceId = document.body.dataset.workspace;
let savingCount = 0;

function saveOverlay() {
  let overlay = document.querySelector("#save-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "save-overlay";
    overlay.className = "save-overlay";
    overlay.hidden = true;
    overlay.setAttribute("role", "status");
    overlay.setAttribute("aria-live", "polite");
    overlay.innerHTML =
      '<div class="save-overlay-panel"><span class="calendar-spinner" aria-hidden="true"></span><strong>Saving changes</strong><small>Please wait while Classarit updates your data.</small></div>';
    document.body.append(overlay);
  }
  return overlay;
}

export function setSaving(active, message = "Saving changes") {
  const overlay = saveOverlay();
  savingCount = Math.max(0, savingCount + (active ? 1 : -1));
  if (active) overlay.querySelector("strong").textContent = message;
  const saving = savingCount > 0;
  overlay.hidden = !saving;
  document.body.classList.toggle("is-saving-data", saving);
  document.body.setAttribute("aria-busy", saving ? "true" : "false");
}

export async function withSaving(work, message = "Saving changes") {
  setSaving(true, message);
  try {
    return await work();
  } finally {
    setSaving(false);
  }
}

const mutatesData = (method) =>
  !["GET", "HEAD", "OPTIONS"].includes(String(method || "GET").toUpperCase());

async function send(path, method, data) {
  const response = await fetch(path, {
    method,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content,
    },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  let result;
  try {
    result = await response.json();
  } catch {
    throw new Error(
      "The server could not complete this request. Please try again.",
    );
  }
  if (!response.ok) {
    if (response.status === 401) {
      location.href = "/login";
    }
    throw new Error(
      Array.isArray(result.detail)
        ? result.detail
            .map((x) => `${x.loc.slice(1).join(".")}: ${x.msg}`)
            .join("; ")
        : result.detail || "Request failed.",
    );
  }
  return result;
}

export async function request(path, method = "GET", data) {
  return mutatesData(method)
    ? withSaving(() => send(path, method, data))
    : send(path, method, data);
}
export const api = (path, method = "GET", data) =>
  request(`/api/workspaces/${workspaceId}${path}`, method, data);
export const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
let noticeTimer;
export function clearNotice() {
  const el = document.querySelector("#notice");
  if (!el) return;
  clearTimeout(noticeTimer);
  noticeTimer = undefined;
  el.textContent = "";
  el.classList.remove("error");
  el.hidden = true;
}
export function notice(message, error = false) {
  const el = document.querySelector("#notice");
  clearTimeout(noticeTimer);
  el.textContent = message;
  el.classList.toggle("error", error);
  el.hidden = false;
  if (!error) noticeTimer = setTimeout(clearNotice, 2500);
}
