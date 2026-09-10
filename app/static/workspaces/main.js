import { api, request, notice, workspaceId } from "./api.js";
import { render } from "./render.js";
import { action } from "./actions.js";
let snapshot,
  tab = "overview";
async function refresh() {
  snapshot = await api("/snapshot");
  draw();
}
function draw() {
  document.querySelector("#workspace-content").innerHTML = render(
    snapshot,
    tab,
  );
  document
    .querySelectorAll("[data-tab]")
    .forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
}
document.querySelector("#logout").onclick = async () => {
  try {
    const response = await fetch("/auth/logout", {
      method: "POST",
      body: new URLSearchParams({
        csrf_token: document.querySelector('meta[name="csrf-token"]').content,
      }),
    });
    if (!response.ok) throw new Error("Could not log out. Please retry.");
    location.href = "/";
  } catch (e) {
    notice(e.message, true);
  }
};
document
  .querySelector("#workspace-switch")
  ?.addEventListener(
    "change",
    (e) =>
      (location.href = `/dashboard?workspace=${encodeURIComponent(e.target.value)}`),
  );
document
  .querySelector("#onboarding-form")
  ?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const button = e.target.querySelector("button");
    button.disabled = true;
    try {
      const row = await request(
        "/api/workspaces",
        "POST",
        Object.fromEntries(new FormData(e.target)),
      );
      location.href = `/dashboard?workspace=${row.id}`;
    } catch (e) {
      notice(e.message, true);
    } finally {
      button.disabled = false;
    }
  });
document
  .querySelector("#accept-invitation")
  ?.addEventListener("click", async () => {
    try {
      const row = await request(
        `/api/invitations/${encodeURIComponent(document.body.dataset.invitation)}/accept`,
        "POST",
      );
      location.href = `/dashboard?workspace=${row.workspace_id}`;
    } catch (e) {
      notice(e.message, true);
    }
  });
document
  .querySelector("#dismiss-invitation")
  ?.addEventListener("click", async () => {
    try {
      await request("/api/invitations/dismiss", "POST");
      location.href = "/dashboard";
    } catch (e) {
      notice(e.message, true);
    }
  });
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-tab],[data-action]");
  if (!b) return;
  if (b.dataset.tab) {
    tab = b.dataset.tab;
    draw();
  } else action(snapshot, b.dataset.action, b.dataset.id, refresh);
});
if (workspaceId) refresh().catch((e) => notice(e.message, true));
