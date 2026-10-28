import asyncio
from datetime import date
from playwright.async_api import async_playwright
from backend.app_models import DayPlan, Task
from backend.app_timesheet import Timesheets


HTML = '''<!doctype html><html><body>
<input id="ctl00_ContentPlaceHolder1_RadReportDate" />
<textarea id="ctl00_ContentPlaceHolder1_txtTaskDescription"></textarea>
<button id="ctl00_ContentPlaceHolder1_btnAdd">Add Row</button>
<button id="ctl00_ContentPlaceHolder1_btnSave">Save</button>
<table id="ctl00_ContentPlaceHolder1_gvEntries"><tr>
<th>Sno</th><th>Name of Client</th><th>Task Name</th><th>Module</th><th>Work Place</th>
<th>Task Description (Max. 500 Character)</th><th>Start Time (HH:MM)</th><th>End Time (HH:MM)</th>
<th>Total Hours</th><th>Edit</th><th>Remove</th></tr>
<tr id="placeholder"><td>1</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>Edit</td><td>Remove</td></tr></table>
<script>
const selected = {}, dates = {};
const prefix = 'ctl00_ContentPlaceHolder1_';
window.$find = id => ({
  findItemByText(text) {
    return ['Augastam (New Product)', 'New Requirement', 'Augastam ai', 'Office', 'Home'].includes(text)
      ? {select(){selected[id]=text;}} : null;
  },
  get_selectedItem(){return selected[id] ? {get_text(){return selected[id];}} : null;},
  set_selectedDate(date){dates[id]=date;},
  get_selectedDate(){return dates[id] || null;}
});
document.getElementById(prefix+'btnAdd').onclick = () => {
  document.getElementById('placeholder')?.remove();
  const time = suffix => {const d=dates[prefix+suffix]; return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;};
  const row = document.createElement('tr');
  const cells = [String(document.querySelectorAll('#'+prefix+'gvEntries tr').length),
    selected[prefix+'ddlClientName'], selected[prefix+'ddlTaskName'], selected[prefix+'ddlModule'],
    selected[prefix+'ddlWorkPlace'], document.getElementById(prefix+'txtTaskDescription').value,
    time('RadTimeFrom'), time('RadTimeEnd'), '04:45', 'Edit', 'Remove'];
  cells.forEach(value => {const cell=document.createElement('td');cell.textContent=value;row.appendChild(cell);});
  document.getElementById(prefix+'gvEntries').appendChild(row);
};
</script></body></html>'''


class FakeSession:
    def __init__(self, page):
        self.page = page
        self.lock = asyncio.Lock()

    async def open(self, path):
        return self.page

    async def background(self, path):
        return self.page

    async def is_login(self, page):
        return False


def sample():
    return DayPlan(date=date(2026, 9, 23), workplace='Office', totalHours='09:15',
                   tasks=[Task(description='First task.', start='09:45', end='14:30'),
                   Task(description='Second task.', start='14:30', end='19:00')])


async def run_fixture(tmp_path, monkeypatch):
    import backend.app_timesheet as module
    monkeypatch.setattr(module, 'RUNTIME', tmp_path)
    async with async_playwright() as driver:
        browser = await driver.chromium.launch()
        page = await browser.new_page()
        await page.set_content(HTML)
        portal = Timesheets(FakeSession(page))
        plan = sample()
        first = await portal.fill([plan])
        assert first['days'][0]['status'] == 'filled'
        assert len(first['days'][0]['gridRows']) == 2
        assert await page.locator('#ctl00_ContentPlaceHolder1_btnSave').count() == 1
        again = await portal.fill([plan])
        assert again['days'][0]['status'] == 'filled'
        assert len(await portal.grid(page)) == 2
        assert (tmp_path / 'audit.jsonl').is_file()
        assert list(tmp_path.glob('*.png'))
        await browser.close()


