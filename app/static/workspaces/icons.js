/** Small outline icons shared by workspace actions; labels live on the controls. */
const paths = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  student: '<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M19 8v6m-3-3h6"/>',
  program: '<path d="M12 5c-3-2-7-2-10-1v15c3-1 7-1 10 1 3-2 7-2 10-1V4c-3-1-7-1-10 1Zm0 0v15"/>',
  session: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 11h18m-9 3v4m-2-2h4"/>',
  venue: '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
  teachers: '<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 4v3"/>',
  edit: '<path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14Z"/>',
  close: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6m0-6-6 6"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',
  makeup: '<path d="M3 10a9 9 0 1 1 2 8M3 3v7h7M12 7v5l3 2"/>',
  gear: '<circle cx="12" cy="12" r="4"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2"/>',
  reporting: '<path d="M4 19V5m0 14h17M8 16v-5m5 5V8m5 8v-3"/>',
};
const aliases = {enroll:'student',event:'student',invite:'student',member:'gear',policy:'gear','edit-student':'edit',reschedule:'session',cancel:'close',revoke:'close','end-enrollment':'close',release:'close',complete:'check',attendance:'check',grant:'makeup','disable-series':'close','restore-series':'makeup'};
export function icon(action) {
  return `<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${paths[aliases[action] || action] || paths.plus}</svg>`;
}
