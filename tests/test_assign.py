import asyncio
import pytest
from fastapi.testclient import TestClient
from backend import app_assign, main
from backend.app_assign import (COLUMNS, AssignRequest, AssignService, AssignTicket, SentTicket, ensure_test_sheet,
                                read_sheet, write_ticket)
from backend.app_session import Session
from backend.app_tasks import TaskCreator, TaskDraft, check_drafts
from backend.assign_rules import AssignSettings, read_json, sheet_drafts, task_fields
from tests.test_assign_rules import CASES, bug, make_xlsx

HEADERS = {'X-ACE-Client': '1'}
FORM = {'options': {'task_type': [{'text': 'Bug'}], 'priority': [{'text': 'High'}], 'client_name': [{'text': 'Augastam (New Product)'}],
                    'module': [{'text': m} for m in CASES['modules']], 'frd_nature': [{'text': 'Low'}],
                    'task_status': [{'text': 'Open'}, {'text': 'Completed'}]},
        'employees': CASES['employees']}
DRAFT = dict(taskType='Bug', priority='High', client='Augastam (New Product)', module='Augastam - Registration', status='Open',
             targetDate='2026-11-06T18:00', effortDays=7, keyword='Registration', description='Mobile length check\n[Assigned by Pooja]',
             clientRemarks='.', employeeRemarks='.', assignTo='Vineet Kukreti')


# ---------- the local test copy ----------

def test_test_sheet_has_the_bug_list_columns_and_one_open_row(tmp_path):
    path = tmp_path / 'sheet.csv'
    ensure_test_sheet(path)
    columns, rows = read_sheet(path)
    assert columns == COLUMNS
    assert [(r['_row'], r['Status'], r['Assigned to'], r['ASPL Ticket No']) for r in rows] == [(2, 'Open', 'Vineet Kukreti', '')]


def test_ticket_number_goes_only_into_an_empty_ticket_cell(tmp_path):
    path = tmp_path / 'sheet.csv'
    ensure_test_sheet(path)
    before = read_sheet(path)[1][0]
    write_ticket(path, 2, 'ASPL Ticket No', 'ASPL-190001')
    after = read_sheet(path)[1][0]
    assert after['ASPL Ticket No'] == 'ASPL-190001'
    assert {k: v for k, v in after.items() if k != 'ASPL Ticket No'} == {k: v for k, v in before.items() if k != 'ASPL Ticket No'}
    with pytest.raises(ValueError, match='already has'):
        write_ticket(path, 2, 'ASPL Ticket No', 'ASPL-190002')
    with pytest.raises(ValueError, match='no "Ticket" column'):
        write_ticket(path, 2, 'Ticket', 'ASPL-190002')


# ---------- ACE account ----------

def test_each_ticket_can_name_its_own_assignee():
    creator = TaskCreator(session=None)
    assert creator.assignee_for(TaskDraft(**DRAFT)) == 'Vineet Kukreti'
    assert creator.assignee_for(TaskDraft(**{**DRAFT, 'assignTo': ''})) == creator.assignee
    check_drafts([TaskDraft(**{**DRAFT, 'assignTo': 'Gaurav Bagouli'})], FORM)
    with pytest.raises(ValueError, match='Assign To'):
        check_drafts([TaskDraft(**{**DRAFT, 'assignTo': 'Nobody'})], FORM)


def test_agent_account_keeps_its_own_login():
    mine, agent = Session(), Session('ACE_AGENT', 'storage_state_agent.json')
    assert (mine.account, mine.state_file.name) == ('ACE', 'storage_state.json')
    assert (agent.account, agent.state_file.name) == ('ACE_AGENT', 'storage_state_agent.json')
    # main keys the agent's saved login by username, so switching accounts signs in fresh.
    assert main.agent_session.state_file.name.startswith('storage_state_agent_')


def test_other_accounts_logins_are_hidden_from_scans():
    from backend.services.safe_fs import is_blocked_name
    assert is_blocked_name('storage_state_agent_satender_d.json')
    assert not is_blocked_name('storage_notes.json')


