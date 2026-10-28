import hashlib
import json
import re
from datetime import datetime, timezone
try:
    from playwright.async_api import Error as PlaywrightError
except ImportError:
    # Browser failures are reported by Session.start(); keep non-browser routes available.
    class PlaywrightError(Exception):
        pass
from backend.app_session import PortalError
from backend.config import RUNTIME
from backend.app_models import DayPlan, Ticket
from backend.app_rules import today_ist

PREFIX = 'ctl00_ContentPlaceHolder1_'
PATH = '/TimeSheet/TimeSheet.aspx?Mpg=P3'
FIELDS = ['client', 'taskName', 'module', 'workplace', 'description', 'start', 'end', 'total']


def normalize(value):
    return ' '.join(value.replace('\xa0', ' ').split())


def normalize_time(value):
    value = normalize(value).upper().replace(' ', '')
    for fmt in ('%H:%M', '%I:%M%p', '%H:%M:%S', '%I:%M:%S%p'):
        try:
            return datetime.strptime(value, fmt).strftime('%H:%M')
        except ValueError:
            pass
    return value


def parse_grid(rows):
    parsed = []
    for cells in rows:
        if len(cells) != 11:
            raise PortalError('ACE grid structure changed. No further rows were added.')
        values = [normalize(c) for c in cells[1:9]]
        if not any(values):
            continue
        record = dict(zip(FIELDS, values))
        record['start'] = normalize_time(record['start'])
        record['end'] = normalize_time(record['end'])
        # ACE inserts a zero-length row (start == end, 00:00) when a ticket is updated.
        # It is not a timesheet entry, so it neither blocks a fill nor counts as filled.
        if record['start'] and record['start'] == record['end'] and record['total'] == '00:00':
            continue
        parsed.append(record)
    return parsed


def expected_rows(plan):
    return [{**{k: normalize(getattr(t, k)) for k in ('client', 'taskName', 'module', 'description', 'start', 'end')},
             'workplace': plan.workplace} for t in plan.tasks]


def prefix_matches(actual, expected):
    return len(actual) <= len(expected) and all(
        all(row.get(k) == value for k, value in target.items())
        for row, target in zip(actual, expected))


async def settle(page):
    await page.wait_for_load_state('networkidle', timeout=20000)
    await page.wait_for_function('''() => {
        const m = window.Sys?.WebForms?.PageRequestManager?.getInstance();
        return !m || !m.get_isInAsyncPostBack();
    }''', timeout=20000)


async def set_widget(page, suffix, value, kind='combo'):
    await page.evaluate('''([id, value, kind]) => {
        const widget = window.$find?.(id);
        if (!widget) throw new Error('Missing ACE widget: ' + id);
        let item = null;
        if (kind === 'combo') {
            item = widget.findItemByText(value);
            if (!item) throw new Error('ACE option unavailable: ' + value);
        }
        // Telerik widgets fire a synchronous ASP.NET postback whose internals read
        // arguments.callee, which is illegal in this strict-mode evaluate frame.
        // Defer the mutation to a macrotask so the postback runs in normal scope.
        setTimeout(() => {
            if (kind === 'combo') { item.select(); }
            else {
                let date;
                if (kind === 'date') { const [y,m,d] = value.split('-').map(Number); date = new Date(y,m-1,d); }
                else { const [h,m] = value.split(':').map(Number); date = new Date(2000,0,1,h,m); }
                widget.set_selectedDate(date);
            }
        }, 0);
    }''', [PREFIX + suffix, value, kind])
    await settle(page)
    actual = await page.evaluate('''([id, kind]) => {
        const w = window.$find?.(id);
        if (!w) return null;
        if (kind === 'combo') return w.get_selectedItem()?.get_text();
        const d = w.get_selectedDate(); if (!d) return null;
        const pad = n => String(n).padStart(2,'0');
        return kind === 'date' ? `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}` : `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }''', [PREFIX + suffix, kind])
    if actual != value:
        raise PortalError(f'ACE did not retain {suffix}. Review the open portal tab.')


async def dom_click(locator):
    # ACE lays the page out in fixed-size Telerik splitter panes that clip without
    # scrolling, so a mouse click on the far-right controls can time out as "outside
    # of the viewport". Click in the DOM instead; deferred so a postback runs outside
    # the strict-mode evaluate frame (see set_widget).
    await locator.evaluate('el => { setTimeout(() => el.click(), 0); }')


