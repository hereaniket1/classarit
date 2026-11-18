import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';

const require = createRequire(process.env.CLASSARIT_PLAYWRIGHT_PACKAGE || import.meta.url);
const { chromium } = require('playwright');
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
const root = process.cwd();
const fixture = path.join(root, '.cache', 'loading-review');
const origin = 'http://classarit.test';
const zone = 'Asia/Kolkata';
const meeting = 'https://example.com/lesson';
const today = '2026-11-16';
const classDay = '2026-11-20';
const taskDay = '2026-11-19';
const classSession = {
  id: 'maths-session', program_id:'maths-course', title: 'Maths', workspace_name: 'Study studio', timezone: zone,
  starts_at: classDay + 'T09:00:00Z', ends_at: classDay + 'T10:00:00Z',
  status: 'SCHEDULED', session_kind: 'CLASS', delivery_mode: 'ONLINE', meeting_url: meeting,
};
const sessions = [
  classSession,
  ...Array.from({ length: 6 }, (_, i) => ({
    ...classSession, id: 'lab-' + i, program_id:'lab-course-' + i, title: i === 0 ? 'Robotics advanced' : 'Lab ' + (i + 1),
    delivery_mode: 'IN_PERSON', meeting_url: null,
  })),
  {
    ...classSession, id: 'completed', title: 'Completed lesson', status: 'COMPLETED',
    starts_at: '2026-11-12T09:00:00Z', ends_at: '2026-11-12T10:00:00Z',
  },
  {
    ...classSession, id: 'december-lesson', title: 'December lesson',
    starts_at: '2026-12-01T09:00:00Z', ends_at: '2026-12-01T10:00:00Z',
  },
];
const documentFiles = {
  '/student': 'student.html',
  '/student/planner': 'student-planner.html',
  '/student/calendar': 'student-calendar.html',
  '/student/classes': 'student-classes.html',
};

