import { esc } from "./workspaces/api.js?v=global-loading-20260930";

export function openStudentPopup(id, title, content) {
  const previous = document.activeElement;
  const overlay = document.createElement("div");
  overlay.className = "student-popup";
  overlay.id = id;
  overlay.innerHTML = `<section class="student-popup-panel" role="dialog" aria-modal="true" aria-labelledby="${id}-title">
    <div class="editor-heading"><h2 id="${id}-title">${esc(title)}</h2>
      <button type="button" class="student-popup-close" aria-label="Close">×</button></div>
    <div class="student-popup-content">${content}</div>
  </section>`;
  document.body.append(overlay);
  document.body.classList.add("student-popup-open");
  const events = new AbortController();
  function close(restoreFocus = true) {
    events.abort();
    overlay.remove();
    document.body.classList.remove("student-popup-open");
    if (restoreFocus) previous?.focus();
  }
  overlay.querySelector(".student-popup-close").addEventListener("click", () => close());
  overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { event.preventDefault(); close(); }
    if (event.key !== "Tab") return;
    const controls = [...overlay.querySelectorAll('a[href],button,input,select,textarea,[tabindex="0"]')].filter(el => !el.disabled && el.getClientRects().length);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }, { signal: events.signal });
  overlay.querySelector("input,button")?.focus();
  return { element: overlay, close };
}
