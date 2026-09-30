const csrf = document.querySelector('meta[name="csrf-token"]').content;
const rows = document.querySelector('#request-rows');
const filter = document.querySelector('#request-filter');
const status = document.querySelector('#requests-status');
const previous = document.querySelector('#requests-prev');
const next = document.querySelector('#requests-next');
let offset = 0;
let revision = 0;
let busy = false;
const reviewLink = new URLSearchParams(location.hash.replace(/^#/, ''));
if (reviewLink.get('request')) filter.value = 'ALL';

async function api(url, method = 'GET', data) {
  const response = await fetch(url, {method, credentials: 'same-origin', cache: 'no-store',
    headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf},
    ...(data ? {body: JSON.stringify(data)} : {})});
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Check the details and try again.');
  return result;
}
function cell(row, text) {
  const element = document.createElement('td');
  element.textContent = text;
  row.append(element);
  return element;
}
function date(value) { return value ? new Date(value).toLocaleString() : 'Not sent'; }
async function load() {
  const current = ++revision;
  status.textContent = 'Loading requestsâ€¦';
  previous.disabled = next.disabled = true;
  try {
    const data = await api(`/api/executive/invitation-requests?status=${filter.value}&offset=${offset}${reviewLink.get('request') ? '&request_id='+encodeURIComponent(reviewLink.get('request')) : ''}`);
    if (current !== revision) return;
    rows.replaceChildren();
    for (const item of data.requests) {
      const row = document.createElement('tr');
      row.id = 'request-' + item.id;
      cell(row, `${item.full_name}\n${item.email}`);
      cell(row, `${item.usage_type === 'ORGANIZATION' ? 'Organization' : item.usage_type === 'INDIVIDUAL' ? 'Individual' : 'Not selected'} Â· ${item.country}`);
      cell(row, date(item.requested_at));
      cell(row, item.status + (item.verification_required ? (item.email_verified_at ? ' Â· Email verified' : ' Â· Awaiting email verification') : ' Â· Legacy request'));
      cell(row, date(item.last_email_sent_at));
      const actions = cell(row, '');
      const add = (label, action) => {
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'btn btn-sm btn-outline-primary';
        button.textContent = label;
        button.addEventListener('click', async () => {
          if (busy) return;
          busy = true;
          rows.querySelectorAll('button').forEach(b => { b.disabled = true; });
          try {
            let reviewResult;
            if (action === 'email') await api(`/api/executive/invitation-requests/${item.id}/email`, 'POST');
            else reviewResult = await api(`/api/executive/invitation-requests/${item.id}`, 'PATCH', {status: action});
            await load();
            status.textContent = action === 'email' ? 'Invitation accepted by the email provider.' : action === 'APPROVED' ? (reviewResult.email_sent ? 'Approved. Access email accepted by the email provider.' : 'Approval saved. Email needs retry: ' + reviewResult.email_error) : 'Request declined.';
          } catch (error) { status.textContent = error.message; }
          finally { busy = false; rows.querySelectorAll('button').forEach(b => { b.disabled = false; }); }
        });
        actions.append(button);
      };
      if (item.status !== 'APPROVED' && (!item.verification_required || item.email_verified_at)) add('Approve', 'APPROVED');
      if (item.status !== 'REJECTED') add('Reject', 'REJECTED');
      if (item.status === 'APPROVED') add(item.last_email_sent_at ? 'Resend email' : 'Send invitation', 'email');
      rows.append(row);
      if (String(item.id) === reviewLink.get('request')) {
        row.style.background = '#edf4ff';
        const heading = document.createElement('strong');
        heading.textContent = reviewLink.get('decision') === 'REJECTED' ? 'Use Reject below to confirm your decision.' : 'Use Approve below after email verification to grant access.';
        actions.prepend(heading);
        row.scrollIntoView({block:'center'});
      }
    }
    status.textContent = data.requests.length ? `Showing ${offset+1}â€“${offset+data.requests.length}` : 'No requests in this view.';
    previous.disabled = offset === 0;
    next.disabled = !data.has_more;
  } catch (error) { if (current === revision) status.textContent = error.message; }
}
filter.addEventListener('change', () => { reviewLink.delete('request'); history.replaceState(null, '', location.pathname); offset = 0; load(); });
previous.addEventListener('click', () => { offset = Math.max(0, offset-50); load(); });
next.addEventListener('click', () => { offset += 50; load(); });
load();

const termsForm = document.querySelector('#terms-editor');
const termsStatus = document.querySelector('#terms-editor-status');
const save = termsForm.querySelector('button');
api('/api/executive/terms').then(data => {
  termsForm.elements.title.value = data.title;
  termsForm.elements.body.value = data.body;
  save.disabled = false;
}).catch(error => { termsStatus.textContent = error.message; });
termsForm.addEventListener('submit', async event => {
  event.preventDefault(); save.disabled = true;
  try {
    await api('/api/executive/terms', 'PUT', Object.fromEntries(new FormData(termsForm)));
    termsStatus.textContent = 'Saved. New signup pages will show these terms.';
  } catch (error) { termsStatus.textContent = error.message; }
  finally { save.disabled = false; }
});
