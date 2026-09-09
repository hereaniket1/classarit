(() => {
  const toast = document.getElementById('signup-toast');
  let toastTimer;
  document.querySelectorAll('[data-signup]').forEach(button => button.addEventListener('click', () => {
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 6000);
  }));
  document.querySelector('[data-dismiss-toast]')?.addEventListener('click', () => { toast.hidden = true; });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && toast) toast.hidden = true; });

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
    check(); // The server session, never the message, is proof of login.
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
    // Polling also handles providers that sever window.opener for isolation.
    timer = setTimeout(check, 1500);
  });
  window.addEventListener('pagehide', stop);
})();