# ---------- the service, with ACE and Excel Online faked ----------

class FakeExcel:
    def __init__(self, rows):
        self.data, self.writes, self.fail = make_xlsx(rows), [], False

    async def download(self, url):
        return self.data

    async def write(self, url, tab, writes):
        self.writes.append((tab, writes))
        if self.fail:
            raise RuntimeError('offline')
        return [{'cell': w['cell'], 'status': 'written', 'detail': ''} for w in writes]


class FakeCreator:
    """Saves every draft; like ACE it shows no number, which then appears in the Sent list."""
    def __init__(self):
        self.calls, self.sent, self.next = [], [SentTicket(ticket='ASPL-100000', description='old')], 190001

    async def fill(self, drafts, save=False, proceed=None, close_saved=False):
        self.calls.append((drafts, save))
        tasks = []
        for i, d in enumerate(drafts, start=1):
            if proceed and not proceed(i):
                return {'tasks': tasks, 'notStarted': list(range(i, len(drafts) + 1)), 'saved': bool(tasks)}
            if save:
                self.sent.append(SentTicket(ticket=f'ASPL-{self.next}', description=d.description, assignedTo=d.assignTo))
                self.next += 1
            tasks.append({'index': i, 'keyword': d.keyword, 'status': 'saved' if save else 'filled', 'ticket': None,
                          'message': 'Saved in ACE.' if save else 'Filled.'})
        return {'tasks': tasks, 'notStarted': [], 'saved': save}


HEADER = (1, COLUMNS)


@pytest.fixture
def service(tmp_path, monkeypatch):
    creator = FakeCreator()
    svc = AssignService(session=None, creator=creator, excel=FakeExcel([HEADER, (2, bug())]))
    svc.ledger_file, svc.auto_file, svc.test_sheet = tmp_path / 'ledger.json', tmp_path / 'auto.json', tmp_path / 'sheet.csv'

    async def sent(session):
        return list(creator.sent)
    monkeypatch.setattr(app_assign, 'sent_tickets', sent)
    monkeypatch.setattr(app_assign, 'load_form', lambda: FORM)
    monkeypatch.setattr(app_assign, 'load_settings', lambda: AssignSettings())
    monkeypatch.setenv('ACE_ASSIGN_SHEET_URL', 'https://onedrive.live.com/x')
    return svc


def ticket_for(svc, row_number):
    _, rows = asyncio.run(svc.read(AssignSettings()))
    draft = next(d for d in sheet_drafts(rows, AssignSettings(), '2026-10-30', CASES['modules'], CASES['employees'])['drafts']
                 if d['row'] == row_number)
    return AssignTicket(row=row_number, draft=TaskDraft(**task_fields(draft)))


def test_live_create_checks_the_row_and_writes_the_number(service):
    result = asyncio.run(service.create(AssignRequest(tickets=[ticket_for(service, 2)], settings=AssignSettings(), save=True)))
    task = result['tasks'][0]
    assert (task['ticket'], task['sheet']) == ('ASPL-190001', 'Written to row 2.')
    assert service.excel.writes == [('Bug List', [{'cell': 'K2', 'value': 'ASPL-190001', 'checks': {
        'D2': 'Merge Registration is pending', 'G2': 'Gaurav Bagouli', 'H2': 'Open'}}])]
    [entry] = read_json(service.ledger_file, {}).values()
    assert (entry['ticket'], entry['written'], entry['assignee']) == ('ASPL-190001', True, 'Gaurav Bagouli')


def test_rows_of_every_picked_status_get_their_number_written(service):
    service.excel.data = make_xlsx([HEADER, (2, bug()), (3, bug(Description='Already fixed', Status='done/build'))])
    record = asyncio.run(service.run_once('manual', everything=True))
    assert [(c['row'], c['sheet']) for c in record['created']] == [(2, 'Written to row 2.'), (3, 'Written to row 3.')]
    [(_, writes)] = service.excel.writes
    assert [(w['cell'], w['checks']['H3' if w['cell'] == 'K3' else 'H2']) for w in writes] == [('K2', 'Open'), ('K3', 'done/build')]
    assert [d.status for d in service.creator.calls[0][0]] == ['Open', 'Completed']


