import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const require=createRequire(process.env.CLASSARIT_PLAYWRIGHT_PACKAGE||import.meta.url);
const {chromium}=require('playwright');
const browser=await chromium.launch({headless:true,channel:'chrome'});
const loading=await fs.readFile('app/static/loading.js','utf8');
const profile=await fs.readFile('app/static/profile.js','utf8');
const errors=[];
try {
 const page=await browser.newPage();
 page.on('pageerror', error=>errors.push(error.message));
 await page.route('http://loading.test/**', route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html><body><main id="main"><a id="link" href="/next">Next</a><a id="hash" href="#">Section</a><form id="form"><button>Save</button></form><form id="new-tab" target="_blank"><button>Other tab</button></form><div id="notice"></div><section id="email-verification-card"><button id="send-profile-otp">Send code</button><form id="profile-otp-form" hidden><input name="challenge_id"><input name="code"></form></section></main><aside id="already-inert" inert>Restricted</aside></body></html>`}));
 await page.goto('http://loading.test/');
 await page.clock.install();
 // Deterministic transport, including a response whose JSON body never finishes.
 await page.evaluate(()=>{
   window.fetch = async (input, init={}) => {
     const path=String(input);
     if(path.includes('hanging')) return new Promise((resolve,reject)=>init.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))));
     if(path.includes('body-stall')) {
       const stream=new ReadableStream({start(controller){init.signal.addEventListener('abort',()=>controller.error(new DOMException('Aborted','AbortError')));}});
       return new Response(stream,{headers:{'content-type':'application/json'}});
     }
     if(path.includes('offline')) throw new TypeError('Failed to fetch');
     if(path.includes('unavailable')) return new Response('Unavailable',{status:503});
     return new Response(JSON.stringify({ok:true,challenge_id:'test',email:'test@example.com'}),{headers:{'content-type':'application/json'}});
   };
 });
 await page.addScriptTag({content:loading});
 await page.addScriptTag({content:profile});
 // Handlers registered AFTER the loading module must be able to cancel navigation.
 await page.evaluate(()=>{
   document.addEventListener('click',event=>{if(event.target.closest('#link')) event.preventDefault();});
   document.addEventListener('submit',event=>event.preventDefault());
 });
 await page.locator('#link').click();
 await page.locator('#form button').click();
 await page.clock.fastForward(5);
 assert.equal(await page.locator('.global-page-loader').count(),0);
 await page.locator('#hash').click();
 assert.equal(await page.locator('.global-page-loader').count(),0);
 await page.locator('#send-profile-otp').click();
 await page.waitForFunction(()=>!document.querySelector('#profile-otp-form').hidden);
 assert.equal(await page.locator('#send-profile-otp').isHidden(),true);
 assert.equal(await page.locator('#email-verification-card').getAttribute('aria-busy'),'false');
 // A spinner's delayed cleanup must not remove a newer operation on the same control.
 await page.evaluate(()=>{
   const control=document.querySelector('#form button');
   window.ClassaritLoading.actionBegin(control);
   window.ClassaritLoading.actionEnd(control);
   window.ClassaritLoading.actionBegin(control);
 });
 await page.clock.fastForward(300);
 assert.equal(await page.locator('#form button').getAttribute('aria-busy'),'true');
 await page.evaluate(()=>window.ClassaritLoading.actionEnd(document.querySelector('#form button')));
 await page.clock.fastForward(300);
 assert.equal(await page.locator('#form button [data-action-spinner]').count(),0);
 // Explicit navigation fallback restores the page but respects originally inert areas.
 await page.evaluate(()=>window.ClassaritLoading.transition('test'));
 assert.equal(await page.locator('#main').evaluate(el=>el.inert),true);
 await page.clock.fastForward(15010);
 assert.equal(await page.locator('.global-page-loader').count(),0);
 assert.equal(await page.locator('#main').evaluate(el=>el.inert),false);
 assert.equal(await page.locator('#already-inert').evaluate(el=>el.inert),true);
 for(const path of ['hanging','body-stall']) {
   await page.evaluate(path=>{
     window.failure=null;
     window.ClassaritLoading.lockPage('Saving');
     window.pending=fetch('/api/'+path,{method:'POST'}).catch(e=>window.failure=e.message).finally(()=>window.ClassaritLoading.unlockPage());
   },path);
   await page.clock.fastForward(45010);
   await page.waitForFunction(()=>window.failure!==null);
   assert.match(await page.evaluate(()=>window.failure),/timed out.*Check whether your change was saved/);
   assert.equal(await page.locator('.global-page-loader').count(),0);
   assert.equal(await page.locator('#main').evaluate(el=>el.inert),false);
 }
 assert.match(await page.evaluate(()=>fetch('/api/offline').catch(e=>e.message)),/connection was interrupted/);
 assert.match(await page.evaluate(()=>fetch('/api/unavailable').catch(e=>e.message)),/temporarily unavailable/);
 // An interrupted handler cannot leave an operation overlay forever.
 await page.evaluate(()=>window.ClassaritLoading.lockPage('Interrupted action'));
 await page.clock.fastForward(60010);
 assert.equal(await page.locator('.global-page-loader').count(),0);
 await page.evaluate(()=>document.querySelector('#link').id='real-link');
 await page.locator('#real-link').click();
 await page.waitForURL('http://loading.test/next');
 assert.deepEqual(errors,[]);
 console.log('Passed: cancelled delegated navigation/forms, hash links, profile OTP success, navigation recovery, request and body timeouts, offline/503 failures, inert restoration and interrupted-operation recovery.');
} finally { await browser.close(); }
