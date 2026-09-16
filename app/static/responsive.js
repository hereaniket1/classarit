/** Small-screen navigation enhancement; navigation remains visible without JavaScript. */
for (const sidebar of document.querySelectorAll('.workspace-sidebar, .sidebar')) {
  const button=document.createElement('button');
  button.type='button';button.className='nav-toggle';
  button.setAttribute('aria-label','Open navigation');button.setAttribute('aria-expanded','false');
  button.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg><span>Menu</span>';
  const nav=sidebar.querySelector('nav');
  if(nav){nav.id=nav.id||'main-navigation';button.setAttribute('aria-controls',nav.id);}
  const setOpen=open=>{sidebar.classList.toggle('mobile-nav-open',open);button.setAttribute('aria-expanded',String(open));button.setAttribute('aria-label',open?'Close navigation':'Open navigation');};
  button.addEventListener('click',()=>setOpen(!sidebar.classList.contains('mobile-nav-open')));
  sidebar.addEventListener('click',event=>{if(event.target.closest('[data-tab], [data-section]')&&window.matchMedia('(max-width: 800px)').matches){setOpen(false);button.focus();}});
  sidebar.addEventListener('keydown',event=>{if(event.key==='Escape'){setOpen(false);button.focus();}});
  sidebar.append(button);sidebar.classList.add('nav-ready');
}
// Keyboard users can focus and horizontally scroll wide data tables independently.
for(const container of document.querySelectorAll('.table-responsive,.table-scroll')){
  container.tabIndex=0;container.setAttribute('role','region');container.setAttribute('aria-label','Scrollable table');
}