def test_a_row_never_gets_a_second_ticket(service):
    request = AssignRequest(tickets=[ticket_for(service, 2)], settings=AssignSettings(), save=True)
    asyncio.run(service.create(request))
    with pytest.raises(ValueError, match='already got ASPL-190001'):
        asyncio.run(service.create(request))
    assert len(service.creator.calls) == 1


def test_fill_only_never_touches_the_sheet_or_ledger(service):
    asyncio.run(service.create(AssignRequest(tickets=[ticket_for(service, 2)], settings=AssignSettings())))
    assert service.excel.writes == [] and read_json(service.ledger_file, {}) == {}


def test_a_failed_sheet_write_is_retried_without_a_new_ticket(service):
    service.excel.fail = True
    result = asyncio.run(service.create(AssignRequest(tickets=[ticket_for(service, 2)], settings=AssignSettings(), save=True)))
    assert 'It will be retried' in result['tasks'][0]['sheet']
    service.excel.fail = False
    record = asyncio.run(service.run_once('manual'))
    assert record['written'] == ['Written to row 2.'] and record['created'] == []
    assert len(service.creator.calls) == 1
    assert list(read_json(service.ledger_file, {}).values())[0]['written'] is True


def test_auto_run_only_takes_rows_added_after_switch_on_and_holds_unclear_ones(service):
    summary = asyncio.run(service.set_auto(True))
    assert (summary['on'], summary['baseline']) == (True, 1)
    service.excel.data = make_xlsx([HEADER, (2, bug()),
                                    (3, bug(Description='Invoice total wrong', **{'Assigned to': 'Naveen', 'Module': 'Augstam billing'})),
                                    (4, bug(Description='Unclear owner', **{'Assigned to': 'Satendra sir'}))])
    record = asyncio.run(service.run_once('manual'))
    assert [(c['row'], c['assignee'], c['ticket']) for c in record['created']] == [(3, 'Naveen Shekhar Mishra', 'ASPL-190001')]
    assert [(h['row'], h['sheetName']) for h in record['held']] == [(4, 'Satendra sir')]
    assert [w[1][0]['cell'] for w in service.excel.writes] == ['K3']
    again = asyncio.run(service.run_once('manual'))
    assert again['created'] == [] and len(service.creator.calls) == 1
    state = service.auto_summary()
    assert (len(state['runs']), state['nextRun'] is not None) == (2, True)
    assert asyncio.run(service.set_auto(False))['nextRun'] is None


def test_run_now_takes_the_rows_waiting_since_switch_on(service):
    asyncio.run(service.set_auto(True))
    assert asyncio.run(service.run_once('scheduled'))['created'] == []
    record = asyncio.run(service.run_once('manual', everything=True))
    assert [(c['row'], c['ticket']) for c in record['created']] == [(2, 'ASPL-190001')]
    assert asyncio.run(service.run_once('manual', everything=True))['created'] == []  # the ledger has it now
    assert service.auto_summary()['running'] is None


def test_run_now_can_take_only_the_first_few_rows(service):
    service.excel.data = make_xlsx([HEADER, (2, bug()), (3, bug(Description='Second bug')), (4, bug(Description='Third bug'))])
    record = asyncio.run(service.run_once('manual', everything=True, count=2))
    assert ([c['row'] for c in record['created']], record['left']) == ([2, 3], 1)
    rest = asyncio.run(service.run_once('manual', everything=True, count=2))
    assert ([c['row'] for c in rest['created']], 'left' in rest) == ([4], False)


def test_stop_ends_the_run_after_the_ticket_in_progress(service):
    service.excel.data = make_xlsx([HEADER, (2, bug()), (3, bug(Description='Second bug')), (4, bug(Description='Third bug'))])
    proceed = service._proceed

    def stop_after_first(i):
        if i == 2:
            service.stop()
        return proceed(i)
    service._proceed = stop_after_first
    record = asyncio.run(service.run_once('manual', everything=True))
    assert ([c['row'] for c in record['created']], record['stopped']) == ([2], 2)
    assert [w[1][0]['cell'] for w in service.excel.writes] == ['K2']  # the saved ticket's number is still written
    assert (service.running, service.stopping) == (None, False)


