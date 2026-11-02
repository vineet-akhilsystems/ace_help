"""Ticket assignment: ACE tickets for other people from rows of a bug sheet, created by the ACE_ASSIGN_ACCOUNT account.

The only thing ever written to the sheet is the new ticket number, into the ticket column of that row, and only
when that cell is still empty. A ledger of every ticket created keeps a row from ever getting a second ticket.
"""
import asyncio
import csv
import re
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, ValidationError
from backend.app_models import StrictModel
from backend.app_rules import today_ist
from backend.app_session import PortalError
from backend.app_tasks import TaskDraft, check_drafts, load_form, match_new_tickets, option_texts
from backend.app_timesheet import set_widget, settle
from backend.assign_rules import (AssignSettings, check_columns, clean, fingerprint, held_reasons, load_settings,
                                  now_iso, read_json, sheet_drafts, task_fields, write_json)
from backend.config import RUNTIME, setting
from backend.services import xlsx

TEST_SHEET = RUNTIME / 'assign_test_sheet.csv'
# Same columns as the Augastam Front Office "Bug List" sheet.
COLUMNS = ['S.No', 'Module', 'Page', 'Description', 'Screenshot', 'Assigned By', 'Assigned to', 'Status',
           'Employee Remark', 'TargetDate', 'ASPL Ticket No']
TEST_ROWS = [['1', 'Augastam - Registration', 'Registration',
              'TEST ticket from the ACE assistant ticket assignment tab. Please ignore.', '', 'Vineet Kukreti',
              'Vineet Kukreti', 'Open', '', '', '']]
P = '#ctl00_ContentPlaceHolder1_Tasks1_'


class AssignTicket(StrictModel):
    row: int = Field(ge=2, le=100000)  # sheet row number; the header is row 1
    draft: TaskDraft


class AssignRequest(BaseModel):
    tickets: list[AssignTicket] = Field(min_length=1, max_length=30)
    settings: AssignSettings
    save: bool = False


class SheetRequest(BaseModel):
    source: str = Field(default='', pattern='^(live|test|)$')  # empty: the saved setting
    sheetTab: str = Field(default='', max_length=120)


class AutoRequest(StrictModel):
    on: bool


class RunRequest(StrictModel):
    count: int | None = Field(default=None, ge=1, le=1000)  # how many tickets Run now creates; None = every waiting row


class SentTicket(StrictModel):
    ticket: str
    description: str
    assignedTo: str = ''


def ensure_test_sheet(path=TEST_SHEET):
    if not path.exists():
        write_rows(path, COLUMNS, TEST_ROWS)


def write_rows(path, columns, rows):
    # utf-8-sig so Excel opens the file with the right characters.
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def read_sheet(path=TEST_SHEET):
    """Columns and rows keyed by column name; _row is the sheet row number (header = 1)."""
    with path.open(encoding='utf-8-sig', newline='') as stream:
        table = list(csv.reader(stream))
    if not table:
        raise ValueError('The sheet is empty.')
    columns = [c.strip() for c in table[0]]
    rows = [{'_row': n, **{c: (cells[i] if i < len(cells) else '') for i, c in enumerate(columns)}}
            for n, cells in enumerate(table[1:], start=2) if any(cell.strip() for cell in cells)]
    return columns, rows


def write_ticket(path, row, column, ticket):
    """Puts the ticket number into one empty cell; never overwrites a cell that already has a value."""
    with path.open(encoding='utf-8-sig', newline='') as stream:
        table = list(csv.reader(stream))
    columns = [c.strip() for c in table[0]]
    if column not in columns:
        raise ValueError(f'The sheet has no "{column}" column.')
    if not 2 <= row <= len(table):
        raise ValueError(f'Row {row} is not in the sheet.')
    cells, at = table[row - 1], columns.index(column)
    cells += [''] * (len(columns) - len(cells))
    if cells[at].strip():
        raise ValueError(f'Row {row} already has "{cells[at].strip()}" in {column}; nothing was written.')
    cells[at] = ticket
    write_rows(path, table[0], table[1:])


async def sent_tickets(session, days=2):
    """Tickets this account created in the last few days, from ACE's Sent list (never its Select link: it hangs ACE)."""
    async with session.lock:
        page = await session.background('/Tasks/TaskPageN.aspx')
        try:
            return await read_sent(page, days)
        finally:
            await page.close()