async def set_report_date(page, day_str):
    popup = page.locator('#' + PREFIX + 'RadReportDate_popupButton')
    if await popup.count() == 1:
        target_date = datetime.strptime(day_str, '%Y-%m-%d')
        current = await page.evaluate('''id => {
            const d = window.$find?.(id)?.get_selectedDate();
            return d ? [d.getFullYear(), String(d.getMonth()+1).padStart(2,'0'), String(d.getDate()).padStart(2,'0')].join('-') : null;
        }''', PREFIX + 'RadReportDate')
        if current == day_str:
            return

        cal = page.locator('#' + PREFIX + 'RadReportDate_calendar')
        if not await cal.is_visible():  # the button toggles, so never click an open popup shut
            await dom_click(popup)
        await cal.wait_for(state='visible', timeout=5000)

        target_month_str = target_date.strftime('%B %Y')
        title_loc = page.locator('#' + PREFIX + 'RadReportDate_calendar_Title')

        for _ in range(24):
            title = await title_loc.inner_text()
            if target_month_str.lower() in title.lower():
                break
            curr_dt = datetime.strptime(title.strip(), '%B %Y')
            if target_date < curr_dt:
                await dom_click(page.locator('#' + PREFIX + 'RadReportDate_calendar_NP'))
            else:
                await dom_click(page.locator('#' + PREFIX + 'RadReportDate_calendar_NN'))
            await page.wait_for_timeout(200)

        day_pad = f"{target_date.day:02d}"
        cell = cal.locator(f'td[title*="{target_date.strftime("%B")}"][title*=" {day_pad}, "] a').first
        if await cell.count() == 0:
            cell = cal.locator('td:not(.rcOtherMonth) a').filter(has_text=str(target_date.day)).first

        if 'TimeSheet' in page.url:
            async with page.expect_response(lambda r: 'TimeSheet.aspx' in r.url, timeout=15000):
                await dom_click(cell)
        else:
            await dom_click(cell)
        await settle(page)
    else:
        await set_widget(page, 'RadReportDate', day_str, 'date')


