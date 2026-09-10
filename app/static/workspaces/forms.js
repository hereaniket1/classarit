import { esc } from "./api.js";
const dialog = document.querySelector("#editor"),
  form = document.querySelector("#editor-form");
export const field = (name, label, type = "text", options = {}) => ({
  name,
  label,
  type,
  ...options,
});
export function edit(title, fields, save) {
  document.querySelector("#editor-title").textContent = title;
  document.querySelector("#editor-error").textContent = "";
  document.querySelector("#editor-fields").innerHTML = fields
    .map((f) => {
      const attrs = `name="${esc(f.name)}" ${f.required ? "required" : ""}`;
      if (f.type === "checkbox")
        return `<label class="checkbox-label"><input type="checkbox" ${attrs} ${f.value ? "checked" : ""}>${esc(f.label)}</label>`;
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
      const control = form.elements.namedItem(field.name);
      if (field.visibleWhen) {
        const visible = field.visibleWhen.values.includes(
          form.elements.namedItem(field.visibleWhen.field).value,
        );
        control.closest("label").hidden = !visible;
        control.disabled = !visible;
      }
      if (field.venueField) {
        const venue = form.elements.namedItem(field.venueField).value;
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
    button.disabled = true;
    try {
      const fd = new FormData(form),
        data = {};
      for (const f of fields) {
        let v =
          f.type === "multiple"
            ? fd.getAll(f.name)
            : f.type === "checkbox"
              ? fd.has(f.name)
              : fd.get(f.name);
        if (f.type === "number") v = v === "" ? null : Number(v);
        if (v === "") v = null;
        data[f.name] = v;
      }
      await save(data);
      dialog.close();
    } catch (error) {
      document.querySelector("#editor-error").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  };
  dialog.showModal();
}
for (const id of ["close-editor", "cancel-editor"])
  document.getElementById(id).onclick = () => dialog.close();