async def read_sent(page, days):
    sent = page.locator(P + 'btnPosted')
    if await sent.count() != 1:
        raise PortalError('ACE Sent button not found.')
    await sent.click()
    await settle(page)
    await set_widget(page, 'Tasks1_SendFromDate', (today_ist() - timedelta(days=days)).isoformat(), 'date')
    await set_widget(page, 'Tasks1_SendToDate', today_ist().isoformat(), 'date')
    await page.locator(P + 'btnSearchSend').click()
    await settle(page)
    grid = page.locator(P + 'grvPosted')
    if await grid.count() != 1:
        return []
    found, number = {}, 1
    while number <= 20:
        rows = await grid.locator('tr').evaluate_all(
            "rows => rows.filter(r => r.querySelector('td') && !r.querySelector('th'))"
            ".map(r => Array.from(r.children).map(c => c.innerText.trim()))")
        for cells in rows:
            # Ticket No, Client, Module, AMC DueDate, InSupport, Status, Priority, ASPL Priority, Description, Assigned To…
            if len(cells) >= 10 and re.fullmatch(r'ASPL-\d{5,8}', cells[0]):
                found[cells[0]] = SentTicket(ticket=cells[0], description=cells[8], assignedTo=cells[9])
        link = grid.locator(f'a[href*="Page\\${number + 1}"]')
        if await link.count() == 0:
            break
        await link.click()
        await settle(page)
        number += 1
    return list(found.values())


LEDGER_FILE = RUNTIME / 'assign_ledger.json'
AUTO_FILE = RUNTIME / 'assign_auto.json'
AUTO_DEFAULT = {'on': False, 'since': None, 'baseline': [], 'intervalMinutes': 30, 'lastRun': None, 'nextRun': None,
                'runs': []}
RUN_LIMIT = 30  # tickets per run; more wait for the next run