try {
  const context = await browser.newContext({ timezoneId: zone, locale: 'en-US' });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  const calendarZone = await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone);
  await page.clock.setFixedTime(new Date(today + 'T12:00:00Z'));
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let enrolled = false;
  let task;
  let rejectEnrollment = true;
  let submittedSearch;
  const calendarMonths = [];

  await context.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.href === meeting) return route.fulfill({ body: 'Online lesson', contentType: 'text/html' });
    if (url.origin !== origin) return route.abort();

    if (url.pathname.startsWith('/api/student/')) {
      const json = (body, status = 200) => route.fulfill({ status, json: body });
      if (url.pathname.endsWith('/planner') && request.method() === 'GET') {
        return json({ groups: task ? [{
          ...task, id:'group-1', count:task.repeat === 'WEEKLY' ? 2 : 1, upcoming_count:1,
        }] : [] });
      }
      if (url.pathname.includes('/planner/series/')) {
        if (request.method() === 'PATCH') {
          task = { ...task, ...request.postDataJSON(), series_id:'group-1' };
          task.starts_at = new Date(task.starts_at + '+05:30').toISOString();
          task.ends_at = new Date(Date.parse(task.starts_at) + task.duration_minutes * 60000).toISOString();
          return json({ count:1 });
        }
        return json({ tasks: [{ ...task, series_id:'group-1' }] });
      }
      if (request.method() === 'POST') {
        assert.ok(request.headers()['x-csrf-token']);
        if (url.pathname.endsWith('/planner/tasks')) {
          task = { ...request.postDataJSON(), id: 'task-1', status: 'ACTIVE' };
          task.starts_at = new Date(task.starts_at + '+05:30').toISOString();
          task.ends_at = new Date(Date.parse(task.starts_at) + task.duration_minutes * 60000).toISOString();
          return json(task, 201);
        }
        assert.equal(url.pathname, '/api/student/classes/course/enroll');
        if (rejectEnrollment) return json({ detail: 'This class is full.' }, 409);
        enrolled = true;
        return json({ id: 'enrollment' });
      }
      if (url.pathname.endsWith('/upcoming')) {
        return json({
          classes: enrolled ? [{ id: 'course', name: 'Maths', workspace_name: 'Study studio', status: 'ACTIVE' }] : [],
          sessions: enrolled ? sessions.filter(session => session.status === 'SCHEDULED') : [],
          tasks: task ? [task] : [],
        });
      }
      if (url.pathname.endsWith('/calendar')) {
        const month = url.searchParams.get('month');
        assert.equal(url.searchParams.get('timezone'), calendarZone);
        calendarMonths.push(month);
        return json({
          month,
          sessions: enrolled ? sessions.filter(session => session.starts_at.startsWith(month)) : [],
          tasks: task?.starts_at.startsWith(month) ? [task] : [],
        });
      }
      if (url.pathname.endsWith('/classes')) {
        if (url.searchParams.get('location') === 'Pune') submittedSearch = url.searchParams;
        return json({
          classes: [{
            id: 'course', name: 'Maths <script>alert(1)</script>', description: 'Practice together',
            workspace_name: 'Study studio', teachers: 'Teacher', default_delivery_mode: 'ONLINE',
            default_duration_minutes: 60, seats_available: 1, enrolled,
          }],
          has_more: false,
        });
      }
      return route.abort();
    }

    const file = url.pathname.startsWith('/static/')
      ? path.join(root, 'app', url.pathname)
      : path.join(fixture, documentFiles[url.pathname]);
    const contentType = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html';
    await route.fulfill({ body: await fs.readFile(file), contentType });
  });

  const assertFits = async () => assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  const day = key => page.locator(`[data-calendar-day="${key}"]`);
  const popup = page.locator('#calendar-popup');
  const closeDay = () => popup.getByRole('button', { name: 'Close day schedule' }).click();
  const control = key => page.locator(`[data-calendar-control="${key}"]`);
  const waitForCalendar = view => page.locator(`.month-calendar.calendar-view-${view}[aria-busy="false"]`).waitFor();

  await page.goto(origin + '/student');
  await page.locator('#student-calendar .agenda-calendar').waitFor();
  assert.equal(await page.locator('#student-calendar [data-calendar-day]').count(), 7);
  assert.equal(await page.locator('#student-calendar .calendar-day.today').getAttribute('data-calendar-day'), today);
  assert.equal(await page.getByText('Upcoming 7 days', { exact: true }).count(), 0);
  assert.equal(await page.getByText('Classes and personal tasks in your local time zone.', { exact: true }).count(), 0);
  assert.equal(await page.locator('[data-action],#workspace-picker,a[href="/workspaces/new"],a[href="/dashboard?overview=1"]').count(), 0);
  await page.locator('#user-dropdown summary').click();
  await page.getByRole('link', { name: 'Edit profile' }).waitFor();
  await page.keyboard.press('Escape');

  await page.getByRole('navigation').getByRole('link', { name: 'Classes', exact: true }).click();
  const enroll = page.getByRole('button', { name: 'Join class', exact: true });
  await enroll.waitFor();
  assert.equal(await page.locator('#student-results script').count(), 0);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await assertFits();
    await page.screenshot({ path: path.join(fixture, `student-discovery-${width}.png`), fullPage: true });
  }
  await page.locator('#student-search [name="q"]').fill('Maths');
  await page.locator('#student-search [name="location"]').fill('Pune');
  await page.locator('#student-search [name="mode"]').selectOption('IN_PERSON');
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await enroll.waitFor();
  assert.equal(submittedSearch.get('location'), 'Pune');
  assert.equal(submittedSearch.get('mode'), 'IN_PERSON');
  await enroll.click();
  await page.getByText('This class is full.').waitFor();
  assert.equal(await enroll.isEnabled(), true);
  rejectEnrollment = false;
  await enroll.click();
  await page.getByRole('button', { name: 'Enrolled', exact: true }).waitFor();

  await page.goto(origin + '/student');
  await day(classDay).waitFor();
  assert.equal(await day(classDay).locator('.day-marker').count(), 5);
  assert.equal(await day(classDay).locator('.day-marker svg').count(), 0);
  assert.equal(await day(classDay).locator('.calendar-label-text').nth(1).textContent(), 'Robotics a…');
  const mathsColor = await day(classDay).locator('.calendar-label').first().getAttribute('style');
  assert.notEqual(await day(classDay).locator('.calendar-label').nth(1).getAttribute('style'), mathsColor);
  await assertFits();
  await page.screenshot({ path: path.join(fixture, 'student-dashboard-390.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await assertFits();
  await page.screenshot({ path: path.join(fixture, 'student-dashboard-1440.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 900 });
  await day(classDay).click();
  await popup.getByText('Maths', { exact: true }).waitFor();
  assert.equal(await popup.locator('.compact-day-session').count(), 7);
  const joinClass = popup.getByRole('link', { name: 'Join class' });
  assert.equal(await joinClass.getAttribute('href'), meeting);
  const openedMeeting = context.waitForEvent('request', request => request.url() === meeting);
  const openedWindow = page.waitForEvent('popup');
  await joinClass.click();
  const meetingWindow = await openedWindow;
  await openedMeeting;
  await meetingWindow.waitForURL(meeting, { waitUntil: 'domcontentloaded' });
  assert.equal(await meetingWindow.evaluate(() => window.opener), null);
  assert.equal(new URL(page.url()).pathname, '/student');
  await meetingWindow.close();

  await page.goto(origin + '/student/planner');
  await page.getByRole('button', { name: 'Add schedule' }).click();
  const scheduler = page.locator('#editor');
  await scheduler.locator('[name="title"]').fill('School project');
  await scheduler.locator('[name="start_date"]').fill(taskDay);
  await scheduler.locator('[name="start_time"]').fill('09:00');
  await scheduler.locator('[name="duration_minutes"]').fill('45');
  assert.equal(await scheduler.locator('input[type="datetime-local"]').count(), 0);
  await scheduler.getByRole('button', { name: 'Save', exact: true }).click();
  await page.getByText('Added to your planner.').waitFor();
  assert.equal(await scheduler.isVisible(), false);
  assert.equal(task.title, 'School project');
  assert.equal(task.duration_minutes, 45);
  assert.equal(task.repeat, 'NONE');
  await page.getByRole('button', { name: 'Add schedule' }).click();
  await scheduler.locator('[name="schedule_type"]').selectOption('weekly');
  await scheduler.locator('[name="title"]').fill('Weekly study');
  await scheduler.locator('[name="start_date"]').fill('2026-11-23');
  await scheduler.locator('[name="start_time"]').fill('17:30');
  await scheduler.locator('[name="repeat_weekdays"]:checked').uncheck({ force: true });
  await scheduler.getByRole('button', { name: 'Save', exact: true }).click();
  await scheduler.getByText('Choose at least one repeat day.').waitFor();
  await scheduler.locator('.weekday-picker label').filter({ hasText: 'Mon' }).click();
  await scheduler.locator('.weekday-picker label').filter({ hasText: 'Thu' }).click();
  await scheduler.locator('[name="repeat_months"]').selectOption('3');
  await page.waitForFunction(() => !document.querySelector('#editor [data-action-spinner]'));
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await assertFits();
    await page.screenshot({ path: path.join(fixture, `student-scheduler-${width}.png`) });
  }
  await scheduler.getByRole('button', { name: 'Save', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('#editor').open);
  assert.deepEqual(task.repeat_weekdays, ['MON', 'THU']);
  assert.equal(task.repeat_months, 3);
  assert.equal(task.repeat, 'WEEKLY');
  // Restore the one-time event for the calendar checks below.
  task = {
    id: 'task-1', title: 'School project', status: 'ACTIVE', timezone: zone,
    starts_at: taskDay + 'T03:30:00Z', ends_at: taskDay + 'T04:15:00Z',
  };
  await page.reload();
  await page.getByRole('button', { name: /School project/ }).click();
  const details = page.locator('#planner-details');
  await details.getByRole('button', { name:'Edit schedule' }).click();
  await scheduler.locator('[name="title"]').fill('School project edited');
  await scheduler.getByRole('button', { name:'Save', exact:true }).click();
  await page.getByRole('button', { name:/School project edited/ }).waitFor();
  await page.getByRole('button', { name:/School project edited/ }).click();
  await details.getByRole('link').first().click();
  await waitForCalendar('month');
  await popup.getByText('School project edited', { exact: true }).waitFor();
  assert.equal(new URL(page.url()).searchParams.get('date'), taskDay);
  await closeDay();

  assert.equal(await page.getByText('Your enrolled classes and personal planner items, month by month.').count(), 0);
  assert.equal(await page.locator('.month-selector').count(), 1);
  assert.equal(await page.locator('.month-calendar .weekday-row span').first().textContent(), 'Mon');
  assert.equal(await page.locator('.month-calendar .calendar-key').count(), 3);
  assert.equal(await day(today).evaluate(el => el.classList.contains('today')), true);
  assert.equal(await day(classDay).locator('.day-marker').count(), 5);
  assert.equal(await day(classDay).locator('.day-markers small').textContent(), '+2 more');
  assert.equal(await day(classDay).locator('.calendar-label').first().getAttribute('style'), mathsColor);
  assert.match(await day(classDay).locator('.calendar-label-time').first().innerText(), /2:30PM\s+to\s+3:30PM/);
  assert.equal(await day(taskDay).locator('.day-marker.kind-session').count(), 1);
  assert.equal(await day('2026-11-12').locator('.day-marker.kind-check').count(), 1);
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await assertFits();
    assert.ok(await day(classDay).locator('.calendar-label').evaluateAll(labels => labels.every(label =>
      label.getBoundingClientRect().right <= label.closest('.calendar-day').getBoundingClientRect().right &&
      label.getBoundingClientRect().bottom <= label.closest('.calendar-day').getBoundingClientRect().bottom)));
    await page.screenshot({ path: path.join(fixture, `student-calendar-${width}.png`), fullPage: true });
  }

  await day('2026-11-12').click();
  await popup.getByText('Completed lesson', { exact: true }).waitFor();
  assert.equal(await popup.getByRole('link', { name: 'Join class' }).count(), 0);
  await closeDay();
  await day(classDay).click();
  await closeDay();
  await control('view-day').click();
  await waitForCalendar('day');
  const positions = await page.locator('.calendar-time-event').evaluateAll(items => items.map(item => {
    const bounds=item.getBoundingClientRect(); return {left:bounds.left,right:bounds.right,height:bounds.height};
  }));
  assert.equal(positions.length,7);
  const lanes = positions.sort((a,b)=>a.left-b.left);
  assert.ok(lanes.every((lane,index)=>Math.abs(lane.height-64)<1 && (index===0 || lane.left>=lanes[index-1].right)));
  await page.locator('[data-calendar-slot="'+classDay+'"][data-start-time="09:30"]').click();
  assert.equal(await scheduler.locator('[name=start_time]').inputValue(),'09:30');
  assert.equal(await scheduler.locator('[name=duration_minutes]').inputValue(),'30');
  await scheduler.getByRole('button',{name:'Cancel',exact:true}).click();
  await page.screenshot({path:path.join(fixture,'student-day-timeline.png'),fullPage:true});
  await control('view-month').click();
  await waitForCalendar('month');
  await day('2026-11-30').click();
  await closeDay();
  await control('view-week').click();
  await waitForCalendar('week');
  assert.equal(await page.locator('[data-calendar-day]').count(), 7);
  assert.equal(await page.locator('[data-calendar-slot]').count(), 336);
  assert.equal(await page.locator('.calendar-hours>span').count(), 24);
  assert.ok(calendarMonths.includes('2026-12'));
  const decemberBlock = page.locator('[data-calendar-event="december-lesson"]');
  assert.equal(await decemberBlock.locator('small').textContent(), '1h');
  assert.ok(await decemberBlock.evaluate(el => Math.abs(el.getBoundingClientRect().height-64)<1));
  await decemberBlock.click();
  await popup.getByText('December lesson', { exact: true }).waitFor();
  await closeDay();
  const selectedSlot = page.locator('[data-calendar-slot="2026-12-01"][data-start-time="16:00"]');
  await selectedSlot.click();
  await scheduler.waitFor();
  assert.equal(await scheduler.locator('[name=start_date]').inputValue(),'2026-12-01');
  assert.equal(await scheduler.locator('[name=start_time]').inputValue(),'16:00');
  assert.equal(await scheduler.locator('[name=duration_minutes]').inputValue(),'30');
  await scheduler.locator('[name=title]').fill('Timeline task');
  await scheduler.getByRole('button',{name:'Save',exact:true}).click();
  await waitForCalendar('week');
  assert.equal(task.duration_minutes,30);
  assert.equal(task.starts_at,'2026-12-01T10:30:00.000Z');
  for (const width of [390,1440]) {
    await page.setViewportSize({width,height:900});
    await assertFits();
    await page.screenshot({path:path.join(fixture,`student-timeline-${width}.png`),fullPage:true});
  }
  await day('2026-12-01').click();
  await popup.getByText('December lesson', { exact: true }).waitFor();
  await closeDay();
  await control('view-day').click();
  await waitForCalendar('day');
  assert.equal(await page.locator('[data-calendar-day]').count(), 1);
  assert.equal(await page.locator('[data-calendar-slot]').count(), 48);
  await control('today').click();
  await waitForCalendar('day');
  assert.equal(await day(today).count(), 1);
  await control('view-month').click();
  await waitForCalendar('month');
  await control('next').click();
  await waitForCalendar('month');
  assert.equal(await page.locator('.month-selector h2').textContent(), 'December 2026');
  await control('previous').click();
  await waitForCalendar('month');
  assert.equal(await page.locator('.month-selector h2').textContent(), 'November 2026');
  assert.deepEqual(errors, []);
  console.log('Passed: student navigation, enrollment, meeting link, planner deep link, and shared calendar views.');
} finally {
  await browser.close();
}
