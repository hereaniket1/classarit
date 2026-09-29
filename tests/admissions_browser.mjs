import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(process.env.CLASSARIT_PLAYWRIGHT_PACKAGE||import.meta.url);
const {chromium}=require('playwright');
const root=process.cwd();
const fixtures=path.join(root,'.cache','admissions-review');
const browser=await chromium.launch({headless:true,channel:'chrome'});
const errors=[];
const requests=[];
let requestStatus='PENDING';
let invitationMode=true;
try {
  const page=await browser.newPage();
  page.setDefaultTimeout(10000);
  page.on('pageerror', error=>errors.push(error.message));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.hostname==='cdn.jsdelivr.net') { await route.fulfill({body:await fs.readFile(path.join(fixtures,'bootstrap.min.css')),contentType:'text/css'}); return; }
    if(url.hostname!=='classarit.test') { await route.abort(); return; }
    const payload=route.request().postDataJSON();
    const json=body=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
    if(url.pathname.startsWith('/api/') || url.pathname==='/auth/invitation-requests') {
      requests.push({url:url.pathname,method:route.request().method(),payload});
      if(url.pathname==='/auth/invitation-requests') return json({ok:true,message:'Your request has been received.'});
      if(url.pathname==='/api/executive/dashboard') return json({settings:{invite_request_enabled:invitationMode},registrations:{},api:{}});
      if(url.pathname==='/api/executive/settings') { invitationMode=payload.invite_request_enabled; return json({settings:{invite_request_enabled:invitationMode}}); }
      if(url.pathname==='/api/executive/terms') return json({title:'Review terms',body:'Review text'});
      if(url.pathname==='/api/executive/invitation-requests') return json({requests:[{id:'request-1',full_name:'<img src=x onerror=alert(1)>',email:'review@example.com',country:'IN',usage_type:'ORGANIZATION',status:requestStatus,requested_at:'2026-09-29T10:00:00Z'}],has_more:false});
      if(route.request().method()==='PATCH') requestStatus=payload.status;
      return json({ok:true});
    }
    const file=url.pathname.startsWith('/static/') ? path.join(root,'app',url.pathname) : path.join(fixtures,url.pathname.slice(1)+'.html');
    try { await route.fulfill({body:await fs.readFile(file),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'}); }
    catch { await route.fulfill({status:404,body:'Missing fixture'}); }
  });
  for(const width of [390,1440]) {
    await page.setViewportSize({width,height:1000});
    for(const name of ['login','home','executive','organization','reuse','individual','open-signup','google-profile']) {
      await page.goto('http://classarit.test/'+name,{waitUntil:'networkidle'});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1), `${name} overflows at ${width}`);
      await page.screenshot({path:path.join(fixtures,`${name}-${width}.png`),fullPage:true});
    }
  }
  await page.goto('http://classarit.test/login');
  assert.equal(await page.locator('#invitation').isVisible(),false);
  await page.locator('.public-nav').getByRole('link',{name:'Request invitation',exact:true}).click();
  assert.equal(await page.locator('#invitation').isVisible(),true);
  assert.equal(await page.locator('#invitation-request-form [name=full_name]').evaluate(el=>el===document.activeElement),true);
  assert.equal(await page.locator('.public-nav [data-signup]').count(),0);
  await page.getByRole('button',{name:'Close invitation request'}).click();
  assert.equal(await page.locator('#invitation').isVisible(),false);
  await page.locator('.public-nav').getByRole('link',{name:'Request invitation',exact:true}).click();
  console.log('Responsive views passed; checking request submission');
  const form=page.locator('#invitation-request-form');
  await form.locator('[name=full_name]').fill('Review Applicant');
  await form.locator('[name=email]').fill('review@example.com');
  await form.locator('[name=usage_type]').selectOption('ORGANIZATION');
  await form.locator('button').click();
  await page.waitForFunction(()=>document.querySelector('#invitation-request-status').textContent.includes('received'));
  assert.equal(requests.find(r=>r.url==='/auth/invitation-requests').payload.usage_type,'ORGANIZATION');
  await page.goto('http://classarit.test/executive');
  console.log('Request form passed; checking executive actions');
  await page.getByRole('button',{name:'Approve',exact:true}).click();
  await page.getByRole('button',{name:'Send invitation',exact:true}).waitFor();
  assert.equal(await page.locator('#request-rows img').count(),0,'Applicant text must be escaped');
  await page.getByRole('button',{name:'Send invitation',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#requests-status').textContent.includes('provider'));
  await page.locator('.setting-toggle').filter({has:page.locator('[data-setting=invite_request_enabled]')}).click();
  console.log('Approval and email controls passed; checking settings');
  await page.waitForFunction(()=>!document.querySelector('[data-setting=invite_request_enabled]').checked);
  await page.locator('#terms-editor [name=body]').fill('Updated review terms');
  await page.getByRole('button',{name:'Save terms',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#terms-editor-status').textContent.includes('Saved'));
  await page.goto('http://classarit.test/reuse');
  assert.equal(await page.locator('[name=owner_aadhaar_number]').count(),0);
  assert.equal(await page.locator('[name=business_gstin]').count(),0);
  assert.equal(await page.locator('[name=workspace_type] option').count(),1);
  await page.goto('http://classarit.test/organization');
  assert.equal(await page.locator('[name=business_gstin]').getAttribute('required'),'');
  await page.goto('http://classarit.test/individual');
  assert.equal(await page.locator('#business-profile-fields').isVisible(),false);
  await page.goto('http://classarit.test/open-signup');
  assert.equal(await page.locator('.public-nav [data-request-invitation]').count(),0);
  await page.locator('.public-nav').getByRole('link',{name:'Sign up',exact:true}).click();
  assert.equal(await page.locator('#signup-panel').isVisible(),true);
  assert.equal(await page.locator('#signup-start-form [name=account_type]').getAttribute('required'),'');
  assert.equal(await page.locator('#signup-start-form [name=account_type] option').count(),3);
  await page.goto('http://classarit.test/google-profile');
  assert.equal(await page.locator('#google-profile-form [name=account_type]').getAttribute('required'),'');
  assert.deepEqual(errors,[]);
  console.log('Passed: 16 responsive views, collapsed invitation form, request submission, required signup account type, review/email controls, invitation toggle, terms save, escaped applicant text, identity reuse and type-specific onboarding.');
} finally { await browser.close(); }
