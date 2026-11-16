import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(process.env.CLASSARIT_PLAYWRIGHT_PACKAGE||import.meta.url);
const {chromium}=require('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
const fixture=path.join(process.cwd(),'.cache/loading-review');
try {
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let enrolled=false,fail=true,lastSearch;
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.hostname!=='classarit.test')return route.abort();
  if(url.pathname.startsWith('/api/student/')){
   let body;
   if(route.request().method()==='POST'){
    assert.ok(route.request().headers()['x-csrf-token']);
    if(fail)return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'This class is full.'})});
    enrolled=true;body={id:'enrollment'};
   }else if(url.pathname.endsWith('/upcoming'))body={classes:enrolled?[{name:'Maths',workspace_name:'Study studio',status:'ACTIVE'}]:[],sessions:enrolled?[{title:'Maths',workspace_name:'Study studio',starts_at:'2026-11-20T09:00:00Z',ends_at:'2026-11-20T10:00:00Z',timezone:'Asia/Kolkata',delivery_mode:'ONLINE',meeting_url:'https://example.com/lesson'}]:[]};
   else{lastSearch=url.searchParams;body={classes:[{id:'course',name:'Maths <script>alert(1)</script>',description:'Practice together',workspace_name:'Study studio',teachers:'Teacher',default_delivery_mode:'ONLINE',default_duration_minutes:60,seats_available:1,enrolled}],has_more:false};}
   return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  }
  const file=url.pathname.startsWith('/static/')?path.join(process.cwd(),'app',url.pathname):path.join(fixture,'student.html');
  await route.fulfill({body:await fs.readFile(file),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'});
 });
 await page.goto('http://classarit.test/student');
 await page.getByText('You have not enrolled in any classes yet.').waitFor();
 assert.equal(await page.locator('[data-action],#workspace-picker,a[href="/workspaces/new"],a[href="/dashboard?overview=1"]').count(),0);
 await page.locator('#user-dropdown summary').click();
 await page.getByRole('link',{name:'Edit profile'}).waitFor();
 await page.keyboard.press('Escape');
 await page.goto('http://classarit.test/student#discover');
 await page.getByRole('button',{name:'Join class',exact:true}).waitFor();
 assert.equal(await page.locator('#student-results script').count(),0);
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:900});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:path.join(fixture,`student-discovery-${width}.png`),fullPage:true});
 }
 await page.locator('[name="q"]').fill('Maths');await page.locator('[name="location"]').fill('Pune');await page.locator('[name="mode"]').selectOption('IN_PERSON');
 await page.getByRole('button',{name:'Search',exact:true}).click();
 await page.getByRole('button',{name:'Join class',exact:true}).waitFor();
 assert.equal(lastSearch.get('location'),'Pune');assert.equal(lastSearch.get('mode'),'IN_PERSON');
 await page.getByRole('button',{name:'Join class',exact:true}).click();
 await page.getByText('This class is full.').waitFor();
 assert.equal(await page.getByRole('button',{name:'Join class',exact:true}).isEnabled(),true);
 fail=false;await page.getByRole('button',{name:'Join class',exact:true}).click();
 await page.getByRole('button',{name:'Already enrolled'}).waitFor();
 await page.goto('http://classarit.test/student#upcoming');
 await page.getByRole('link',{name:'Join class',exact:true}).waitFor();
 assert.equal(await page.locator('.student-session').count(),1);
 assert.equal(await page.locator('#student-enrollments h3').textContent(),'Maths');
 assert.deepEqual(errors,[]);
 console.log('Passed: student navigation, no staff controls, safe results, filters, mobile layout, enrollment error recovery and upcoming classes.');
}finally{await browser.close();}
