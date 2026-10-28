from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from backend import app_tasks
from backend.app_tasks import TaskDraft, check_drafts, snap
from backend.main import app

HEADERS = {'X-ACE-Client': '1'}
FORM = {'options': {'task_type': [{'text': 'Bug'}], 'priority': [{'text': 'High'}, {'text': 'Medium'}],
                    'client_name': [{'text': 'Aster RV Hospital'}, {'text': 'Aster MIMS Calicut'}],
                    'module': [{'text': 'EMR'}, {'text': 'Oracle - HIS\xa0 Interface'}],
                    'frd_nature': [{'text': 'Low'}], 'task_status': [{'text': 'Open'}, {'text': 'Working'}]}}


def draft(**change):
    data = dict(taskType='Bug', priority='High', client='Aster RV Hospital', module='EMR', status='Open',
                targetDate='2026-10-01T18:00', effortDays=1, keyword='vitals', description='Vitals not saving',
                clientRemarks='Reported by ward', employeeRemarks='Analysis in progress.')
    return TaskDraft(**{**data, **change})


def test_snap_returns_exact_ace_text():
    choices = [o['text'] for o in FORM['options']['module']]
    assert snap('oracle - his interface', choices) == 'Oracle - HIS\xa0 Interface'
    assert snap('Aster Calicut', ['Aster RV Hospital', 'Aster MIMS Calicut']) == 'Aster MIMS Calicut'
    assert snap('Aster', ['Aster RV Hospital', 'Aster MIMS Calicut']) == ''
    assert snap('', choices) == ''


def test_drafts_must_use_ace_options():
    check_drafts([draft()], FORM)
    with pytest.raises(ValueError):
        check_drafts([draft(client='Aster RV')], FORM)
    with pytest.raises(ValueError):
        check_drafts([draft(frdNature='Urgent')], FORM)


def test_padded_ace_options_survive_whitespace_stripping():
    form = {'options': {**FORM['options'], 'client_name': [{'text': 'Cloud LIS '}],
                        'module': [{'text': 'Oracle - HIS  Interface'}]}}
    # TaskDraft strips "Cloud LIS " to "Cloud LIS"; the fill must still use ACE's exact text.
    d = draft(client='Cloud LIS ', module='oracle - his interface')
    check_drafts([d], form)
    assert d.client == 'Cloud LIS ' and d.module == 'Oracle - HIS  Interface'
    with pytest.raises(ValueError):
        check_drafts([draft(client='Cloud')], form)


def test_fill_validates_before_browser_and_has_no_save(monkeypatch):
    from backend.main import creator
    import backend.main as main
    fill = AsyncMock(return_value={'tasks': [], 'notStarted': [], 'saved': False})
    monkeypatch.setattr(creator, 'fill', fill)
    monkeypatch.setattr(main, 'load_form', lambda: FORM)
    good = draft().model_dump(mode='json')
    with TestClient(app) as client:
        assert client.post('/tasks/fill', json=[{**good, 'client': 'Unknown'}], headers=HEADERS).status_code == 422
        assert client.post('/tasks/fill', json=[{**good, 'effortDays': 0}], headers=HEADERS).status_code == 422
        assert client.post('/tasks/fill', json=[], headers=HEADERS).status_code == 422
        fill.assert_not_awaited()
        assert client.post('/tasks/fill', json=[good], headers=HEADERS).json()['saved'] is False
    assert not any('save' in path.lower() for path in app.openapi()['paths'])


def test_planned_drafts_snap_and_default(monkeypatch):
    import asyncio
    from datetime import date
    from backend.services import providers
    monkeypatch.setattr(app_tasks, 'load_form', lambda: FORM)
    notes = 'Aster Calicut EMR vitals not saving, high priority'
    async def fake(agent, prompt, schema):
        assert agent == 'antigravity'
        return {'tasks': [{'source': 'Aster Calicut EMR vitals not saving', 'client': 'Aster Calicut', 'module': 'EMRs',
                           'priority': 'high', 'keyword': 'vitals', 'description': 'd'}]}
    monkeypatch.setattr(providers, 'agent_json', fake)
    [task] = asyncio.run(app_tasks.make_task_drafts(notes, app_tasks.TaskDefaults(taskType='Bug'), date(2026, 10, 2)))
    assert (task['client'], task['module'], task['priority'], task['status']) == ('Aster MIMS Calicut', 'EMR', 'High', 'Open')
    assert task['targetDate'] == '2026-10-03T18:00'  # Friday -> Saturday (working day)
    assert task['effortDays'] == 1 and len(task['warnings']) == 2
    assert (task['clientRemarks'], task['employeeRemarks']) == ('.', '.')


