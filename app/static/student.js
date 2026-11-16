import './account-dashboard.js';
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const modeName = mode => ({ONLINE:'Online',IN_PERSON:'In person',HYBRID:'Hybrid'}[mode] || mode);
const localZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata';
let offset=0, searchVersion=0, currentUpcoming={sessions:[],tasks:[]};
const filters={q:'',location:'',mode:''};
const skeleton = '<div class="student-skeleton" role="status" aria-label="Loading"></div>';
async function request(path,method='GET',body) {
  const response=await fetch(path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':$('meta[name="csrf-token"]').content},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(25000)});
  if(response.status===401){location.assign('/login');throw new Error('Please sign in again.');}
  const result=await response.json();
  if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Unable to complete this request. Please retry.');
  return result;
}
function report(error){$('#notice').hidden=false;$('#notice').textContent=error.name==='TimeoutError'?'The request timed out. Refresh to check whether your change was saved.':error.message;}
function empty(text){return `<p class="student-empty">${esc(text)}</p>`;}
const dateKey = date => { const d=new Date(date); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
const dayLabel = date => new Intl.DateTimeFormat(undefined,{weekday:'short',month:'short',day:'numeric'}).format(date);
const timeLabel = date => new Intl.DateTimeFormat(undefined,{hour:'numeric',minute:'2-digit'}).format(new Date(date));
function renderCalendar(data){
  const today=new Date();today.setHours(0,0,0,0);
  const days=Array.from({length:7},(_,i)=>new Date(today.getTime()+i*86400000));
  const sessions=data.sessions||[], tasks=data.tasks||[];
  $('#student-calendar').innerHTML=`<div class="student-calendar-grid">${days.map((day,index)=>{
    const key=dateKey(day);
    const items=[...sessions.filter(x=>dateKey(x.starts_at)===key).map(x=>({...x,kind:'class'})),...tasks.filter(x=>dateKey(x.starts_at)===key).map(x=>({...x,kind:'task'}))].sort((a,b)=>new Date(a.starts_at)-new Date(b.starts_at));
    return `<section class="student-day ${index===0?'is-today':''}"><header><strong>${esc(index===0?'Today':dayLabel(day))}</strong><small>${items.length?`${items.length} item${items.length===1?'':'s'}`:'Free'}</small></header><div class="student-day-items">${items.map(item=>item.kind==='class'?`<article class="student-calendar-item class-item"><span class="student-item-icon" aria-hidden="true">▣</span><div><strong>${esc(item.title)}</strong><small>${esc(timeLabel(item.starts_at))} – ${esc(timeLabel(item.ends_at))} · ${esc(item.workspace_name)}</small></div></article>`:`<article class="student-calendar-item task-item"><span class="student-item-icon" aria-hidden="true">✓</span><div><strong>${esc(item.title)}</strong><small>${esc(timeLabel(item.starts_at))} – ${esc(timeLabel(item.ends_at))}${item.location?' · '+esc(item.location):''}</small></div><button type="button" class="planner-delete" data-task="${esc(item.id)}" aria-label="Delete ${esc(item.title)}">×</button></article>`).join('')||'<p class="student-day-empty">No plans</p>'}</div></section>`;}).join('')}</div>`;
}
async function loadUpcoming(){
  $('#student-calendar').innerHTML=skeleton;
  try{
    currentUpcoming=await request('/api/student/upcoming');
    renderCalendar(currentUpcoming);
    $('#student-enrollments').innerHTML=(currentUpcoming.classes||[]).map(p=>`<article class="workspace-card"><h3>${esc(p.name)}</h3><small>${esc(p.workspace_name)} · ${esc(p.status)}</small></article>`).join('')||empty('You have not enrolled in any classes yet.');
    $('#planner-list').innerHTML=(currentUpcoming.tasks||[]).map(t=>`<article class="planner-list-item"><div><strong>${esc(t.title)}</strong><small>${esc(new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(new Date(t.starts_at)))}${t.location?' · '+esc(t.location):''}</small>${t.notes?`<p>${esc(t.notes)}</p>`:''}</div><button type="button" class="planner-delete" data-task="${esc(t.id)}" aria-label="Delete ${esc(t.title)}">×</button></article>`).join('')||empty('Your personal planner is empty. Add a school day, tuition, study session, or task above.');
  }catch(error){$('#student-calendar').innerHTML=empty('Could not load your week.');report(error);}
}
async function search(){
  const version=++searchVersion;$('#student-results').innerHTML=skeleton;$('#student-next').disabled=$('#student-prev').disabled=true;
  try{
    const data=await request('/api/student/classes?'+new URLSearchParams({...filters,offset}));if(version!==searchVersion)return;
    $('#student-results').innerHTML=data.classes.map(p=>`<article class="workspace-card"><h3>${esc(p.name)}</h3><small>${esc(p.workspace_name)}${p.teachers?' · '+esc(p.teachers):''}</small><p>${esc(p.description)}</p><small>${esc(modeName(p.default_delivery_mode))} · ${esc(p.default_duration_minutes)} minutes${p.level?' · '+esc(p.level):''}</small>${p.location?`<p>${esc(p.venue_name)} · ${esc(p.location)}</p>`:''}<p>${esc(p.seats_available)} seats available</p><button class="btn btn-primary" type="button" data-enroll="${esc(p.id)}" ${p.enrolled||!p.seats_available?'disabled':''}>${p.enrolled?'Already enrolled':p.seats_available?'Join class':'Class full'}</button></article>`).join('')||empty('No matching classes. Try another location or learning mode.');
    $('#student-prev').disabled=offset===0;$('#student-next').disabled=!data.has_more;
  }catch(error){if(version!==searchVersion)return;$('#student-results').innerHTML=empty('Could not load class search. Please search again.');report(error);}
}
$('#student-search').addEventListener('submit',event=>{event.preventDefault();Object.assign(filters,Object.fromEntries(new FormData(event.currentTarget)));offset=0;search();});
$('#student-prev').onclick=()=>{offset=Math.max(0,offset-20);search();};$('#student-next').onclick=()=>{offset+=20;search();};
$('#student-results').addEventListener('click',async event=>{const button=event.target.closest('[data-enroll]');if(!button||button.disabled)return;button.disabled=true;button.textContent='Joining…';try{await request(`/api/student/classes/${encodeURIComponent(button.dataset.enroll)}/enroll`,'POST');button.textContent='Already enrolled';$('#notice').hidden=false;$('#notice').textContent='You are enrolled. Your scheduled classes appear in your week.';await loadUpcoming();}catch(error){button.disabled=false;button.textContent='Join class';report(error);}});
$('#planner-form').addEventListener('submit',async event=>{event.preventDefault();const form=event.currentTarget,button=form.querySelector('button[type=submit]'),status=$('#planner-status');button.disabled=true;status.textContent='Saving…';try{const data=Object.fromEntries(new FormData(form));data.starts_at=new Date(data.starts_at).toISOString();data.ends_at=data.ends_at?new Date(data.ends_at).toISOString():null;data.timezone=localZone;await request('/api/student/planner/tasks','POST',data);form.reset();status.textContent='Added to your planner.';await loadUpcoming();}catch(error){status.textContent=error.message;}finally{button.disabled=false;}});
document.addEventListener('click',async event=>{const button=event.target.closest('[data-task]');if(!button)return;button.disabled=true;try{await request(`/api/student/planner/tasks/${encodeURIComponent(button.dataset.task)}`,'DELETE');await loadUpcoming();}catch(error){button.disabled=false;report(error);}});
function navigate(){const target=location.hash.slice(1)||'upcoming';document.querySelectorAll('.workspace-sidebar .account-nav').forEach(a=>a.classList.toggle('active',a.hash===`#${target}`));document.getElementById(target)?.scrollIntoView({behavior:'smooth',block:'start'});if(target==='discover')search();}
window.addEventListener('hashchange',navigate);loadUpcoming();navigate();