class AssignService:
    """Reads the sheet, creates tickets as the assignment account, writes their numbers back, and runs on a timer."""

    def __init__(self, session, creator, excel):
        self.session, self.creator, self.excel = session, creator, excel
        self.lock = asyncio.Lock()
        self.running = None  # the run going now: {reason, since, total, current}
        self.stopping = False  # Stop was pressed; the run ends after the ticket in progress
        self.task = None
        self.cache = {}  # source -> (columns, rows) from the last read
        self.ledger_file, self.auto_file, self.test_sheet = LEDGER_FILE, AUTO_FILE, TEST_SHEET

    # ---------- sheet ----------

    async def read(self, settings):
        async with self.lock:
            return await self._read(settings)

    async def _read(self, settings):
        if settings.source == 'test':
            ensure_test_sheet(self.test_sheet)
            names, rows = read_sheet(self.test_sheet)
            columns = [(xlsx.column_letter(i), n) for i, n in enumerate(names) if n]
        else:
            url = setting('ACE_ASSIGN_SHEET_URL')
            if not url:
                raise ValueError('Add the sheet link under Settings → Sheet link first.')
            try:
                data = await self.excel.download(url)
            except Exception as exc:
                raise PortalError(f'Could not download the sheet from OneDrive: {str(exc)[:200]}') from exc
            columns, rows = xlsx.read_sheet(data, settings.sheetTab)
        self.cache[settings.source] = (columns, rows)
        return columns, rows

    # ---------- ledger ----------

    def ledger(self):
        return read_json(self.ledger_file, {})

    def _key(self, settings, row):
        return f'{settings.source}:{fingerprint(row, settings)}'

    # ---------- creating ----------

    async def create(self, request):
        async with self.lock:
            return await self._create(request.tickets, request.settings, request.save)

    async def _create(self, tickets, settings, save, proceed=None):
        columns, rows = self.cache.get(settings.source) or await self._read(settings)
        names = [h for _, h in columns]
        if settings.ticketColumn not in names:
            raise ValueError(f'The sheet has no "{settings.ticketColumn}" column.')
        by_row, ledger = {r['_row']: r for r in rows}, self.ledger()
        for t in tickets:
            row = by_row.get(t.row)
            if row is None:
                raise ValueError(f'Row {t.row} is not in the sheet any more. Read the sheet again.')
            if clean(row.get(settings.ticketColumn)):
                raise ValueError(f'Row {t.row} already has a ticket number; nothing was created.')
            done = ledger.get(self._key(settings, row))
            if save and done:
                raise ValueError(f'Row {t.row} already got {done.get("ticket") or "a ticket"} on {done["at"][:10]}; '
                                 'it is not created again.')
        drafts = [t.draft for t in tickets]
        check_drafts(drafts, load_form())
        known = [s.ticket for s in await sent_tickets(self.session)] if save else []
        result = await self.creator.fill(drafts, save=save, proceed=proceed, close_saved=save)
        if not save:
            return result
        missing = [r for r in result['tasks'] if r['status'] in ('saved', 'unconfirmed') and not r.get('ticket')]
        if missing:
            # ACE clears the form without showing the number, so find each new ticket in this account's Sent list.
            try:
                links = match_new_tickets([drafts[r['index'] - 1].description for r in missing],
                                          await sent_tickets(self.session), known)
                for r, ticket in zip(missing, links):
                    if ticket:
                        r.update(ticket=ticket, status='saved', message=f'Saved in ACE as {ticket}.')
            except PortalError as exc:
                for r in missing:
                    r['message'] += f' Could not read the Sent list: {exc}'
        # Remembered before writing to the sheet, so a failed write can never lead to a second ticket.
        for r in result['tasks']:
            if r['status'] in ('saved', 'unconfirmed'):
                t = tickets[r['index'] - 1]
                ledger[self._key(settings, by_row[t.row])] = {
                    'ticket': r.get('ticket'), 'status': r['status'], 'row': t.row, 'assignee': t.draft.assignTo,
                    'at': now_iso(), 'written': False}
        write_json(self.ledger_file, ledger)
        pending = [(r, tickets[r['index'] - 1].row) for r in result['tasks'] if r.get('ticket')]
        outcome = await self._write_numbers([(row, r['ticket']) for r, row in pending], settings, columns, by_row)
        for (r, row), sheet in zip(pending, outcome):
            r['sheet'] = sheet
        return result

    async def _write_numbers(self, numbers, settings, columns, by_row):
        """[(row, ticket)] -> one message per number; marks the ledger entry written when it is in the sheet."""
        if not numbers:
            return []
        letters = {h: letter for letter, h in columns}
        if settings.source == 'test':
            outcome = []
            for row, ticket in numbers:
                try:
                    write_ticket(self.test_sheet, row, settings.ticketColumn, ticket)
                    outcome.append({'status': 'written', 'detail': ''})
                except (OSError, ValueError) as exc:
                    outcome.append({'status': 'failed', 'detail': str(exc)})
        else:
            checks = check_columns(settings, list(letters))
            writes = [{'cell': f'{letters[settings.ticketColumn]}{row}', 'value': ticket,
                       'checks': {f'{letters[c]}{row}': by_row[row].get(c, '') for c in checks}} for row, ticket in numbers]
            try:
                outcome = await self.excel.write(setting('ACE_ASSIGN_SHEET_URL'), settings.sheetTab, writes)
            except Exception as exc:  # the tickets exist; the ledger keeps their numbers for the next try
                outcome = [{'status': 'failed', 'detail': f'Excel Online: {str(exc)[:150]}'} for _ in writes]
        ledger, messages = self.ledger(), []
        for (row, ticket), o in zip(numbers, outcome):
            if o['status'] in ('written', 'already'):
                entry = ledger.get(self._key(settings, by_row[row]))
                if entry:
                    entry['written'] = True
                messages.append(f'Written to row {row}.')
            else:
                messages.append(f'Not written to row {row}: {o["detail"] or o["status"]}. It will be retried.')
        write_json(self.ledger_file, ledger)
        return messages

    async def _write_pending(self, settings, columns, rows):
        """Ticket numbers created earlier whose sheet write failed: find each row by its text and write again."""
        ledger, by_key = self.ledger(), {self._key(settings, r): r for r in rows}
        numbers = []
        for key, entry in ledger.items():
            row = by_key.get(key)
            if key.startswith(settings.source + ':') and entry.get('ticket') and not entry.get('written') and row:
                if clean(row.get(settings.ticketColumn)):
                    entry['written'] = True
                else:
                    numbers.append((row['_row'], entry['ticket']))
        write_json(self.ledger_file, ledger)
        return await self._write_numbers(numbers, settings, columns, {r['_row']: r for r in rows})

    # ---------- automatic run ----------

    def auto_state(self):
        return {**AUTO_DEFAULT, **read_json(self.auto_file, {})}

    def auto_summary(self):
        state, ledger = self.auto_state(), self.ledger()
        return {**{k: v for k, v in state.items() if k != 'baseline'}, 'baseline': len(state['baseline']),
                'running': self.running, 'stopping': self.stopping,
                'waitingToWrite': sum(1 for e in ledger.values() if e.get('ticket') and not e.get('written')),
                'unconfirmed': sum(1 for e in ledger.values() if e['status'] == 'unconfirmed' and not e.get('ticket'))}

    async def set_auto(self, on):
        async with self.lock:
            state = self.auto_state()
            if on and not state['on']:
                # Rows already waiting when the switch goes on stay for the user; only rows added later run on their own.
                settings = load_settings()
                _, rows = await self._read(settings)
                drafts = sheet_drafts(rows, settings, today_ist(), [], [])['drafts']
                state.update(on=True, since=now_iso(), baseline=[d['fingerprint'] for d in drafts],
                             nextRun=self._after(state['intervalMinutes']))
            elif not on:
                state.update(on=False, nextRun=None)
            write_json(self.auto_file, state)
            return self.auto_summary()

    @staticmethod
    def _after(minutes):
        return (datetime.now().astimezone() + timedelta(minutes=minutes)).isoformat(timespec='seconds')

    def start_run(self, count=None):
        """Run now, in the background so it can be stopped: the first `count` waiting rows in sheet order (all when
        None), including those set aside at switch-on."""
        if self.running or self.lock.locked():
            raise ValueError('A run is already going. Stop it or wait for it to finish.')
        self.running = {'reason': 'manual', 'since': now_iso(), 'total': 0, 'current': 0}
        self.task = asyncio.create_task(self.run_once('manual', everything=True, count=count))
        return self.auto_summary()

    def stop(self):
        if self.running:
            self.stopping = True
        return self.auto_summary()

    def _proceed(self, index):
        if self.stopping:
            return False
        self.running['current'] = index
        return True

    async def run_once(self, reason='scheduled', everything=False, count=None):
        async with self.lock:
            self.running = {'reason': reason, 'since': now_iso(), 'total': 0, 'current': 0}
            record = {'at': now_iso(), 'reason': reason, 'created': [], 'held': [], 'failed': [], 'written': []}
            try:
                await self._run(self.auto_state(), record, everything, count)
            except Exception as exc:  # recorded and shown on the tab; the timer keeps going
                record['error'] = str(exc)[:300] or exc.__class__.__name__
            finally:
                self.running, self.stopping = None, False
            state = self.auto_state()  # the user may have switched it off meanwhile
            state.update(lastRun=record['at'], runs=[record, *state['runs']][:20],
                         nextRun=self._after(state['intervalMinutes']) if state['on'] else None)
            write_json(self.auto_file, state)
            return record

    async def _run(self, state, record, everything=False, count=None):
        """The timer takes only rows added after switch-on; Run now (everything) takes every waiting row, or the first
        `count` of them."""
        settings = load_settings()
        columns, rows = await self._read(settings)
        record['rows'] = len(rows)
        record['written'] = await self._write_pending(settings, columns, rows)
        form = load_form()
        modules, employees = option_texts(form)['module'], form.get('employees', [])
        drafts = sheet_drafts(rows, settings, today_ist(), modules, employees)['drafts']
        baseline, ledger = set(state['baseline']), self.ledger()
        new = [d for d in drafts if (everything or d['fingerprint'] not in baseline)
               and f'{settings.source}:{d["fingerprint"]}' not in ledger]
        record['new'] = len(new)
        ready = []
        for d in new:
            reasons = held_reasons(d, modules, employees, option_texts(form)['status'])
            draft = None
            try:
                draft = TaskDraft(**task_fields(d))
            except ValidationError as exc:
                reasons.append('; '.join(e['msg'] for e in exc.errors())[:200])
            if reasons:
                record['held'].append({'row': d['row'], 'sheetName': d['sheetName'], 'reasons': reasons})
            else:
                ready.append(AssignTicket(row=d['row'], draft=draft))
        limit = count if everything else RUN_LIMIT
        if limit is not None and len(ready) > limit:
            record['left'] = len(ready) - limit  # ready rows kept for the next run
            ready = ready[:limit]
        self.running['total'] = len(ready)
        if not ready or self.stopping:
            record['stopped'] = len(ready) if self.stopping else 0
            return
        result = await self._create(ready, settings, save=True, proceed=self._proceed)
        record['stopped'] = len(result['notStarted'])
        for r in result['tasks']:
            t = ready[r['index'] - 1]
            item = {'row': t.row, 'assignee': t.draft.assignTo, 'ticket': r.get('ticket'), 'message': r['message'],
                    'sheet': r.get('sheet', '')}
            (record['created'] if r['status'] in ('saved', 'unconfirmed') else record['failed']).append(item)

    async def loop(self):
        """Checks every 30 seconds whether a run is due; started with the app."""
        while True:
            await asyncio.sleep(30)
            state = self.auto_state()
            due = state['on'] and state['nextRun'] and datetime.fromisoformat(state['nextRun']) <= datetime.now().astimezone()
            if due:
                await self.run_once()