ACE_FORM = {'options': {'task_type': [{'text': 'Bug'}, {'text': 'New Requirement'}],
                        'priority': [{'text': 'Medium'}, {'text': 'High'}],
                        'client_name': [{'text': 'Augastam (New Product) '}], 'module': [{'text': 'Augastam ai'}],
                        'frd_nature': [{'text': 'Medium'}], 'task_status': [{'text': 'Open'}]}}


def test_timesheet_rows_become_linked_ticket_drafts():
    from datetime import date
    days = [app_tasks.TimesheetDay(date=date(2026, 10, 27), tasks=[app_tasks.TimesheetRow(
        index=2, description='I fixed the vitals template rendering for doctors on the summary screen.', minutes=150)])]
    [task] = app_tasks.ticket_drafts_for_timesheet(days, ACE_FORM, date(2026, 10, 28))
    assert (task['taskType'], task['priority'], task['client'], task['module'], task['frdNature'], task['status']) == (
        'New Requirement', 'Medium', 'Augastam (New Product) ', 'Augastam ai', 'Medium', 'Open')
    assert task['link'] == {'date': '2026-10-27', 'index': 2}
    assert task['description'].startswith('I fixed the vitals') and task['keyword'] == 'vitals, template'
    assert (task['clientRemarks'], task['employeeRemarks'], task['effortDays']) == ('.', '.', 0.25)
    assert task['targetDate'] == '2026-10-29T18:00' and task['workDate'] == '2026-10-27' and task['warnings'] == []
    TaskDraft(**{k: v for k, v in task.items() if k not in ('link', 'workDate')})


def test_new_tickets_match_by_description_only_once():
    from backend.app_models import Ticket
    text = 'I reviewed the discharge summary API data with the backend team and corrected the wrong values.'
    assigned = [Ticket(ticket='ASPL-100001', description=text), Ticket(ticket='ASPL-100002', description=text[:45]),
                Ticket(ticket='ASPL-100003', description='Something else entirely')]
    assert app_tasks.match_new_tickets([text, 'Nothing saved for this'], assigned, ['ASPL-100002']) == ['ASPL-100001', None]
    # Two unknown candidates for one description is ambiguous, so nothing is linked.
    assert app_tasks.match_new_tickets([text], assigned, []) == [None]


def test_link_tickets_endpoint_reads_ace(monkeypatch):
    from backend import main
    from backend.app_models import Ticket
    monkeypatch.setattr(main.portal, 'tickets', AsyncMock(return_value=[Ticket(ticket='ASPL-100009', description='New work item')]))
    with TestClient(app) as client:
        res = client.post('/tasks/link-tickets', json={'descriptions': ['New work item'], 'known': []}, headers=HEADERS)
    assert res.status_code == 200 and res.json()['links'] == ['ASPL-100009']


def test_strict_schema_requires_every_field_and_keeps_field_names():
    from backend.services.providers import strict_schema
    schema = strict_schema({'title': 'X', 'type': 'object', 'properties': {
        'title': {'type': 'string', 'title': 'Title'}, 'note': {'anyOf': [{'type': 'string'}, {'type': 'null'}], 'default': None}}})
    assert schema == {'type': 'object', 'properties': {'title': {'type': 'string'},
                      'note': {'anyOf': [{'type': 'string'}, {'type': 'null'}]}},
                      'required': ['title', 'note'], 'additionalProperties': False}


def test_existing_ticket_is_kept_only_when_it_is_mine(monkeypatch):
    import asyncio
    from datetime import date
    from backend.app_models import Ticket
    from backend.services import providers
    monkeypatch.setattr(app_tasks, 'load_form', lambda: FORM)
    prompts = []
    async def fake(agent, prompt, schema):
        prompts.append(prompt)
        base = {'keyword': 'k', 'description': 'd'}
        return {'tasks': [{**base, 'source': 'vitals fix', 'existingTicket': 'ASPL-170001'},
                          {**base, 'source': 'new report', 'existingTicket': 'ASPL-999999'}]}
    monkeypatch.setattr(providers, 'agent_json', fake)
    mine = [Ticket(ticket='ASPL-170001', description='Vitals not saving', status='Open')]
    tasks = asyncio.run(app_tasks.make_task_drafts('vitals fix and new report', app_tasks.TaskDefaults(taskType='Bug'),
                                                    date(2026, 10, 28), existing=mine))
    assert [t['existingTicket'] for t in tasks] == ['ASPL-170001', None]
    assert 'ASPL-170001 (Open): Vitals not saving' in prompts[0]