def test_fill_and_retry_do_not_duplicate_rows(tmp_path, monkeypatch):
    asyncio.run(run_fixture(tmp_path, monkeypatch))


async def run_existing(tmp_path, monkeypatch):
    import backend.app_timesheet as module
    monkeypatch.setattr(module, 'RUNTIME', tmp_path)
    async with async_playwright() as driver:
        browser = await driver.chromium.launch()
        session = TabSession(browser)
        fresh = session.open

        async def open_saved_day(path):
            page = await fresh(path)
            await page.evaluate('''() => {
                const row=document.querySelector('#placeholder');
                row.children[1].textContent='Existing client';
            }''')
            return page

        session.open = open_saved_day
        portal = Timesheets(session)
        result = await portal.fill([sample()])
        assert result['days'][0]['status'] == 'skipped'
        assert len(result['days'][0]['gridRows']) == 1
        # The day stays open for the user to check; a repeat click swaps the tab.
        assert not session.opened[0].is_closed() and 'differ' in result['days'][0]['message']
        again = await portal.fill([sample()])
        assert again['days'][0]['status'] == 'skipped'
        assert session.opened[0].is_closed() and not session.opened[1].is_closed()
        await browser.close()


def test_existing_entries_are_skipped(tmp_path, monkeypatch):
    asyncio.run(run_existing(tmp_path, monkeypatch))


async def run_partial(tmp_path, monkeypatch):
    import backend.app_timesheet as module
    monkeypatch.setattr(module, 'RUNTIME', tmp_path)
    original = module.set_widget
    failure = {'raised': False}

    async def fail_once(page, suffix, value, kind='combo'):
        if suffix == 'ddlClientName' and not failure['raised'] and await page.locator(
                '#placeholder').count() == 0:
            failure['raised'] = True
            raise module.PortalError('Injected interruption after first row.')
        return await original(page, suffix, value, kind)

    monkeypatch.setattr(module, 'set_widget', fail_once)
    async with async_playwright() as driver:
        browser = await driver.chromium.launch()
        page = await browser.new_page()
        await page.set_content(HTML)
        portal = Timesheets(FakeSession(page))
        first = await portal.fill([sample()])
        assert first['days'][0]['status'] == 'interrupted'
        assert len(await portal.grid(page)) == 1
        second = await portal.fill([sample()])
        assert second['days'][0]['status'] == 'filled'
        assert len(await portal.grid(page)) == 2
        await browser.close()


def test_partial_draft_resumes_without_duplicates(tmp_path, monkeypatch):
    asyncio.run(run_partial(tmp_path, monkeypatch))


class TabSession(FakeSession):
    """Opens a fresh tab per call, like the real Session."""
    def __init__(self, browser):
        super().__init__(None)
        self.browser = browser
        self.opened = []

    async def open(self, path):
        page = await self.browser.new_page()
        await page.set_content(HTML)
        self.opened.append(page)
        return page


async def run_rebuild(tmp_path, monkeypatch):
    import backend.app_timesheet as module
    monkeypatch.setattr(module, 'RUNTIME', tmp_path)
    async with async_playwright() as driver:
        browser = await driver.chromium.launch()
        session = TabSession(browser)
        portal = Timesheets(session)
        first = await portal.fill([sample()])
        assert first['days'][0]['status'] == 'filled'
        # User closes the unsaved draft tab: retry rebuilds instead of blocking.
        await session.opened[0].close()
        again = await portal.fill([sample()])
        assert again['days'][0]['status'] == 'filled', again
        assert len(session.opened) == 2 and len(again['days'][0]['gridRows']) == 2
        # Same plan again reuses the open draft: no extra tab, no duplicate rows.
        same = await portal.fill([sample()])
        assert same['days'][0]['status'] == 'filled' and len(session.opened) == 2
        assert len(await portal.grid(session.opened[1])) == 2
        # Edited plan replaces the old unsaved draft tab.
        edited = sample()
        edited.tasks[0].description = 'Edited first task.'
        changed = await portal.fill([edited])
        assert changed['days'][0]['status'] == 'filled', changed
        assert session.opened[1].is_closed() and len(session.opened) == 3
        assert changed['days'][0]['gridRows'][0]['description'] == 'Edited first task.'
        await browser.close()


