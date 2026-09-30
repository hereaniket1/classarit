(() => {
  const form = document.getElementById('google-profile-form');
  if (!form) return;
  const status = document.getElementById('google-profile-status');
  const loading = window.ClassaritLoading;
  form.addEventListener('submit', async event => {
    event.preventDefault();
    status.textContent = '';
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    loading?.lockPage('Saving your profile');
    try {
      const data = Object.fromEntries(new FormData(form));
      const response = await fetch('/auth/google/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': data.csrf_token || '' },
        credentials: 'same-origin',
        body: JSON.stringify({
          full_name: data.full_name,
          phone: data.phone || null,
          account_type: data.account_type,
          accepted_terms: data.accepted_terms === 'true',
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || 'Please try again.');
      loading?.navigate('/dashboard', 'dashboard') || window.location.assign('/dashboard');
    } catch (error) {
      status.textContent = error.message;
      button.disabled = false;
      loading?.unlockPage();
    }
  });
})();