class Timesheets:
    def __init__(self, session):
        self.session = session
        self.drafts = {}
        self.shown = {}  # date -> open tab showing a day that already had entries
        self.ticket_cache = None  # None = never loaded; [] = loaded, none assigned
        self.load_cached_tickets()

    def load_cached_tickets(self):
        cache_file = RUNTIME / 'tickets_cache.json'
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding='utf-8'))
                self.ticket_cache = [Ticket.model_validate(t) for t in data]
            except Exception:
                pass

    def save_cached_tickets(self, tickets):
        self.ticket_cache = tickets
        try:
            cache_file = RUNTIME / 'tickets_cache.json'
            with cache_file.open('w', encoding='utf-8') as f:
                json.dump([t.model_dump() for t in tickets], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    async def grid(self, page):
        grid = page.locator('#' + PREFIX + 'gvEntries')
        if await grid.count() != 1:
            raise PortalError('Cannot identify the ACE entry grid. Filling stopped to protect existing entries.')
        headers = await grid.locator('th').all_text_contents()
        if len(headers) != 11 or normalize(headers[1]) != 'Name of Client':
            raise PortalError('Unexpected ACE grid columns. Filling stopped.')
        rows = await grid.locator('tr').evaluate_all(
            "rows => rows.filter(r => r.querySelector('td') && !r.querySelector('th')).map(r => Array.from(r.children).map(c => c.innerText))")
        return parse_grid(rows)

    async def report_date(self, page):
        return await page.evaluate('''id => {
            const d = window.$find?.(id)?.get_selectedDate();
            return d ? [d.getFullYear(), String(d.getMonth()+1).padStart(2,'0'), String(d.getDate()).padStart(2,'0')].join('-') : null;
        }''', PREFIX + 'RadReportDate')

    async def check_date(self, page, day):
        if await self.report_date(page) != day:
            raise PortalError('The ACE report date changed. Filling stopped.')

    def audit(self, plan, event, rows, detail=''):
        record = {'at': datetime.now(timezone.utc).isoformat(), 'event': event,
                  'plan': plan.model_dump(mode='json'), 'observedRows': rows, 'detail': detail,
                  'submitted': False}
        with (RUNTIME / 'audit.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')

    async def fill_one(self, plan):
        plan = DayPlan.model_validate(plan.model_dump())
        day = plan.date.isoformat()
        fingerprint = hashlib.sha256(plan.model_dump_json().encode()).hexdigest()
        expected = expected_rows(plan)
        draft = self.drafts.get(day)
        actual = []
        page = None
        try:
            if draft and (draft['page'].is_closed() or draft['fingerprint'] != fingerprint):
                # The tab was closed or the plan was edited: unsaved draft rows are
                # discarded and the day is rebuilt from a fresh page. Saved rows still
                # show on the fresh page and make the date skip, so nothing duplicates.
                if not draft['page'].is_closed():
                    await draft['page'].close()
                self.drafts.pop(day, None)
                draft = None
            if draft:
                page = draft['page']
                if await self.session.is_login(page):
                    await self.session.login(page)
                    raise PortalError('Session restored. The draft page was interrupted; inspect ACE before retrying.')
                if await self.report_date(page) != day:
                    # The tab left this date (ACE does that after Save, or the user picked
                    # another day). Leave that tab alone and read the day from a fresh
                    # page: saved rows show there and make the date skip.
                    self.drafts.pop(day, None)
                    draft = None
                else:
                    # Rows the user cleared in ACE (its New/Remove buttons) are simply
                    # added again; the prefix check keeps that free of duplicates.
                    actual = await self.grid(page)
                    if not prefix_matches(actual, expected):
                        raise PortalError('The draft grid differs from this plan. No more rows were added; review ACE.')
            if not draft:
                page = await self.session.open(PATH)
                await set_report_date(page, day)
                await self.check_date(page, day)
                actual = await self.grid(page)
                if actual:
                    print(f"[ACE Assistant] [SKIP] Skipping {day}: already has {len(actual)} saved entries in ACE.", flush=True)
                    self.audit(plan, 'skipped_existing', actual)
                    # Leave the day open so the user can see what ACE already holds;
                    # a repeat click replaces this tab instead of stacking another.
                    shown = self.shown.pop(day, None)
                    if shown and not shown.is_closed():
                        await shown.close()
                    self.shown[day] = page
                    await page.bring_to_front()
                    same = len(actual) == len(expected) and prefix_matches(actual, expected)
                    message = (('These are the same rows as this plan, so the day is already saved in ACE. '
                                if same else 'ACE already has saved entries for this date that differ from this plan. ')
                               + 'Nothing was added. The date is open in the ACE browser for you to check.')
                    return {'date': day, 'status': 'skipped', 'message': message, 'gridRows': actual}
                draft = {'page': page, 'fingerprint': fingerprint}
                self.drafts[day] = draft
            tasks_to_add = plan.tasks[len(actual):]
            if tasks_to_add:
                print(f"[ACE Assistant] [ADD] Adding {len(tasks_to_add)} task(s) to ACE grid for {day}...", flush=True)
            for i, task in enumerate(tasks_to_add, start=len(actual) + 1):
                print(f"[ACE Assistant]   -> Row {i}/{len(plan.tasks)}: [{task.start}-{task.end}] {task.description[:55]}...", flush=True)
                await self.check_date(page, day)
                for field, value in [('ddlClientName', task.client), ('ddlTaskName', task.taskName),
                                     ('ddlModule', task.module), ('ddlWorkPlace', plan.workplace)]:
                    await set_widget(page, field, value)
                await page.locator('#' + PREFIX + 'txtTaskDescription').fill(task.description)
                await set_widget(page, 'RadTimeFrom', task.start, 'time')
                await set_widget(page, 'RadTimeEnd', task.end, 'time')
                await self.check_date(page, day)
                self.audit(plan, 'before_add', actual)
                before = len(actual)
                await dom_click(page.locator('#' + PREFIX + 'btnAdd'))
                await settle(page)
                await self.check_date(page, day)
                actual = await self.grid(page)
                if len(actual) != before + 1 or not prefix_matches(actual, expected):
                    raise PortalError('Added row could not be verified exactly. Review ACE before retrying.')
                self.audit(plan, 'row_verified', actual)
            screenshot = f'{day}-{fingerprint[:12]}.png'
            await page.screenshot(path=str(RUNTIME / screenshot), full_page=True)
            await page.bring_to_front()
            try:
                await page.evaluate("() => { window.focus(); }")
            except Exception:
                pass
            self.audit(plan, 'filled_not_saved', actual)
            if not tasks_to_add:
                print(f"[ACE Assistant] [INFO] All {len(actual)} tasks already present in ACE draft grid for {day}.", flush=True)
                message = f'All {len(actual)} rows are already in your ACE browser grid. Switch to ACE and click Save.'
            else:
                print(f"[ACE Assistant] [OK] Successfully filled {len(actual)} task(s) for {day}!", flush=True)
                print(f"[ACE Assistant] [ACTION] Switch to your ACE browser window and click 'Save'.", flush=True)
                message = 'Ready in the ACE browser. Review and click Save yourself. Keep this app running.'
            return {'date': day, 'status': 'filled', 'gridRows': actual,
                    'screenshotUrl': '/screenshots/' + screenshot,
                    'message': message}
        except (PortalError, PlaywrightError) as exc:
            message = str(exc) if isinstance(exc, PortalError) else 'ACE interaction failed. Inspect the open tab; retrying the same plan checks existing draft rows first.'
            self.audit(plan, 'interrupted', actual, message)
            return {'date': day, 'status': 'interrupted', 'gridRows': actual, 'message': message}

    async def fill(self, plans):
        if len({p.date for p in plans}) != len(plans):
            raise ValueError('Duplicate dates in a fill request are not allowed.')
        async with self.session.lock:
            results = []
            for plan in plans:
                result = await self.fill_one(plan)
                results.append(result)
            return {'days': results, 'notStarted': [], 'saved': False}

    async def tickets(self):
        async with self.session.lock:
            page = await self.session.background('/Tasks/TaskPageN.aspx')
            try:
                assigned = page.locator('#ctl00_ContentPlaceHolder1_Tasks1_btnSent')
                if await assigned.count() == 1:
                    await assigned.click()
                    await settle(page)
                # ACE defaults to a 30-day search window, which omits older assigned tickets.
                await set_widget(page, 'Tasks1_AssignedFromDate', '2020-01-01', 'date')
                await set_widget(page, 'Tasks1_AssignedToDate', today_ist().isoformat(), 'date')
                await page.locator('#ctl00_ContentPlaceHolder1_Tasks1_btnSearch').click()
                await settle(page)
                grid = page.locator('#ctl00_ContentPlaceHolder1_Tasks1_gvTasks')
                if await grid.count() != 1:
                    raise PortalError('Assigned-ticket grid not found.')
                tickets_by_id = {}
                current_page = 1
                max_pages = 20

                while current_page <= max_pages:
                    rows = await grid.locator('tr').evaluate_all(
                        "rows => rows.filter(r => r.querySelector('td') && !r.querySelector('th')).map(r => Array.from(r.children).map(c => c.innerText.trim()))")
                    for cells in rows:
                        if len(cells) >= 10 and re.fullmatch(r'ASPL-\d{5,8}', cells[0]):
                            t = Ticket(ticket=cells[0], module=cells[2], taskType=cells[3], status=cells[6], description=cells[9])
                            if t.ticket not in tickets_by_id or t.status.lower() == 'open':
                                tickets_by_id[t.ticket] = t

                    next_page = current_page + 1
                    next_link = grid.locator(f'a[href*="Page\\${next_page}"]')
                    if await next_link.count() == 0:
                        break

                    try:
                        if 'TaskPageN' in page.url:
                            async with page.expect_response(lambda r: 'TaskPageN' in r.url, timeout=15000):
                                await next_link.click()
                        else:
                            await next_link.click()
                        await settle(page)
                        current_page = next_page
                    except Exception:
                        # Retain tickets collected so far if a subsequent page navigation fails
                        break

                tickets = list(tickets_by_id.values())
                self.save_cached_tickets(tickets)
                print(f"[ACE Assistant] [TICKETS] Retrieved {len(tickets)} assigned ticket(s) from ACE and cached locally.", flush=True)
                return tickets
            finally:
                await page.close()
