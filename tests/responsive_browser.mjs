/** Run with CLASSARIT_PLAYWRIGHT_PACKAGE pointing to playwright/package.json if not locally installed.
 * Synthetic templates/assets are intercepted in the browser; no app server, account or DB is used.
 */
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const require=createRequire(process.env.CLASSARIT_PLAYWRIGHT_PACKAGE||import.meta.url);
const {chromium}=require('playwright');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const fixtures=process.env.CLASSARIT_LAYOUT_FIXTURES||'/tmp/classarit-responsive';
const browser=await chromium.launch({headless:true,channel:'chrome'});
try{
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.hostname==='cdn.jsdelivr.net'){await route.continue();return;}
  if(url.hostname!=='classarit.test'){await route.abort();return;}
  let file;
  if(url.pathname.startsWith('/static/')) file=path.join(root,'app',url.pathname);
  else if(url.pathname.includes('/section/')){
   const snapshot=JSON.parse(await fs.readFile(path.join(fixtures,'snapshot.json'),'utf8'));
   const section=url.pathname.split('/section/')[1];
   if(section==='calendar') snapshot.calendar={month:url.searchParams.get('month')||'2026-09',sessions:snapshot.sessions};
   if(section==='reporting') snapshot.metrics={students:snapshot.students.length,classes:snapshot.programs.length,upcoming_sessions:snapshot.sessions.length,teachers:snapshot.members.length};
   await route.fulfill({body:JSON.stringify(snapshot),contentType:'application/json'});
   return;
  }
  else if(url.pathname.endsWith('/calendar')){
   const snapshot=JSON.parse(await fs.readFile(path.join(fixtures,'snapshot.json'),'utf8'));
   await route.fulfill({body:JSON.stringify({month:url.searchParams.get('month'),sessions:snapshot.sessions}),contentType:'application/json'});
   return;
  }
  else if(url.pathname.endsWith('/snapshot')) file=path.join(fixtures,'snapshot.json');
  else file=path.join(fixtures,(url.pathname.slice(1)||'owner')+'.html');
  try{const body=await fs.readFile(file);const ext=path.extname(file);await route.fulfill({body,contentType:ext==='.css'?'text/css':ext==='.js'?'text/javascript':ext==='.json'?'application/json':'text/html'});}
  catch{await route.fulfill({status:404,body:'Not found'});}
 });
 async function fits(label){
  const size=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
  assert.ok(size.scroll<=size.width+1,`${label}: page overflow ${JSON.stringify(size)}`);
 }
 for(const width of [320,390,768,1024,1440,1920]){
  await page.setViewportSize({width,height:900});
  for(const name of ['owner','teacher','workspace','onboarding','invitation','home','login','callback']){
   await page.goto('http://classarit.test/'+name,{waitUntil:'networkidle'});
   await fits(`${name} at ${width}`);
   if(width<=800 && await page.locator('.nav-toggle').count()){
    await page.locator('.nav-toggle').click();await fits(`${name} open navigation at ${width}`);
    assert.equal(await page.locator('.nav-toggle').getAttribute('aria-expanded'),'true');
    await page.locator('.nav-toggle').press('Escape');
    assert.equal(await page.locator('.nav-toggle').getAttribute('aria-expanded'),'false');
   }
    if(name==='workspace'){
    assert.equal(await page.locator('#workspace-picker option').count(),3);
    if(width===390){
     await page.locator('#workspace-picker').selectOption('second');
     await page.waitForURL('**/workspaces/second');
     await page.goto('http://classarit.test/workspace',{waitUntil:'networkidle'});
    }
    assert.equal(await page.locator('.calendar-day').count(),30);
    assert.equal(await page.locator('.calendar-loader').count(),1);
    assert.equal(await page.locator('.month-calendar').getAttribute('aria-busy'),'false');
    assert.equal(await page.locator('.calendar-day.past').count(),13);
    assert.equal(await page.locator('.past-toggle').count(),0);
    assert.equal(await page.locator('.calendar-day.today').count(),1);
    await page.evaluate(()=>window.__noticeTest=Date.now());
    await page.evaluate(()=>import('/static/workspaces/api.js').then(({notice})=>notice('Saved successfully.')));
    assert.equal(await page.locator('#notice').isVisible(),true);
    await page.waitForFunction(()=>document.querySelector('#notice')?.hidden === true,{timeout:4000});
    await page.locator('.calendar-day.past').first().click();
    assert.equal(await page.locator('#calendar-popup:not([hidden])').isVisible(),true);
    assert.equal(await page.locator('#calendar-popup [data-calendar-action]').count(),0);
    await page.getByRole('button',{name:'Close day schedule'}).click();
    await page.getByRole('button',{name:'Next'}).click();
    await page.waitForFunction(()=>document.querySelector('.month-calendar h2')?.textContent.includes('October 2026'));
    assert.equal(await page.locator('.calendar-day').count(),31);
    await page.getByRole('button',{name:'Current month'}).click();
    await page.waitForFunction(()=>document.querySelector('.month-calendar h2')?.textContent.includes('September 2026'));
    assert.equal(await page.locator('.calendar-day.past').count(),13);
    const targetDay=page.locator('.calendar-day.busy').first();
    await targetDay.click();
    assert.equal(await page.locator('#calendar-popup:not([hidden])').isVisible(),true);
    assert.equal(await page.locator('#calendar-popup [data-calendar-action="session"]').count(),1);
    assert.equal(await page.locator('#calendar-popup [data-calendar-action="reschedule"]').count(),1);
    assert.equal(await page.locator('#calendar-popup [data-calendar-action="cancel"]').count(),1);
    await fits(`day popup at ${width}`);
    const selectedDay=await targetDay.getAttribute('data-calendar-day');
    await page.locator('#calendar-popup [data-calendar-action="session"]').click();
    assert.equal(await page.locator('#editor').isVisible(),true);
    assert.equal(await page.locator('#editor input[name="starts_at"]').inputValue(),`${selectedDay}T09:00`);
    await fits(`calendar add schedule form at ${width}`);
    await page.locator('#close-editor').click();
    await targetDay.click();
    await page.getByRole('button',{name:'Close day schedule'}).click();
    const calendarChecks=await page.evaluate(async()=>{
      const {calendarDays,setCalendarMonthData,updateCalendarView}=await import('/static/workspaces/calendar.js');
      const session={starts_at:'2026-09-14T18:00:00Z',ends_at:'2026-09-14T19:00:00Z',status:'SCHEDULED'};
      const data={workspace:{timezone:'Asia/Kolkata'},sessions:Array.from({length:5},()=>({...session}))};
      updateCalendarView('today',data);
      setCalendarMonthData({month:'2026-09',sessions:data.sessions});
      const days=calendarDays(data,new Date('2026-09-14T12:00:00Z'));
      data.sessions=data.sessions.slice(0,4);
      setCalendarMonthData({month:'2026-09',sessions:data.sessions});
      const four=calendarDays(data,new Date('2026-09-14T12:00:00Z'));
      return [days.length,days[12].state,days[13].state,days[13].today,days[14].state,four[13].state];
    });
    assert.deepEqual(calendarChecks,[30,'past','full',true,'full','busy']);
    assert.equal(await page.locator('a[href="/legacy/dashboard"]').count(),0);
    for(const action of await page.locator('.action-icon').all()){
     assert.ok(await action.getAttribute('title'));
     assert.ok(await action.getAttribute('aria-label'));
    }
    if([390,1440].includes(width))await page.screenshot({path:path.join(fixtures,`workspace-${width}.png`),fullPage:true});
    for(const section of ['calendar','classes','students','sessions','venues','team','makeups','reporting']){
     if(width<=800)await page.locator('.nav-toggle').click();
     await page.locator(`[data-tab="${section}"]`).click();await fits(`workspace/${section} at ${width}`);
    }
    if(width<=800)await page.locator('.nav-toggle').click();
    await page.locator('[data-tab="classes"]').click();
    await page.locator('[data-action="program"]').click();
    const dialog=page.locator('#editor');assert.equal(await dialog.isVisible(),true);
    await fits(`class form at ${width}`);
    const box=await dialog.boundingBox();assert.ok(box.width<=width && box.x>=0);
    await page.locator('#close-editor').click();
   }
   if(name==='owner' && [390,1440].includes(width)){
    if(width===390){const gear=await page.locator('.manage-workspace').first().boundingBox();assert.ok(gear.height>=44 && gear.width>=44);}
    await page.screenshot({path:path.join(fixtures,`owner-${width}.png`),fullPage:true});
   }
  }
 }
 await page.goto('http://classarit.test/workspace',{waitUntil:'networkidle'});
 await page.locator('#workspace-picker').selectOption('second');
 await page.waitForURL('**/workspaces/second');
 assert.deepEqual(errors,[]);
 console.log('Passed: 8 pages at 6 viewport widths, workspace sections/forms, mobile navigation and gear touch targets.');
}finally{await browser.close();}