def test_saved_ticket_is_never_saved_twice():
    import asyncio
    creator = app_tasks.TaskCreator(session=None)
    d = draft()
    fp = __import__('hashlib').sha256(d.model_dump_json(exclude={'warnings', 'source'}).encode()).hexdigest()
    creator.saved[fp] = {'status': 'saved', 'ticket': 'ASPL-170002'}
    result = asyncio.run(creator.fill_one(1, d, save=True))
    assert result['ticket'] == 'ASPL-170002' and 'not saved again' in result['message']


def test_create_finds_ticket_number_when_ace_does_not_show_it(monkeypatch):
    from backend import main
    from backend.app_models import Ticket
    monkeypatch.setattr(app_tasks, 'load_form', lambda: FORM)
    monkeypatch.setattr(main, 'load_form', lambda: FORM)
    monkeypatch.setattr(main.creator, 'fill', AsyncMock(return_value={'tasks': [
        {'index': 1, 'keyword': 'vitals', 'status': 'unconfirmed', 'ticket': None, 'message': 'x'}], 'notStarted': [], 'saved': False}))
    monkeypatch.setattr(main.portal, 'tickets', AsyncMock(return_value=[Ticket(ticket='ASPL-170003', description='Vitals not saving')]))
    monkeypatch.setattr(main.portal, 'ticket_cache', [])
    with TestClient(app) as client:
        res = client.post('/tasks/create', json=[draft().model_dump(mode='json')], headers=HEADERS).json()
    assert res['tasks'][0]['ticket'] == 'ASPL-170003' and res['tasks'][0]['status'] == 'saved'


def test_keywords_fit_ace_25_characters():
    assert app_tasks.short_keyword('Augastam Workspace Claude Setup') == 'Augastam Workspace Claude'
    assert app_tasks.short_keyword('vitals, template, rendering') == 'vitals, template'
    assert app_tasks.short_keyword('Supercalifragilisticexpialidocious') == 'Supercalifragilisticexpia'
    assert app_tasks.short_keyword(' short  one ') == 'short one'
    with pytest.raises(ValueError):
        draft(keyword='x' * 26)


def test_one_failed_ticket_does_not_stop_the_rest(monkeypatch):
    import asyncio
    creator = app_tasks.TaskCreator(session=type('S', (), {'lock': asyncio.Lock()})())
    calls = []
    async def one(index, d, save=False):
        calls.append(index)
        return {'index': index, 'status': 'interrupted' if index == 1 else 'saved', 'ticket': None}
    monkeypatch.setattr(creator, 'fill_one', one)
    result = asyncio.run(creator.fill([draft(), draft(keyword='b'), draft(keyword='c')], save=True))
    assert calls == [1, 2, 3] and result['notStarted'] == [] and result['saved'] is True


def test_save_refuses_a_form_holding_an_existing_ticket():
    import asyncio
    from backend.app_session import PortalError
    clicked = []
    class Locator:
        async def click(self): clicked.append(True)
    class Page:
        async def evaluate(self, script, arg=None): return {'id': '18342', 'label': 'Update'}
        def locator(self, selector): return Locator()
        def on(self, *a): pass
        def remove_listener(self, *a): pass
    with pytest.raises(PortalError):
        asyncio.run(app_tasks.TaskCreator(session=None).save_page(Page()))
    assert clicked == []


def test_past_work_records_its_day_but_targets_the_future(monkeypatch):
    import asyncio
    from datetime import date
    from backend.services import providers
    monkeypatch.setattr(app_tasks, 'load_form', lambda: FORM)
    async def fake(agent, prompt, schema):
        base = {'keyword': 'k', 'description': 'd'}
        return {'tasks': [{**base, 'source': 'vitals fix', 'workDate': '2026-10-21'},
                          {**base, 'source': 'new report', 'workDate': '2026-11-30'},   # future: ignored
                          {**base, 'source': 'old bug', 'workDate': None}]}
    monkeypatch.setattr(providers, 'agent_json', fake)
    tasks = asyncio.run(app_tasks.make_task_drafts('vitals fix, new report, old bug', app_tasks.TaskDefaults(taskType='Bug'),
                                                    date(2026, 10, 28)))
    assert [(t['workDate'], t['targetDate']) for t in tasks] == [
        ('2026-10-21', '2026-10-29T18:00'), (None, '2026-10-29T18:00'), (None, '2026-10-29T18:00')]  # ACE rejects past targets
