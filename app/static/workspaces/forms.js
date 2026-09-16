import { esc, withSaving } from "./api.js?v=workspace-reporting-20260915";
const dialog = document.querySelector("#editor"),
  form = document.querySelector("#editor-form");
function editorLoader() {
  let loader = dialog.querySelector(".editor-save-loader");
  if (!loader) {
    loader = document.createElement("div");
    loader.className = "editor-save-loader";
    loader.setAttribute("role", "status");
    loader.setAttribute("aria-live", "polite");
    loader.innerHTML =
      '<span class="calendar-spinner" aria-hidden="true"></span><strong>Saving changes</strong><small>Please wait while Classarit updates your data.</small>';
    dialog.append(loader);
  }
  return loader;
}
export const field = (name, label, type = "text", options = {}) => ({
  name,
  label,
  type,
  ...options,
});
export function edit(title, fields, save) {
  const isControlList = (control) =>
    control && typeof control.length === "number" && !control.tagName;
  const controlsFor = (name) => {
    const control = form.elements.namedItem(name);
    if (!control) return [];
    if (isControlList(control)) return Array.from(control);
    return [control];
  };
  const fieldWrapper = (name) => form.querySelector(`[data-field="${name}"]`);
  const fieldValue = (name) => {
    const control = form.elements.namedItem(name);
    return isControlList(control) ? control.value : control?.value;
  };
  editorLoader();
  document.querySelector("#editor-title").textContent = title;
  dialog.classList.remove("is-saving");
  document.querySelector("#editor-error").textContent = "";
  document.querySelector("#editor-fields").innerHTML = fields
    .map((f) => {
      const attrs = `name="${esc(f.name)}" ${f.required && !["weekday-multiple"].includes(f.type) ? "required" : ""}`;
      if (f.type === "note")
        return `<p data-field="${esc(f.name)}" class="form-note">${esc(f.label)}</p>`;
      if (f.type === "checkbox")
        return `<label data-field="${esc(f.name)}" class="checkbox-label"><input type="checkbox" ${attrs} ${f.value ? "checked" : ""}>${esc(f.label)}</label>`;
      if (f.type === "weekday-multiple")
        return `<fieldset data-field="${esc(f.name)}" class="weekday-picker"><legend>${esc(f.label)}</legend><div>${(f.options || []).map((o) => `<label><input type="checkbox" name="${esc(f.name)}" value="${esc(o.id)}" ${(f.value || []).includes(o.id) ? "checked" : ""}><span>${esc(o.name)}</span></label>`).join("")}</div>${f.help ? `<small class="subtext">${esc(f.help)}</small>` : ""}</fieldset>`;
      let input;
      if (f.type === "select" || f.type === "multiple")
        input = `<select class="form-select" ${attrs} ${f.type === "multiple" ? "multiple" : ""}>${(f.options || []).map((o) => `<option value="${esc(o.id)}" ${o.venue_id ? `data-venue="${esc(o.venue_id)}"` : ""} ${(Array.isArray(f.value) ? f.value.includes(o.id) : String(f.value ?? "") === String(o.id)) ? "selected" : ""}>${esc(o.name)}</option>`).join("")}</select>`;
      else
        input = `<input class="form-control" type="${f.type}" ${attrs} value="${esc(f.value ?? "")}" ${f.min !== undefined ? `min="${f.min}"` : ""} ${f.max !== undefined ? `max="${f.max}"` : ""}>`;
      return `<label data-field="${esc(f.name)}">${esc(f.label)}${input}${f.help ? `<small class="subtext">${esc(f.help)}</small>` : ""}</label>`;
    })
    .join("");
  function updateDependencies() {
    for (const field of fields) {
      const controls = controlsFor(field.name);
      const control = controls[0];
      if (field.visibleWhen) {
        const visible = field.visibleWhen.values.includes(
          fieldValue(field.visibleWhen.field),
        );
        const wrapper = fieldWrapper(field.name);
        if (wrapper) wrapper.hidden = !visible;
        for (const item of controls) item.disabled = !visible;
      }
      if (field.venueField && control) {
        const venue = fieldValue(field.venueField);
        for (const option of control.options) {
          option.disabled = !!option.value && option.dataset.venue !== venue;
          option.hidden = option.disabled;
        }
        if (control.selectedOptions[0]?.disabled) control.value = "";
      }
    }
    const format = form.elements.namedItem("teaching_format"),
      capacity = form.elements.namedItem("capacity");
    if (format && capacity) {
      capacity.readOnly = format.value === "ONE_TO_ONE";
      if (capacity.readOnly) capacity.value = "1";
    }
  }
  form.onchange = updateDependencies;
  updateDependencies();
  form.onsubmit = async (e) => {
    e.preventDefault();
    const button = form.querySelector("[type=submit]");
    const buttonText = button.textContent;
    button.disabled = true;
    button.textContent = "Saving…";
    dialog.classList.add("is-saving");
    try {
      const fd = new FormData(form),
        data = {};
      for (const f of fields) {
        if (f.type === "note") continue;
        const controls = controlsFor(f.name),
          wrapper = fieldWrapper(f.name),
          inactive =
            (wrapper && wrapper.hidden) ||
            (controls.length && controls.every((control) => control.disabled));
        if (inactive) continue;
        let v =
          ["multiple", "weekday-multiple"].includes(f.type)
            ? fd.getAll(f.name)
            : f.type === "checkbox"
              ? fd.has(f.name)
              : fd.get(f.name);
        if (f.required && f.type === "weekday-multiple" && !v.length)
          throw new Error("Choose at least one repeat day.");
        if (f.type === "number") v = v === "" ? null : Number(v);
        if (v === "") v = null;
        data[f.name] = v;
      }
      await withSaving(() => save(data));
      dialog.close();
    } catch (error) {
      document.querySelector("#editor-error").textContent = error.message;
    } finally {
      button.disabled = false;
      button.textContent = buttonText;
      dialog.classList.remove("is-saving");
    }
  };
  dialog.showModal();
}
for (const id of ["close-editor", "cancel-editor"])
  document.getElementById(id).onclick = () => dialog.close();
