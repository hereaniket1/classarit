document.querySelectorAll(".sidebar .nav-link").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".sidebar .nav-link").forEach((el) => el.classList.remove("active"));
    button.classList.add("active");
    document.querySelectorAll(".page-section").forEach((section) => section.classList.remove("active"));
    document.getElementById(button.dataset.section).classList.add("active");
  });
});

async function markAttendance(classId, status) {
  const form = new FormData();
  form.append("status", status);
  const response = await fetch(`/api/classes/${classId}/attendance`, { method: "POST", body: form, headers: { "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]').content } });
  if (!response.ok) { alert("Could not save attendance. Please refresh and try again."); return; }
  location.reload();
}

function confirmCancel(classId) {
  if (confirm("Cancel this class?")) {
    markAttendance(classId, "Teacher Cancelled");
  }
}

function openNotes(classId) {
  alert(`Notes workflow can be attached to class ${classId} in the next iteration.`);
}
