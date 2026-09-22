(() => {
  const signupPanel = document.getElementById('signup-panel');
  const signupStatus = document.getElementById('signup-status');
  const startForm = document.getElementById('signup-start-form');
  const verifyForm = document.getElementById('signup-verify-form');
  const sent = document.getElementById('signup-sent');
  const loginForm = document.getElementById('password-login-form');
  const loginFormStatus = document.getElementById('password-login-status');
  const loginCard = document.querySelector('.login-card');
  const loading = window.ClassaritLoading;
  document.querySelectorAll('[data-login]').forEach(link => link.addEventListener('click', event => {
    if (!loginForm) return;
    event.preventDefault();
    signupPanel.hidden = true;
    loginCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    loginForm.elements.email.focus({ preventScroll: true });
  }));
  document.querySelectorAll('[data-toggle-password]').forEach(button => button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.togglePassword);
    const visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    button.setAttribute('aria-pressed', String(visible));
    button.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
    button.title = visible ? 'Hide password' : 'Show password';
  }));
  const termsPopup = document.getElementById('terms-popup');
  const openTerms = () => {
    if (!termsPopup) return;
    termsPopup.hidden = false;
    termsPopup.querySelector('[data-terms-close]')?.focus();
  };
  const closeTerms = () => {
    if (termsPopup) termsPopup.hidden = true;
  };
  document.querySelectorAll('[data-terms-open]').forEach(button => button.addEventListener('click', event => {
    event.preventDefault();
    openTerms();
  }));
  document.querySelectorAll('[data-terms-close]').forEach(button => button.addEventListener('click', closeTerms));
  termsPopup?.addEventListener('click', event => {
    if (event.target === termsPopup) closeTerms();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !termsPopup?.hidden) closeTerms();
  });
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
  document.querySelector('[data-close-signup]')?.addEventListener('click', () => {
    signupPanel.hidden = true;
    history.replaceState(null, '', window.location.pathname + window.location.search);
  });
  if (window.location.hash === '#signup') showSignup();
  const json = async (url, body) => {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin', body: JSON.stringify(body) });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || 'Please try again.');
    return payload;
  };
  loginForm?.addEventListener('submit', async event => {
    event.preventDefault();
    loginFormStatus.textContent = '';
    loading?.begin(loginCard, 'login', { rows: 3 });
    try {
      await json('/auth/password/login', Object.fromEntries(new FormData(loginForm)));
      window.location.assign('/dashboard');
    } catch (error) {
      loginFormStatus.textContent = error.message;
      loading?.end(loginCard);
    }
  });
  startForm?.addEventListener('submit', async event => {
    event.preventDefault();
    signupStatus.textContent = 'Creating your account…';
    const button = startForm.querySelector('button');
    button.disabled = true;
    loading?.begin(signupPanel, 'registration email', { rows: 3 });
    try {
      const payload = Object.fromEntries(new FormData(startForm));
      payload.accepted_terms = payload.accepted_terms === 'true';
      const result = await json('/auth/password/register', payload);
      if (!result.verification_required) {
        window.location.assign('/dashboard');
        return;
      }
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
      loading?.end(signupPanel);
    }
  });
  verifyForm?.addEventListener('submit', async event => {
    event.preventDefault();
    signupStatus.textContent = 'Verifying…';
    const button = verifyForm.querySelector('button');
    button.disabled = true;
    loading?.begin(signupPanel, 'account verification', { rows: 3 });
    try {
      await json('/auth/password/register/verify', Object.fromEntries(new FormData(verifyForm)));
      window.location.assign('/dashboard');
    } catch (error) {
      signupStatus.textContent = error.message;
      button.disabled = false;
    } finally {
      loading?.end(signupPanel);
    }
  });

  const loginDestination = async () => {
    try {
      const response = await fetch('/auth/me', { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) return '/dashboard';
      const payload = await response.json();
      return payload.next_url || '/dashboard';
    } catch (_) {
      return '/dashboard';
    }
  };

  const result = document.getElementById('auth-result');
  if (result?.dataset.success === 'true') {
    if (window.opener) {
      window.opener.postMessage({ type: 'classarit:login-complete' }, window.location.origin);
      window.close();
    } else {
      loginDestination().then(url => window.location.replace(url));
    }
  }

  if (result?.dataset.success === 'false' && window.opener) {
    window.opener.postMessage({ type: 'classarit:login-failed' }, window.location.origin);
  }

  const button = document.getElementById('google-login');
  if (!button) return;
  const status = document.getElementById('login-status');
  const fallback = document.getElementById('same-window-login');
  const googleReady = button.dataset.googleReady === 'true';
  let popup, timer, attempts = 0;
  const syncGoogleButton = () => {
    button.disabled = !googleReady;
  };
  syncGoogleButton();
  const stop = () => { clearTimeout(timer); syncGoogleButton(); };
  const check = async () => {
    try {
      const response = await fetch('/auth/me', { credentials: 'same-origin', cache: 'no-store' });
      if (response.ok) {
        const payload = await response.json();
        if (payload.authenticated) {
          stop();
          window.location.assign(payload.next_url || '/dashboard');
          return;
        }
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
  button.addEventListener('click', async () => {
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
