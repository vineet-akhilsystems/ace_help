"""Ticket assignment rules: sheet rows -> ACE ticket drafts. Mirrors frontend/src/assign.js; both are checked
against tests/fixtures/assign_cases.json, so change them together."""
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from backend.config import RUNTIME

SKIP = '__skip__'
SETTINGS_FILE = RUNTIME / 'assign_settings.json'


class FieldRule(BaseModel):
    model_config = ConfigDict(extra='ignore')
    # fixed = same value every ticket; column = one sheet column; template = {Column} placeholders combined;
    # days = the date column when filled, otherwise today + N days.
    source: Literal['fixed', 'column', 'template', 'days']
    value: str | int | float = ''
    column: str = ''


DEFAULT_FIELDS = {
    'taskType': {'source': 'fixed', 'value': 'Bug'},
    'client': {'source': 'fixed', 'value': 'Augastam (New Product)'},
    'module': {'source': 'column', 'value': 'Module'},
    'keyword': {'source': 'column', 'value': 'Page'},
    'description': {'source': 'template', 'value': '{Description}\nScreenshot: {Screenshot}\n[Assigned by {Assigned By}]'},
    'assignTo': {'source': 'column', 'value': 'Assigned to'},
    'targetDate': {'source': 'days', 'value': 7, 'column': 'TargetDate'},
    'effortDays': {'source': 'fixed', 'value': '7'},
    'priority': {'source': 'fixed', 'value': 'High'},
    'employeeRemarks': {'source': 'column', 'value': 'Employee Remark'},
}
REMARK_EMPTY = '.'  # ACE needs some text in the remarks; "." is what the user puts on other tickets
# The ACE status each sheet status is created with; edited in the tab's Statuses table.
DEFAULT_STATUSES = {'open': 'Open', 'completed': 'Completed', 'done': 'Completed', 'done/build': 'Completed'}
# What a row whose Module / Assign To / Status cell is empty gets: 'skip' = no ticket for that row (the default);
# otherwise module 'pick' = held until a module is picked, assignTo 'fallback' = the fallback assignee,
# status 'table' = the Statuses table's (empty) row.
DEFAULT_WHEN_EMPTY = {'module': 'skip', 'assignTo': 'skip', 'status': 'skip'}
EMPTY_LABELS = {'module': 'Module', 'assignTo': 'Assign To', 'status': 'Status'}


class AssignSettings(BaseModel):
    # extra='ignore': older browser-saved settings may still carry keys such as sheetUrl.
    model_config = ConfigDict(extra='ignore')
    source: Literal['live', 'test'] = 'live'  # live = the OneDrive sheet in ACE_ASSIGN_SHEET_URL
    sheetTab: str = Field(default='Bug List', max_length=120)
    statusColumn: str = Field(default='Status', max_length=120)
    # lower-cased sheet status -> ACE status the ticket is created with, or SKIP; a status not listed gets no ticket
    statuses: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_STATUSES))
    ticketColumn: str = Field(default='ASPL Ticket No', max_length=120)
    fallbackAssignee: str = Field(default='Satender Datt Chamoli', max_length=120)
    whenEmpty: dict[str, Literal['skip', 'pick', 'fallback', 'table']] = Field(default_factory=lambda: dict(DEFAULT_WHEN_EMPTY))
    fields: dict[str, FieldRule] = Field(default_factory=lambda: {k: FieldRule(**v) for k, v in DEFAULT_FIELDS.items()})
    modules: dict[str, str] = Field(default_factory=dict)  # sheet module -> ACE module or SKIP; missing = automatic
    people: dict[str, str] = Field(default_factory=dict)   # lower-cased sheet name -> employee; missing = automatic

    def model_post_init(self, _):
        for key, value in DEFAULT_FIELDS.items():
            self.fields.setdefault(key, FieldRule(**value))
        for key, value in DEFAULT_WHEN_EMPTY.items():
            self.whenEmpty.setdefault(key, value)


def load_settings(path=SETTINGS_FILE):
    return AssignSettings.model_validate_json(path.read_text(encoding='utf-8')) if path.exists() else AssignSettings()


def save_settings(settings, path=SETTINGS_FILE):
    path.write_text(settings.model_dump_json(indent=1), encoding='utf-8')


def words(text):
    return re.sub(r'[^a-z]+', ' ', str(text or '').lower()).split()


def clean(value):
    return str(value if value is not None else '').strip()


def product(word):
    # "Augastam" and its misspellings in the sheet ("Augstam billing").
    return word.startswith('aug')


def match_employee(name, employees):
    """The sheet uses short names ("Naveen", "Karan Verma"); one employee containing every word is a match."""
    raw = clean(name)
    exact = next((e for e in employees if e.lower() == raw.lower()), None)
    if exact:
        return {'name': exact, 'how': 'exact', 'candidates': []}
    want = words(raw)
    candidates = [e for e in employees if want and all(w in words(e) for w in want)]
    if len(candidates) == 1:
        return {'name': candidates[0], 'how': 'auto', 'candidates': candidates}
    return {'name': '', 'how': 'ask', 'candidates': candidates}


