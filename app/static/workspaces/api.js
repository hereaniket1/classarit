export const workspaceId = document.body.dataset.workspace;
export async function request(path, method = "GET", data) {
  const response = await fetch(path, {
    method,
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
export function notice(message, error = false) {
  const el = document.querySelector("#notice");
  el.textContent = message;
  el.classList.toggle("error", error);
  el.hidden = false;
}
