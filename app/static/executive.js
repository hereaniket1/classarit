const notice = document.querySelector('#notice');
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
const labels = {
  google_new_accounts_enabled: ['Google new-account login', 'When off, existing Google users can log in, but new emails cannot be created through Google.'],
  signup_enabled: ['Email OTP signup', 'When off, new email OTP registrations are paused. Existing login methods still work.'],
  notification_emails_enabled: ['Operational emails', 'Invitation and schedule notification emails are sent only when this is on.'],
};
function show(message, error=false){ notice.hidden=false; notice.textContent=message; notice.classList.toggle('error', error); if(!error) setTimeout(()=>{notice.hidden=true},2500); }
async function api(path, options={}){ const response=await fetch(path,{credentials:'same-origin',...options}); const payload=await response.json().catch(()=>({})); if(!response.ok) throw new Error(payload.detail || 'Request failed.'); return payload; }
function metric(label,value){ return `<div class="metric"><span class="metric-icon">•</span><div><strong>${value ?? 0}</strong><span>${label}</span></div></div>`; }
function render(data){
  const r=data.registrations||{};
  document.querySelector('#registration-metrics').innerHTML = [
    metric('Students', r.students), metric('Individual', r.individual_workspaces), metric('Institutes', r.institute_workspaces), metric('Teachers', r.teachers), metric('Active users', r.active_users)
  ].join('');
  document.querySelector('#settings-grid').innerHTML = Object.entries(labels).map(([key,[title,help]]) => `<label class="setting-toggle"><span><strong>${title}</strong><small>${help}</small></span><span class="switch"><input type="checkbox" data-setting="${key}" ${data.settings?.[key] ? 'checked' : ''}><span class="slider"></span></span></label>`).join('');
  const apiData=data.api||{}, totals=apiData.totals||{}, daily=apiData.daily||[];
  document.querySelector('#api-total').textContent = `${totals.calls||0} calls · ${totals.avg_latency_ms||0}ms avg · ${totals.errors||0} server errors`;
  const max=Math.max(1,...daily.map(x=>x.max_latency_ms||0));
  document.querySelector('#latency-chart').innerHTML = daily.length ? daily.map(x=>`<div class="latency-bar"><span style="height:${Math.max(4,Math.round((x.avg_latency_ms||0)/max*140))}px"></span><strong>${x.avg_latency_ms||0}ms</strong><small>${x.day}</small><small>${x.calls} calls</small></div>`).join('') : '<p class="subtext">No API samples yet.</p>';
  document.querySelector('#route-table').innerHTML = (apiData.routes||[]).map(x=>`<tr><td>${x.route_template}</td><td>${x.calls}</td><td>${x.avg_latency_ms||0}ms</td><td>${x.max_latency_ms||0}ms</td></tr>`).join('') || '<tr><td colspan="4">No route samples yet.</td></tr>';
}
async function load(){ try{ render(await api('/api/executive/dashboard')); }catch(error){ show(error.message,true); } }
document.addEventListener('change', async event => { const input=event.target.closest('[data-setting]'); if(!input) return; input.disabled=true; try{ const payload={ [input.dataset.setting]: input.checked }; const result=await api('/api/executive/settings',{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(payload)}); show('Setting updated.'); const current=await api('/api/executive/dashboard'); current.settings=result.settings; render(current); }catch(error){ input.checked=!input.checked; show(error.message,true); }finally{ input.disabled=false; } });
document.querySelector('#logout')?.addEventListener('click', async () => { const form=new URLSearchParams({csrf_token:csrf}); const response=await fetch('/auth/logout',{method:'POST',body:form}); if(response.ok) location.href='/'; else show('Could not log out.',true); });
load();