def match_module(module, modules):
    """"Billing", "Augstam-billing" -> "Augastam - Billing"; "Admin" -> "Augastam - Administration"; an Augastam module
    wins over a general one with the same name ("Registration")."""
    key = ' '.join(w for w in words(module) if not product(w))
    if not key:
        return ''

    def fits(option):
        tail = ' '.join(w for w in words(option) if not product(w))
        return bool(tail) and (tail.startswith(key) or key == tail or key.startswith(tail + ' '))
    ours = [m for m in modules if any(product(w) for w in words(m)) and fits(m)]
    return ours[0] if ours else next((m for m in modules if fits(m)), '')


def resolve_module(raw, settings, modules):
    value = clean(raw)
    if value in settings.modules:
        return {'module': settings.modules[value], 'how': 'saved'}
    return {'module': match_module(value, modules), 'how': 'auto'}


def resolve_person(raw, settings, employees):
    value = clean(raw)
    if not value:
        return {'name': settings.fallbackAssignee, 'how': 'default', 'candidates': []}
    saved = settings.people.get(value.lower())
    return {'name': saved, 'how': 'saved', 'candidates': []} if saved else match_employee(value, employees)


def fill_template(template, row):
    """A line whose placeholders are all empty is dropped, so a row without a screenshot has no "Screenshot:" line."""
    lines = []
    for line in str(template or '').split('\n'):
        keys = re.findall(r'\{([^}]+)\}', line)
        if keys and all(not clean(row.get(k)) for k in keys):
            continue
        lines.append(re.sub(r'\{([^}]+)\}', lambda m: clean(row.get(m[1])), line))
    return '\n'.join(lines).strip()


def target_date(today, days=7):
    day = (today if isinstance(today, date) else date.fromisoformat(today)) + timedelta(days=int(float(days or 0)))
    return f'{day.isoformat()}T18:00'


def sheet_date(value):
    """Sheet dates arrive as Excel day numbers, "2026-11-06" or "06/11/2026" (day first)."""
    v = clean(value)
    if not v:
        return ''
    if re.fullmatch(r'\d{5}(\.\d+)?', v):
        return f'{(date(1899, 12, 30) + timedelta(days=int(float(v)))).isoformat()}T18:00'
    m = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', v)
    if m:
        return f'{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}T18:00'
    m = re.match(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})', v)
    return f'{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}T18:00' if m else ''


def field_value(rule, row, today):
    if rule is None:
        return ''
    if rule.source == 'column':
        return clean(row.get(str(rule.value)))
    if rule.source == 'template':
        return fill_template(rule.value, row)
    if rule.source == 'days':
        return (rule.column and sheet_date(row.get(rule.column))) or target_date(today, rule.value)
    return clean(rule.value)


def resolve_status(row, settings):
    """The ACE status for this row's sheet status, or SKIP when the Statuses table does not pick it."""
    return settings.statuses.get(clean(row.get(settings.statusColumn)).lower(), SKIP) or SKIP


def is_open_row(row, settings):
    """A row that gets a ticket: no ticket number yet, and its status is picked in the Statuses table."""
    return resolve_status(row, settings) != SKIP and not clean(row.get(settings.ticketColumn))


def empty_status_skipped(row, settings):
    """A row without a ticket number whose Status cell is empty, while the empty rule says no ticket."""
    return (settings.whenEmpty['status'] == 'skip' and not clean(row.get(settings.statusColumn))
            and not clean(row.get(settings.ticketColumn)))


def identity_columns(settings):
    """Columns that say which bug a row is: the ones the description and keyword come from."""
    cols = []
    for key in ('description', 'keyword'):
        rule = settings.fields[key]
        if rule.source == 'column':
            cols.append(str(rule.value))
        elif rule.source == 'template':
            cols += re.findall(r'\{([^}]+)\}', str(rule.value))
    return list(dict.fromkeys(c for c in cols if c))


def fingerprint(row, settings):
    """Stable id of a bug row (its text, not its row number, which moves when people insert rows)."""
    text = '|'.join(' '.join(clean(row.get(c)).split()).lower() for c in identity_columns(settings))
    return hashlib.sha256(text.encode()).hexdigest()[:20]


def check_columns(settings, columns):
    """Cells re-read in the live sheet before a ticket number is written, so a moved row is never overwritten."""
    first = identity_columns(settings)[:1]
    assign = [str(settings.fields['assignTo'].value)] if settings.fields['assignTo'].source == 'column' else []
    return [c for c in dict.fromkeys(first + assign + [settings.statusColumn]) if c in columns]