def test_closed_or_edited_draft_is_rebuilt(tmp_path, monkeypatch):
    asyncio.run(run_rebuild(tmp_path, monkeypatch))


async def run_stale_draft(tmp_path, monkeypatch):
    import backend.app_timesheet as module
    monkeypatch.setattr(module, 'RUNTIME', tmp_path)
    async with async_playwright() as driver:
        browser = await driver.chromium.launch()
        session = TabSession(browser)
        portal = Timesheets(session)
        assert (await portal.fill([sample()]))['days'][0]['status'] == 'filled'
        draft = session.opened[0]
        # ACE's "New" button empties the unsaved grid but keeps the date: refill the same tab.
        await draft.evaluate('''() => document.querySelectorAll(
            '#ctl00_ContentPlaceHolder1_gvEntries tr').forEach(r => r.querySelector('td') && r.remove())''')
        cleared = await portal.fill([sample()])
        assert cleared['days'][0]['status'] == 'filled', cleared
        assert len(session.opened) == 1 and len(await portal.grid(draft)) == 2
        # After Save, ACE moves the tab to another date: read the day from a fresh page.
        await draft.evaluate("() => $find('ctl00_ContentPlaceHolder1_RadReportDate').set_selectedDate(new Date(2000, 0, 1))")
        moved = await portal.fill([sample()])
        assert moved['days'][0]['status'] == 'filled', moved
        assert len(session.opened) == 2 and not draft.is_closed()
        assert len(await portal.grid(draft)) == 2 and len(await portal.grid(session.opened[1])) == 2
        await browser.close()


def test_cleared_or_moved_draft_recovers(tmp_path, monkeypatch):
    asyncio.run(run_stale_draft(tmp_path, monkeypatch))


def test_interrupted_day_does_not_block_later_days(tmp_path, monkeypatch):
    import backend.app_timesheet as module
    monkeypatch.setattr(module, 'RUNTIME', tmp_path)
    portal = Timesheets(FakeSession(None))
    plans = [sample().model_copy(update={'date': date(2026, 9, day)}) for day in (2, 3)]
    attempted = []

    async def fill_one(plan):
        attempted.append(plan.date)
        return {'date': plan.date.isoformat(),
                'status': 'interrupted' if plan.date.day == 2 else 'filled'}

    portal.fill_one = fill_one
    result = asyncio.run(portal.fill(plans))
    assert attempted == [plan.date for plan in plans]
    assert [day['status'] for day in result['days']] == ['interrupted', 'filled']
    assert result['notStarted'] == []


