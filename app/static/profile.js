const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
const notice = document.querySelector("#notice");
const loading = window.ClassaritLoading;

function show(message, error = false) {
  notice.textContent = message;
  notice.classList.toggle("error", error);
  notice.hidden = false;
  if (!error) setTimeout(() => { notice.hidden = true; notice.textContent = ""; }, 2500);
}

async function api(path, method, data) {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Request failed. Please try again.");
  return payload;
}

document.querySelector("#profile-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const card = document.querySelector("#profile-details-card");
  loading?.busy(card, "Saving profile details");
  try {
    const payload = Object.fromEntries(new FormData(event.currentTarget));
    if (!payload.date_of_birth) payload.date_of_birth = null;
    if (!payload.country) payload.country = null;
    await api("/api/account/profile", "PATCH", payload);
    show("Profile updated.");
  } catch (error) {
    show(error.message, true);
  } finally {
    loading?.end(card);
  }
});

document.querySelector("#send-profile-otp")?.addEventListener("click", async (event) => {
  const card = document.querySelector("#email-verification-card");
  const button = event.currentTarget;
  loading?.busy(card, "Sending verification email");
  try {
    const result = await api("/auth/email/verify/start", "POST");
    const form = document.querySelector("#profile-otp-form");
    form.elements.challenge_id.value = result.challenge_id;
    form.hidden = false;
    button.hidden = true;
    show(`Verification code sent to ${result.email}.`);
    form.elements.code.focus();
  } catch (error) {
    show(error.message, true);
  } finally {
    loading?.end(card);
  }
});

document.querySelector("#profile-otp-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const card = document.querySelector("#email-verification-card");
  loading?.busy(card, "Verifying email");
  try {
    await api("/auth/email/verify/complete", "POST", Object.fromEntries(new FormData(event.currentTarget)));
    loading?.reload("profile") || window.location.reload();
  } catch (error) {
    show(error.message, true);
    loading?.end(card);
  }
});

document.querySelector("#logout")?.addEventListener("click", async () => {
  try {
    const response = await fetch("/auth/logout", {
      method: "POST",
      body: new URLSearchParams({ csrf_token: csrf }),
    });
    if (response.ok) loading?.navigate("/", "home") || window.location.assign("/");
    else show("Could not log out. Please retry.", true);
  } catch (error) { show(error.message, true); }
});
