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
    async def fake(prompt, schema):
        return {'tasks': [{'source': 'Aster Calicut EMR vitals not saving', 'client': 'Aster Calicut', 'module': 'EMRs',
                           'priority': 'high', 'keyword': 'vitals', 'description': 'd', 'clientRemarks': 'c',
                           'employeeRemarks': 'e'}]}
    monkeypatch.setattr(providers, 'gemini_json', fake)
    [task] = asyncio.run(app_tasks.make_task_drafts(notes, app_tasks.TaskDefaults(taskType='Bug'), date(2026, 10, 2)))
    assert (task['client'], task['module'], task['priority'], task['status']) == ('Aster MIMS Calicut', 'EMR', 'High', 'Open')
    assert task['targetDate'] == '2026-10-03T18:00'  # Friday -> Saturday (working day)
    assert task['effortDays'] == 1 and len(task['warnings']) == 2