def test_a_run_that_fails_is_recorded_and_the_timer_keeps_going(service):
    async def broken(url):
        raise RuntimeError('OneDrive down')
    service.excel.download = broken
    record = asyncio.run(service.run_once('manual'))
    assert 'OneDrive down' in record['error']
    assert service.auto_summary()['runs'][0]['error'] == record['error']


# ---------- endpoints ----------

def test_settings_round_trip_through_the_app(monkeypatch, tmp_path):
    store = {}
    monkeypatch.setattr(main, 'save_assign_settings', lambda s: store.update(settings=s))
    monkeypatch.setattr(main, 'load_assign_settings', lambda: store.get('settings', AssignSettings()))
    monkeypatch.setattr(main, 'ASSIGN_SETTINGS_FILE', tmp_path / 'none.json')
    client = TestClient(main.app)
    body = client.get('/assign/settings', headers=HEADERS).json()
    assert (body['saved'], body['settings']['fields']['priority']['value']) == (False, 'High')
    sent = {**body['settings'], 'people': {'satendra sir': 'Satender Datt Chamoli'}, 'sheetUrl': 'ignored'}
    assert client.post('/assign/settings', headers=HEADERS, json=sent).status_code == 200
    assert store['settings'].people == {'satendra sir': 'Satender Datt Chamoli'}
    assert client.get('/assign/auto').status_code == 403  # the local app header is required


def test_sheet_endpoint_reports_the_account_but_never_the_password(monkeypatch, tmp_path):
    monkeypatch.setattr(main.assign_service, 'test_sheet', tmp_path / 'sheet.csv')
    monkeypatch.setenv(f'{main.ASSIGN_ACCOUNT}_USERNAME', 'agent')
    monkeypatch.setenv(f'{main.ASSIGN_ACCOUNT}_PASSWORD', 'secret')
    body = TestClient(main.app).post('/assign/sheet', headers=HEADERS, json={'source': 'test'}).json()
    assert (body['account'], body['ready'], body['source'], len(body['rows'])) == ('agent', True, 'test', 1)
    assert 'sheetUrl' in body and 'secret' not in str(body)


def test_saving_a_setting_changes_only_that_env_line(tmp_path):
    from backend.config import save_setting
    env = tmp_path / '.env'
    env.write_bytes(b'ACE_USERNAME=me\r\nACE_ASSIGN_SHEET_URL=https://old\r\nSATENDER_PASSWORD=x\r\n')
    save_setting('ACE_ASSIGN_SHEET_URL', 'https://onedrive.live.com/new', env)
    assert env.read_bytes() == b'ACE_USERNAME=me\r\nACE_ASSIGN_SHEET_URL=https://onedrive.live.com/new\r\nSATENDER_PASSWORD=x\r\n'
    save_setting('ACE_ASSIGN_ACCOUNT', 'SATENDER', env)
    assert env.read_bytes().endswith(b'SATENDER_PASSWORD=x\r\nACE_ASSIGN_ACCOUNT=SATENDER\r\n')


def test_sheet_link_endpoint_accepts_only_onedrive_or_sharepoint_links(monkeypatch):
    saved = {}
    monkeypatch.setattr(main, 'save_setting', lambda name, value: saved.update({name: value}))
    client = TestClient(main.app)
    link = 'https://onedrive.live.com/:x:/g/personal/abc/XYZ?e=1'
    assert client.post('/assign/sheet-url', headers=HEADERS, json={'url': link}).status_code == 200
    assert saved == {'ACE_ASSIGN_SHEET_URL': link}
    for bad in ('http://onedrive.live.com/x', 'https://evil.example/x', 'https://onedrive.live.com/x\nACE_PASSWORD=1'):
        assert client.post('/assign/sheet-url', headers=HEADERS, json={'url': bad}).status_code == 422
