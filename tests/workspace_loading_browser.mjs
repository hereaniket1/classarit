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
 let failSection=false,failSave=true;
 await page.route('**/*', async route=>{
  const url=new URL(route.request().url());
  if(url.hostname==='cdn.jsdelivr.net') return route.fulfill({body:await fs.readFile('.cache/admissions-review/bootstrap.min.css'),contentType:'text/css'});
  if(url.hostname!=='classarit.test') return route.abort();
  if(url.pathname.startsWith('/api/')) {
   if(route.request().method()!=='GET') return route.fulfill({status:failSave?503:200,contentType:'application/json',body:JSON.stringify(failSave?{detail:'Simulated save failure'}:{id:'saved'})});
   if(failSection) return route.fulfill({status:503,contentType:'text/html',body:'Unavailable'});
   const snapshot=JSON.parse(await fs.readFile(path.join(fixture,'snapshot.json')));
   snapshot.calendar={month:url.searchParams.get('month')||new Date().toISOString().slice(0,7),sessions:snapshot.sessions};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(snapshot)});
  }
  const file=url.pathname.startsWith('/static/')?path.join(root,'app',url.pathname):path.join(fixture,'workspace.html');
  return route.fulfill({body:await fs.readFile(file),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'});
 });
 await page.goto('http://classarit.test/workspace');
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
 failSave=false;
 await page.locator('#editor button[type="submit"]').click();
 await page.waitForFunction(()=>!document.querySelector('#editor').open);
 assert.equal(await page.locator('#save-overlay').isHidden(),true);
 assert.equal(await page.locator('.global-page-loader').count(),0);
 assert.deepEqual(errors,[]);
 console.log('Passed: workspace section navigation, failed load retry, failed save cleanup and successful save retry.');
} finally {await browser.close();}
