(() => {
  const signupPanel = document.getElementById('signup-panel');
  const signupStatus = document.getElementById('signup-status');
  const startForm = document.getElementById('signup-start-form');
  const verifyForm = document.getElementById('signup-verify-form');
  const sent = document.getElementById('signup-sent');
  const showSignup = () => {
    if (!signupPanel) { window.location.href = '/login#signup'; return; }
    signupPanel.hidden = false;
    signupPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    signupPanel.querySelector('input:not([type=hidden])')?.focus();
  };
  document.querySelectorAll('[data-signup]').forEach(button => button.addEventListener('click', event => {
    event.preventDefault();
    showSignup();
  }));
  if (window.location.hash === '#signup') showSignup();
  const json = async (url, body) => {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', body: JSON.stringify(body) });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'Please try again.');
    return payload;
  };
  startForm?.addEventListener('submit', async event => {
    event.preventDefault();
    signupStatus.textContent = 'Sending your OTP…';
    const button = startForm.querySelector('button');
    button.disabled = true;
    try {
      const payload = Object.fromEntries(new FormData(startForm));
      const result = await json('/auth/register/start', payload);
      verifyForm.elements.challenge_id.value = result.challenge_id;
      sent.textContent = `We sent a 6-digit code to ${result.email}.`;
      startForm.hidden = true;
      verifyForm.hidden = false;
      signupStatus.textContent = '';
      verifyForm.elements.code.focus();
    } catch (error) {
      signupStatus.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
  verifyForm?.addEventListener('submit', async event => {
    event.preventDefault();
    signupStatus.textContent = 'Verifying…';
    const button = verifyForm.querySelector('button');
    button.disabled = true;
    try {
      await json('/auth/register/verify', Object.fromEntries(new FormData(verifyForm)));
      window.location.assign('/dashboard');
    } catch (error) {
      signupStatus.textContent = error.message;
      button.disabled = false;
    }
  });

  const result = document.getElementById('auth-result');
  if (result?.dataset.success === 'true') {
    if (window.opener) {
      window.opener.postMessage({ type: 'classarit:login-complete' }, window.location.origin);
      window.close();
    } else {
      window.location.replace('/dashboard');
    }
  }

  if (result?.dataset.success === 'false' && window.opener) {
    window.opener.postMessage({ type: 'classarit:login-failed' }, window.location.origin);
  }

  const button = document.getElementById('google-login');
  if (!button) return;
  const status = document.getElementById('login-status');
  const fallback = document.getElementById('same-window-login');
  let popup, timer, attempts = 0;
  const stop = () => { clearTimeout(timer); button.disabled = false; };
  const check = async () => {
    try {
      const response = await fetch('/auth/me', { credentials: 'same-origin', cache: 'no-store' });
      if (response.ok && (await response.json()).authenticated) {
        stop();
        window.location.assign('/dashboard');
        return;
      }
    } catch (_) { /* A brief network interruption may resolve on the next poll. */ }
    if (++attempts >= 90) {
      stop();
      status.textContent = 'Login has not completed. Please try again or continue in this tab.';
      return;
    }
    timer = setTimeout(check, 2000);
  };
  window.addEventListener('message', event => {
    if (event.origin !== window.location.origin || event.source !== popup) return;
    if (event.data?.type === 'classarit:login-failed') {
      stop(); status.textContent = 'Login was not completed. Please try again.'; return;
    }
    if (event.data?.type !== 'classarit:login-complete') return;
    clearTimeout(timer);
    check();
  });
  button.addEventListener('click', () => {
    stop(); attempts = 0;
    const width = 500, height = 650;
    popup = window.open('/auth/google/login', 'classarit-google-login',
      `popup=yes,width=${width},height=${height},left=${Math.max(0,window.screenX+(window.outerWidth-width)/2)},top=${Math.max(0,window.screenY+(window.outerHeight-height)/2)}`);
    fallback.hidden = false;
    if (!popup) {
      status.textContent = 'Your browser blocked the popup. Continue in this tab to log in.';
      return;
    }
    button.disabled = true;
    status.textContent = 'Complete your login in the Google window. You can also continue in this tab.';
    timer = setTimeout(check, 1500);
  });
  window.addEventListener('pagehide', stop);
})();
