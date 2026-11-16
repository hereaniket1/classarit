const userMenu = document.querySelector('#user-dropdown');
document.addEventListener('click', event => {
  if (userMenu?.open && !userMenu.contains(event.target)) userMenu.open = false;
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && userMenu?.open) {
    userMenu.open = false;
    userMenu.querySelector('summary').focus();
  }
});

if (!document.body.dataset.workspace) {
  document.querySelector('#workspace-picker')?.addEventListener('change', event => {
    if (event.target.value) window.location.assign(`/workspaces/${encodeURIComponent(event.target.value)}`);
  });
}
