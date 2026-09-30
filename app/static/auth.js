(() => {
  const invitationForm = document.getElementById('invitation-request-form');
  const invitationPanel = invitationForm?.closest('section');
  const invitationVerify = document.getElementById('invitation-verify-form');
  const invitationVerifyStatus = document.getElementById('invitation-verify-status');
  invitationForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = invitationForm.querySelector('button[type=submit]');
    const status = document.getElementById('invitation-request-status');
    button.disabled = true;
    status.textContent = 'Sending your request…';
    try {
      const response = await fetch('/auth/invitation-requests', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(invitationForm)))});
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Check your request details and try again.');
      status.textContent = payload.message;
      if (payload.verification_required) {
        invitationVerify.hidden = false;
        invitationVerify.elements.challenge_id.value = payload.challenge_id;
        invitationVerifyStatus.textContent = payload.message;
        invitationVerify.elements.code.value = '';
        invitationVerify.elements.code.focus();
      }
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  });
  document.getElementById('invitation-resend')?.addEventListener('click', () => invitationForm.requestSubmit());
  invitationVerify?.addEventListener('submit', async event => {
    event.preventDefault();
    window.ClassaritLoading?.lockPage('Verifying access request');
    try {
      const response = await fetch('/auth/invitation-requests/verify', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(Object.fromEntries(new FormData(invitationVerify)))
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Verification failed. Please retry.');
      invitationVerify.hidden = true;
      invitationForm.reset();
      document.getElementById('invitation-request-status').textContent = payload.message;
    } catch (error) { invitationVerifyStatus.textContent = error.message; }
    finally { window.ClassaritLoading?.unlockPage(); }
  });
  const signupPanel = document.getElementById('signup-panel');
  const showInvitation = () => {
    if (!invitationForm) { window.ClassaritLoading?.navigate('/login#invitation', 'invitation form') || window.location.assign('/login#invitation'); return; }
    if (signupPanel) signupPanel.hidden = true;
    invitationPanel.hidden = false;
    invitationPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
    invitationForm.elements.full_name.focus({ preventScroll: true });
  };
  document.querySelectorAll('[data-request-invitation]').forEach(button => button.addEventListener('click', event => {
    event.preventDefault();
    showInvitation();
  }));
  if (window.location.hash === '#invitation') showInvitation();
  document.querySelector('[data-close-invitation]')?.addEventListener('click', () => {
    invitationPanel.hidden = true;
    history.replaceState(null, '', window.location.pathname + window.location.search);
  });
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
    if (invitationPanel) invitationPanel.hidden = true;
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
    if (!signupPanel) { loading?.navigate('/login#signup', 'signup form') || window.location.assign('/login#signup'); return; }
    if (invitationPanel) invitationPanel.hidden = true;
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
    loading?.lockPage('Signing in');
    try {
      await json('/auth/password/login', Object.fromEntries(new FormData(loginForm)));
      const destination = await loginDestination();
      loading?.navigate(destination, 'dashboard') || window.location.assign(destination);
    } catch (error) {
      loginFormStatus.textContent = error.message;
      loading?.unlockPage();
    }
  });
  startForm?.addEventListener('submit', async event => {
    event.preventDefault();
    signupStatus.textContent = 'Creating your account…';
    const button = startForm.querySelector('button');
    button.disabled = true;
    let leaving = false;
    let focusVerification = false;
    loading?.lockPage('Creating your account');
    try {
      const payload = Object.fromEntries(new FormData(startForm));
      payload.accepted_terms = payload.accepted_terms === 'true';
      const result = await json('/auth/password/register', payload);
      if (!result.verification_required) {
        leaving = true;
        loading?.navigate('/dashboard', 'dashboard') || window.location.assign('/dashboard');
        return;
      }
      verifyForm.elements.challenge_id.value = result.challenge_id;
      sent.textContent = `We sent a 6-digit code to ${result.email}.`;
      startForm.hidden = true;
      verifyForm.hidden = false;
      signupStatus.textContent = '';
      focusVerification = true;
    } catch (error) {
      signupStatus.textContent = error.message;
    } finally {
      button.disabled = false;
      if (!leaving) loading?.unlockPage();
      if (focusVerification) verifyForm.elements.code.focus();
    }
  });
  verifyForm?.addEventListener('submit', async event => {
    event.preventDefault();
    signupStatus.textContent = 'Verifying…';
    const button = verifyForm.querySelector('button');
    button.disabled = true;
    let leaving = false;
    loading?.lockPage('Verifying your account');
    try {
      await json('/auth/password/register/verify', Object.fromEntries(new FormData(verifyForm)));
      leaving = true;
      loading?.navigate('/dashboard', 'dashboard') || window.location.assign('/dashboard');
    } catch (error) {
      signupStatus.textContent = error.message;
      button.disabled = false;
    } finally {
      if (!leaving) loading?.unlockPage();
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
      loginDestination().then(url => loading?.replace(url, 'dashboard') || window.location.replace(url));
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
          loading?.navigate(payload.next_url || '/dashboard', 'dashboard') || window.location.assign(payload.next_url || '/dashboard');
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
