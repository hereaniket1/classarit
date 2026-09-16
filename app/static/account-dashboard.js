/** Shared account navigation, intentionally independent of workspace editing forms. */
export async function logout() {
  const response = await fetch("/auth/logout", {
    method: "POST",
    body: new URLSearchParams({
      csrf_token: document.querySelector('meta[name="csrf-token"]').content,
    }),
  });
  if (!response.ok) throw new Error("Could not log out. Please retry.");
  location.href = "/";
}
document.querySelector("#logout")?.addEventListener("click", async () => {
  try {
    await logout();
  } catch (error) {
    const notice = document.querySelector("#notice");
    notice.textContent = error.message;
    notice.hidden = false;
  }
});

async function setDefaultWorkspace(workspaceId) {
  const response = await fetch("/api/account/default-workspace", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content,
    },
    body: JSON.stringify({ workspace_id: workspaceId }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Could not update default workspace.");
  return payload.default_workspace_id;
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-default-workspace]");
  if (!button || button.disabled) return;
  event.preventDefault();
  const notice = document.querySelector("#notice");
  const label = button.querySelector("span");
  const original = label ? label.textContent : button.textContent;
  button.disabled = true;
  if (label) label.textContent = "Saving…";
  try {
    const selected = await setDefaultWorkspace(button.dataset.defaultWorkspace);
    document.querySelectorAll("[data-default-workspace]").forEach((item) => {
      const isDefault = item.dataset.defaultWorkspace === selected;
      item.disabled = isDefault;
      item.classList.toggle("is-default", isDefault);
      item.querySelector("span").textContent = isDefault ? "Default" : "Make default";
      item.title = isDefault ? "This opens automatically after login" : "Open this workspace by default after login";
      item.setAttribute("aria-label", `${isDefault ? "Default workspace" : "Make default workspace"}: ${item.closest(".portfolio-card")?.querySelector("h2")?.textContent || "workspace"}`);
    });
    if (notice) {
      notice.textContent = "Default workspace updated.";
      notice.hidden = false;
      setTimeout(() => { notice.hidden = true; notice.textContent = ""; }, 2500);
    }
  } catch (error) {
    button.disabled = false;
    if (label) label.textContent = original;
    if (notice) {
      notice.textContent = error.message;
      notice.hidden = false;
    }
  }
});
