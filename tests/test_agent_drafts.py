from datetime import date
from fastapi.testclient import TestClient
from backend.main import app
from backend.services import agent_drafts as ad
from backend.services.user_tickets import UserTicket

HEADERS = {'X-ACE-Client': '1'}
MINE = [UserTicket(ticket='ASPL-172905', description='Claude skills', completedByMe=True)]
LONG = 'I reviewed the discharge summary API data with the team and corrected the vitals mapping for doctors.'


def context(**change):
    return {'isWorkingDay': True, 'alreadyFilled': False, 'onLeave': False, **change}


def draft(*tasks, day='2026-10-27'):
    return ad.AgentDraft.model_validate({'date': day, 'tasks': list(tasks) or [
        {'description': LONG, 'ticket': 'ASPL-172905', 'evidence': 'Daily note item 1', 'durationMinutes': None}]})


def test_submit_refuses_filled_or_non_working_day():
    for ctx, reason in ((context(alreadyFilled=True), 'already has entries in ACE'),
                        (context(isWorkingDay=False), 'is not a working day'),
                        (context(onLeave=True), 'is marked as leave')):
        plan, errors = ad.accept_draft(draft(), MINE, ctx)
        assert plan is None and reason in errors[0]


def test_unknown_ticket_dropped_with_warning():
    plan, errors = ad.accept_draft(draft({'description': LONG, 'ticket': 'ASPL-111111', 'evidence': 'commit'}), MINE,
                                   context())
    assert errors == [] and plan.tasks[0].ticket is None
    assert 'ASPL-111111 is not one of your tickets, so it was removed.' in plan.warnings


def test_short_description_rejected_with_index():
    plan, errors = ad.accept_draft(draft({'description': LONG, 'ticket': None, 'evidence': 'a'},
                                         {'description': 'Fixed bug.', 'ticket': None, 'evidence': 'b'}), MINE, context())
    assert plan is None and errors == ['Task 2: description must be 40-480 characters after cleanup (got 10).']


def test_tagged_task_gets_prefix_and_reason():
    plan, errors = ad.accept_draft(draft(), MINE, context())
    assert not errors and plan.tasks[0].description.startswith('[ASPL-172905] I reviewed')
    assert plan.tasks[0].matchReason == 'Matched by your agent. Please review.'


def test_accepts_and_stores_draft(monkeypatch, tmp_path):
    monkeypatch.setattr(ad, 'store', ad.DraftStore(tmp_path))
    monkeypatch.setattr('backend.main.agent_day_context', lambda day: context())
    monkeypatch.setattr('backend.main.load_user_tickets', lambda fallback: (MINE, None))
    with TestClient(app) as client:
        body = draft().model_dump(mode='json')
        ok = client.post('/agent/submit', json=body, headers=HEADERS)
        assert ok.status_code == 200 and ok.json()['plan']['date'] == '2026-10-27'
        listed = client.get('/agent/drafts', headers=HEADERS).json()
        assert [d['date'] for d in listed] == ['2026-10-27'] and listed[0]['tasks'] == 1
        assert client.get('/agent/drafts/2026-10-27', headers=HEADERS).json()['tasks'][0]['evidence']
        bad = client.post('/agent/submit', json={**body, 'tasks': [{**body['tasks'][0], 'description': 'short one'}]},
                          headers=HEADERS)
        assert bad.status_code == 422 and bad.json()['detail'][0].startswith('Task 1:')


def test_agent_routes_require_header():
    with TestClient(app) as client:
        assert client.get('/agent/drafts').status_code == 403
        assert client.get('/agent/tickets/ASPL-172905').status_code == 403


def test_context_scan_reused_only_during_current_run(monkeypatch):
    from backend import main
    calls = []
    monkeypatch.setattr(main, 'day_context', lambda day, notes, tickets: calls.append(notes) or context())
    monkeypatch.setattr(main, 'optional_tickets', lambda: ([], None))
    run = ad.ActiveRun(day=date(2026, 10, 27), notes='my notes')
    monkeypatch.setattr(ad, 'current', run)
    assert main.agent_day_context(run.day) == context()
    assert main.agent_day_context(run.day) == context()
    assert calls == ['my notes']
    monkeypatch.setattr(ad, 'current', None)
    main.agent_day_context(run.day)
    assert calls == ['my notes', None]


def test_cached_context_does_not_allow_day_filled_during_run(monkeypatch, tmp_path):
    from backend import main
    run = ad.ActiveRun(day=date(2026, 10, 27), notes='', context=context())
    monkeypatch.setattr(ad, 'current', run)
    monkeypatch.setattr(ad, 'store', ad.DraftStore(tmp_path))
    monkeypatch.setattr(main, 'skip_reason', lambda day: f'{day} already has entries in ACE; skipped.')
    with TestClient(app) as client:
        response = client.post('/agent/submit', json=draft().model_dump(mode='json'), headers=HEADERS)
    assert response.status_code == 422 and 'already has entries' in response.json()['detail']
    assert ad.store.list() == []


def test_invalid_draft_shape_counts_as_rejection(monkeypatch):
    run = ad.ActiveRun(day=date(2026, 10, 27), notes='')
    monkeypatch.setattr(ad, 'current', run)
    with TestClient(app) as client:
        response = client.post('/agent/submit', json={'date': '2026-10-27', 'tasks': [{}]}, headers=HEADERS)
    assert response.status_code == 422
    assert run.rejects == 1 and any('description' in error for error in run.last_errors)


def test_other_validation_errors_do_not_count_as_draft_rejection(monkeypatch):
    run = ad.ActiveRun(day=date(2026, 10, 27), notes='')
    monkeypatch.setattr(ad, 'current', run)
    with TestClient(app) as client:
        response = client.post('/agent/event', json={}, headers=HEADERS)
    assert response.status_code == 422 and run.rejects == 0


def test_agent_cannot_submit_another_date(monkeypatch):
    run = ad.ActiveRun(day=date(2026, 10, 27), notes='')
    monkeypatch.setattr(ad, 'current', run)
    with TestClient(app) as client:
        response = client.post('/agent/submit', json=draft(day='2026-10-26').model_dump(mode='json'), headers=HEADERS)
    assert response.status_code == 422 and 'do not submit another date' in response.json()['detail']
    assert run.rejects == 1