TICKETS_HTML = '''<!doctype html><html><body>
<input type="submit" id="ctl00_ContentPlaceHolder1_Tasks1_btnSent" value="Assigned" />
<input type="text" id="ctl00_ContentPlaceHolder1_Tasks1_AssignedFromDate" />
<input type="text" id="ctl00_ContentPlaceHolder1_Tasks1_AssignedToDate" />
<input type="submit" id="ctl00_ContentPlaceHolder1_Tasks1_btnSearch" value="Search" />
<table id="ctl00_ContentPlaceHolder1_Tasks1_gvTasks">
  <tr>
    <th>Ticket No</th><th>Client Name</th><th>Module Name</th><th>Task Type</th>
    <th>AMC DueDate</th><th>InSupport</th><th>Status</th><th>Priority</th>
    <th>ASPL Priority</th><th>Task Description</th><th>Assigned By</th>
  </tr>
  <tr>
    <td>ASPL-169999</td><td>Augastam (New Product)</td><td>Augastam ai</td><td>Bug</td>
    <td></td><td></td><td>Open</td><td>High</td><td></td><td>First task description</td><td>User</td>
  </tr>
  <tr>
    <td>ASPL-168271</td><td>Augastam (New Product)</td><td>Augastam ai</td><td>Change/Enhancement</td>
    <td></td><td></td><td>Working</td><td>Medium</td><td></td><td>Second task description</td><td>User</td>
  </tr>
  <tr>
    <td><span>1</span></td><td><a id="page2link" href="javascript:__doPostBack('ctl00$ContentPlaceHolder1$Tasks1$gvTasks','Page$2')">2</a></td>
  </tr>
</table>
<script>
const dates = {};
window.$find = id => ({
  set_selectedDate(d){ dates[id] = d; },
  get_selectedDate(){ return dates[id] || null; }
});
document.getElementById('page2link').onclick = e => {
  e.preventDefault();
  const table = document.getElementById('ctl00_ContentPlaceHolder1_Tasks1_gvTasks');
  table.innerHTML = `
    <tr>
      <th>Ticket No</th><th>Client Name</th><th>Module Name</th><th>Task Type</th>
      <th>AMC DueDate</th><th>InSupport</th><th>Status</th><th>Priority</th>
      <th>ASPL Priority</th><th>Task Description</th><th>Assigned By</th>
    </tr>
    <tr>
      <td>ASPL-168271</td><td>Augastam (New Product)</td><td>Augastam ai</td><td>Change/Enhancement</td>
      <td></td><td></td><td>Completed</td><td>Medium</td><td></td><td>Second task completed</td><td>User</td>
    </tr>
    <tr>
      <td>ASPL-166971</td><td>Augastam (New Product)</td><td>Augastam ai</td><td>New Requirement</td>
      <td></td><td></td><td>Open</td><td>High</td><td></td><td>Third task description</td><td>User</td>
    </tr>
    <tr>
      <td><a href="javascript:__doPostBack('ctl00$ContentPlaceHolder1$Tasks1$gvTasks','Page$1')">1</a></td><td><span>2</span></td>
    </tr>
  `;
};
</script></body></html>'''


async def run_tickets_pagination(monkeypatch):
    import backend.app_timesheet as module
    async with async_playwright() as driver:
        browser = await driver.chromium.launch()
        page = await browser.new_page()
        # Route TaskPageN.aspx to avoid real network wait
        await page.route('**/TaskPageN.aspx', lambda route: route.fulfill(status=200, body='OK'))
        await page.set_content(TICKETS_HTML)
        portal = Timesheets(FakeSession(page))
        tickets = await portal.tickets()
        assert len(tickets) == 3
        ticket_map = {t.ticket: t for t in tickets}
        assert 'ASPL-169999' in ticket_map
        assert 'ASPL-168271' in ticket_map
        assert 'ASPL-166971' in ticket_map
        assert ticket_map['ASPL-169999'].status == 'Open'
        assert ticket_map['ASPL-166971'].status == 'Open'
        # Deduplicated ASPL-168271 should be present
        assert ticket_map['ASPL-168271'].ticket == 'ASPL-168271'
        assert portal.ticket_cache == tickets
        await browser.close()


def test_tickets_pagination(monkeypatch):
    asyncio.run(run_tickets_pagination(monkeypatch))


async def run_background_reuse():
    from backend.app_session import Session
    async with async_playwright() as driver:
        browser = await driver.chromium.launch()
        session = Session()
        session.context = await browser.new_context()
        session.reader, session.reader_context = browser, await browser.new_context()
        session.base = 'about:'
        draft = await session.context.new_page()
        first = await session.background('blank')
        second = await session.background('blank')
        third = await session.background('blank')
        assert first is second is third and session.reader_context.pages == [first]
        # The window the user reviews keeps only the draft tab.
        assert session.context.pages == [draft]
        await browser.close()


def test_status_polling_stays_out_of_the_visible_window():
    asyncio.run(run_background_reuse())
