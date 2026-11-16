import './account-dashboard.js';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const modeName = mode => ({ONLINE:'Online',IN_PERSON:'In person',HYBRID:'Hybrid'}[mode] || mode);
let offset=0, searchVersion=0;
const filters={q:'',location:'',mode:''};
const skeleton = '<div class="student-skeleton" role="status" aria-label="Loading"></div>';
async function request(path,method='GET') {
  const response=await fetch(path,{method,headers:{'X-CSRF-Token':$('meta[name="csrf-token"]').content},signal:AbortSignal.timeout(25000)});
  if(response.status===401){location.assign('/login');throw new Error('Please sign in again.');}
  const result=await response.json();
  if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Unable to complete this request. Please retry.');
  return result;
}
function report(error){$('#notice').hidden=false;$('#notice').textContent=error.name==='TimeoutError'?'The request timed out. Refresh your classes to check whether enrollment completed.':error.message;}
function empty(text){return `<p class="student-empty">${esc(text)}</p>`;}
async function loadUpcoming(){
  $('#student-agenda').innerHTML=skeleton;
  try{
    const data=await request('/api/student/upcoming');
    $('#student-agenda').innerHTML=data.sessions.map(s=>{
      const date=new Intl.DateTimeFormat(undefined,{timeZone:s.timezone,weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).format(new Date(s.starts_at));
      const end=new Intl.DateTimeFormat(undefined,{timeZone:s.timezone,hour:'numeric',minute:'2-digit'}).format(new Date(s.ends_at));
      const safeURL=/^https?:\/\//i.test(s.meeting_url||'')?s.meeting_url:null;
      return `<article class="student-session"><time>${esc(date)} – ${esc(end)}<small>${esc(s.timezone)}</small></time><div><strong>${esc(s.title)}</strong><small>${esc(s.workspace_name)} · ${esc(modeName(s.delivery_mode))}</small>${s.venue_name?`<small>${esc(s.venue_name)} · ${esc(s.address)}</small>`:''}</div>${safeURL?`<a class="btn btn-outline-primary" href="${esc(safeURL)}" target="_blank" rel="noopener noreferrer">Join class</a>`:''}</article>`;
    }).join('')||empty('No upcoming classes yet. Find a class to join, or ask your teacher to add your verified email.');
    $('#student-enrollments').innerHTML=data.classes.map(p=>`<article class="workspace-card"><h3>${esc(p.name)}</h3><small>${esc(p.workspace_name)} · ${esc(p.status)}</small></article>`).join('')||empty('You have not enrolled in any classes yet.');
  }catch(error){$('#student-agenda').innerHTML=empty('Could not load your classes.');report(error);}
}
async function search(){
  const version=++searchVersion;
  $('#student-results').innerHTML=skeleton;
  $('#student-next').disabled=$('#student-prev').disabled=true;
  try{
    const data=await request('/api/student/classes?'+new URLSearchParams({...filters,offset}));
    if(version!==searchVersion)return;
    $('#student-results').innerHTML=data.classes.map(p=>`<article class="workspace-card"><h3>${esc(p.name)}</h3><small>${esc(p.workspace_name)}${p.teachers?' · '+esc(p.teachers):''}</small><p>${esc(p.description)}</p><small>${esc(modeName(p.default_delivery_mode))} · ${esc(p.default_duration_minutes)} minutes${p.level?' · '+esc(p.level):''}</small>${p.location?`<p>${esc(p.venue_name)} · ${esc(p.location)}</p>`:''}<p>${esc(p.seats_available)} seats available</p><button class="btn btn-primary" type="button" data-enroll="${esc(p.id)}" ${p.enrolled||!p.seats_available?'disabled':''}>${p.enrolled?'Already enrolled':p.seats_available?'Join class':'Class full'}</button></article>`).join('')||empty('No matching classes. Try another location or learning mode.');
    $('#student-prev').disabled=offset===0;$('#student-next').disabled=!data.has_more;
  }catch(error){if(version!==searchVersion)return;$('#student-results').innerHTML=empty('Could not load class search. Please search again.');report(error);}
}
$('#student-search').addEventListener('submit',event=>{event.preventDefault();Object.assign(filters,Object.fromEntries(new FormData(event.currentTarget)));offset=0;search();});
$('#student-prev').onclick=()=>{offset=Math.max(0,offset-20);search();};
$('#student-next').onclick=()=>{offset+=20;search();};
$('#student-results').addEventListener('click',async event=>{
  const button=event.target.closest('[data-enroll]');if(!button||button.disabled)return;
  button.disabled=true;button.innerHTML='<span class="spinner-border spinner-border-sm" aria-hidden="true"></span> Joining…';
  try{await request(`/api/student/classes/${encodeURIComponent(button.dataset.enroll)}/enroll`,'POST');button.textContent='Already enrolled';$('#notice').hidden=false;$('#notice').textContent='You are enrolled. Your scheduled classes appear under Upcoming classes.';}
  catch(error){button.disabled=false;button.textContent='Join class';report(error);}
});
function navigate(){const discover=location.hash==='#discover';$('#upcoming').hidden=discover;$('#discover').hidden=!discover;document.querySelectorAll('.workspace-sidebar .account-nav').forEach(a=>a.classList.toggle('active',a.hash===(discover?'#discover':'#upcoming')));if(discover)search();else loadUpcoming();}
window.addEventListener('hashchange',navigate);navigate();