def sheet_drafts(rows, settings, today, modules, employees):
    """Open rows without a ticket number -> drafts. Rows whose module is set to skip, or whose Module / Assign To /
    Status cell is empty while the empty rule says no ticket, are listed separately with the reason."""
    drafts, skipped = [], []
    for row in rows:
        if empty_status_skipped(row, settings):
            skipped.append({'row': row['_row'], 'reason': 'Status is empty',
                            'description': field_value(settings.fields.get('description'), row, today)})
    open_rows = [r for r in rows if is_open_row(r, settings) and not empty_status_skipped(r, settings)]
    for row in open_rows:
        value = lambda field: field_value(settings.fields.get(field), row, today)  # noqa: E731
        raw_module = value('module')
        sheet_name = value('assignTo')
        empty = [EMPTY_LABELS[f] for f, raw in (('module', raw_module), ('assignTo', sheet_name))
                 if not raw and settings.whenEmpty[f] == 'skip']
        if empty:
            skipped.append({'row': row['_row'], 'reason': ' and '.join(empty) + (' are empty' if len(empty) > 1 else ' is empty'),
                            'description': value('description')})
            continue
        mod = resolve_module(raw_module, settings, modules)
        if mod['module'] == SKIP:
            skipped.append({'row': row['_row'], 'reason': f'Module "{raw_module}" is set to skip',
                            'description': value('description')})
            continue
        person = resolve_person(sheet_name, settings, employees)
        warnings = []
        if not mod['module']:
            warnings.append(f'Module "{raw_module}" has no ACE module yet. Pick one here or in Settings → Modules.')
        elif mod['module'] not in modules:
            warnings.append(f'ACE has no module "{mod["module"]}". Pick one from ACE\'s list.')
        if person['how'] == 'ask':
            warnings.append(f'"{sheet_name}" matches {"more than one employee" if person["candidates"] else "no employee"}. '
                            'Pick who gets this ticket.')
        if person['how'] == 'default':
            warnings.append(f'No one in "{settings.fields["assignTo"].value}", so it goes to {settings.fallbackAssignee}.')
        if person['name'] and person['name'] not in employees:
            warnings.append(f'ACE has no employee "{person["name"]}". Pick one from ACE\'s list.')
        drafts.append({
            'row': row['_row'], 'fingerprint': fingerprint(row, settings), 'pick': True, 'sheetName': sheet_name,
            'assigneeHow': person['how'], 'candidates': person['candidates'], 'warnings': warnings,
            'taskType': value('taskType'), 'client': value('client'), 'module': mod['module'],
            'keyword': value('keyword')[:25], 'description': value('description'), 'assignee': person['name'],
            'targetDate': value('targetDate'), 'effortDays': value('effortDays'), 'priority': value('priority'),
            'status': resolve_status(row, settings), 'employeeRemarks': value('employeeRemarks')[:4000]})
    skipped.sort(key=lambda s: s['row'])
    return {'drafts': drafts, 'skipped': skipped, 'closed': len(rows) - len(open_rows) - sum(
        1 for r in rows if empty_status_skipped(r, settings))}


def held_reasons(draft, modules, employees, statuses=None):
    """Why the automatic run must not create this draft on its own (empty = safe to create)."""
    reasons = [f'{label} is missing' for field, label in (
        ('module', 'Module'), ('assignee', 'Assign to'), ('keyword', 'Keyword'), ('description', 'Description'),
        ('taskType', 'Task Type'), ('client', 'Client Name'), ('targetDate', 'Target Date'),
        ('effortDays', 'Effort in Days'), ('priority', 'Priority'), ('status', 'Status')) if not clean(draft.get(field))]
    if draft.get('module') and draft['module'] not in modules:
        reasons.append(f'module "{draft["module"]}" is not in ACE')
    if draft.get('assignee') and draft['assignee'] not in employees:
        reasons.append(f'"{draft["assignee"]}" is not in ACE\'s Assign To list')
    if statuses and draft.get('status') and draft['status'] not in statuses:
        reasons.append(f'status "{draft["status"]}" is not in ACE')
    return reasons


def task_fields(draft):
    """The TaskDraft fields for one ticket; the client remark (and an empty employee remark) is "."."""
    try:
        effort = float(draft['effortDays'])
    except (TypeError, ValueError):
        effort = 0
    return {'taskType': draft['taskType'], 'priority': draft['priority'], 'client': draft['client'],
            'module': draft['module'], 'frdNature': '', 'status': draft['status'], 'targetDate': draft['targetDate'],
            'effortDays': effort, 'keyword': draft['keyword'], 'description': draft['description'],
            'clientRemarks': REMARK_EMPTY, 'employeeRemarks': clean(draft.get('employeeRemarks')) or REMARK_EMPTY,
            'assignTo': draft['assignee']}


def now_iso():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except ValueError:
        return default


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
