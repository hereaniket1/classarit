import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(process.env.CLASSARIT_PLAYWRIGHT_PACKAGE||import.meta.url);
const {chromium}=require('playwright');
const root=process.cwd();
const fixture=path.join(root,'.cache','loading-review');
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let failSection=false,failSave=true,individual=false,referenceLoads=0;
 await page.route('**/*', async route=>{
  const url=new URL(route.request().url());
  if(url.hostname==='cdn.jsdelivr.net') return route.fulfill({body:await fs.readFile('.cache/admissions-review/bootstrap.min.css'),contentType:'text/css'});
  if(url.hostname!=='classarit.test') return route.abort();
  if(url.pathname.startsWith('/api/')) {
   if(route.request().method()!=='GET') return route.fulfill({status:failSave?503:200,contentType:'application/json',body:JSON.stringify(failSave?{detail:'Simulated save failure'}:{id:'saved'})});
   if(failSection) return route.fulfill({status:503,contentType:'text/html',body:'Unavailable'});
   const snapshot=JSON.parse(await fs.readFile(path.join(fixture,'snapshot.json')));
   if(url.pathname.endsWith('/action-refs')) referenceLoads++;
   if(url.pathname.endsWith('/calendar')) {
    snapshot.sessions = snapshot.sessions.slice(0,1).map(s=>({...s,status:'SCHEDULED',starts_at:new Date(Date.now()+3600000).toISOString(),ends_at:new Date(Date.now()+7200000).toISOString()}));
    snapshot.policy=null;
   }
   snapshot.workspace.workspace_type=individual?"INDIVIDUAL":"INSTITUTE";
   snapshot.calendar={month:url.searchParams.get('month')||new Date().toISOString().slice(0,7),sessions:snapshot.sessions};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(snapshot)});
  }
  const file=url.pathname.startsWith('/static/')?path.join(root,'app',url.pathname):path.join(fixture,'workspace.html');
  return route.fulfill({body:await fs.readFile(file),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'});
 });
 await page.goto('http://classarit.test/workspace');
 for(const width of [390,1440]) {
  await page.setViewportSize({width,height:950});
  for(const tab of ['dashboard','calendar']) {
   if(width<800) await page.locator('.nav-toggle').click();
   await page.locator(`[data-tab="${tab}"]`).click();
   await page.waitForFunction(()=>document.querySelector('#workspace-content').getAttribute('aria-busy')==='false');
   if(tab==='calendar') {
    assert.equal(await page.locator('.weekday-row span').count(),7);
    assert.equal(await page.locator('.weekday-row span').first().textContent(),'Mon');
    assert.equal(await page.locator('.calendar-key').count(),3);
    await page.locator('[data-calendar-day]').first().click();
    await page.locator('#calendar-popup').waitFor();
    await page.locator('[aria-label="Close day schedule"]').click();
    if(width===1440) {
     await page.locator('.calendar-day').filter({has:page.locator('.day-marker')}).first().click();
     const before=referenceLoads;
     await page.locator('[data-calendar-action="cancel"]').first().click();
     await page.waitForFunction(()=>document.querySelector('#editor').open);
     assert.equal(referenceLoads,before+1);
     assert.equal(await page.locator('#editor [name="grant_makeups"]').count(),1);
     await page.locator('#cancel-editor').click();
    }
   } else assert.equal(await page.locator('.agenda-day').count(),2);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.screenshot({path:path.join(fixture,`${tab}-${width}.png`),fullPage:true});
  }
 }
 for(const tab of ['classes','students','sessions','venues','settings']) {
  await page.locator(`[data-tab="${tab}"]`).click();
  await page.waitForFunction(()=>document.querySelector('#workspace-content').getAttribute('aria-busy')==='false');
  assert.equal(await page.locator('.global-page-loader').count(),0);
 }
 failSection=true;
 await page.locator('[data-tab="students"]').click();
 await page.getByText('This section could not be loaded. Choose it again to retry.').waitFor();
 failSection=false;
 await page.locator('[data-tab="students"]').click();
 await page.locator('.quick-action[data-action="student"]').click();
 await page.locator('#editor [name="full_name"]').fill('Loading test');
 await page.locator('#editor button[type="submit"]').click();
 await page.getByText('Simulated save failure',{exact:true}).waitFor();
 assert.equal(await page.locator('#save-overlay').isHidden(),true);
 assert.equal(await page.locator('#editor button[type="submit"]').isEnabled(),true);
 assert.equal(await page.locator('#editor button[type="submit"]').textContent(),'Save');
 assert.equal(await page.locator('#editor').evaluate(el=>el.classList.contains('is-saving')),false);
 failSave=false;
 await page.locator('#editor button[type="submit"]').click();
 await page.waitForFunction(()=>!document.querySelector('#editor').open);
 assert.equal(await page.locator('#save-overlay').isHidden(),true);
 assert.equal(await page.locator('.global-page-loader').count(),0);
 for (const single of [false,true]) {
  individual=single;
  await page.locator('[data-tab="settings"]').click();
  await page.waitForFunction(()=>document.querySelector('#workspace-content').getAttribute('aria-busy')==='false');
  assert.equal(await page.locator('[data-action="invite"]').count(),single?0:1);
  await page.locator('.quick-action[data-action="program"]').click();
  await page.waitForFunction(()=>document.querySelector('#editor').open);
  assert.equal(await page.locator('#editor [name="teacher_ids"]').count()>0,!single);
  await page.locator('#cancel-editor').click();
 }
 assert.deepEqual(errors,[]);
 console.log('Passed: workspace section navigation, failed load retry, failed save cleanup and successful save retry.');
} finally {await browser.close();}
