import asyncio
from datetime import date
from unittest.mock import AsyncMock
import pytest
from backend.services import planner
from backend.services.providers import ProviderError
from backend.app_rules import minutes


def test_grounding_rejects_invented_source(monkeypatch):
    monkeypatch.setattr(planner,'jev',AsyncMock(return_value={'multiple':{'noul':.1}}))
    monkeypatch.setattr(planner,'gemini',AsyncMock(return_value={'tasks':[{'source':'invented', 'description':'Invented work.', 'durationMinutes':None}]}))
    with pytest.raises(ProviderError):
        asyncio.run(planner.make_plan('Wrote documentation.', date(2026,9,23), []))


def test_optional_jev_failure_does_not_block_no_ticket_work(monkeypatch):
    monkeypatch.setattr(planner,'jev',AsyncMock(side_effect=ProviderError('unavailable')))
    monkeypatch.setattr(planner,'gemini',AsyncMock(return_value={'tasks':[{'source':'Wrote documentation.', 'description':'Updated documentation.', 'durationMinutes':None}]}))
    result = asyncio.run(planner.make_plan('Wrote documentation.', date(2026,9,25), []))
    assert result.workplace == 'Home'
    assert result.tasks[0].ticket is None and result.warnings
    assert 540 <= sum(minutes(t.end) - minutes(t.start) for t in result.tasks) < 570


def test_humanize_strips_files_paths_and_hashes():
    text = ('I fixed the vitals table in PatientSummary.jsx and backend/services/planner.py (commit 3f9a2c1b) '
            r'and shared C:\Users\HP\docs\handover.docx with Nitin.')
    clean = planner.humanize(text)
    for bad in ('.jsx', '.py', '3f9a2c1b', 'C:', 'handover'):
        assert bad not in clean
    assert clean.startswith('I fixed the vitals table') and clean.endswith('with Nitin.')
    assert planner.humanize('Tested API v2.0 on 12 Sep with Rahul.') == 'Tested API v2.0 on 12 Sep with Rahul.'


def test_ticket_description_has_no_worked_on_prefix(monkeypatch):
    from backend.app_models import Ticket
    ticket = Ticket(ticket='ASPL-169999', description='Generate clinical record API returns null fields')
    monkeypatch.setattr(planner, 'jev', AsyncMock(return_value={'multiple': {'noul': .1}}))
    monkeypatch.setattr(planner, 'gather_day_activity', lambda day, on_progress=None: {'has_activity': False})
    monkeypatch.setattr(planner, 'gemini', AsyncMock(return_value={'tasks': [{'source': 'Fixed ASPL-169999 null fields.',
        'description': 'I fixed the null fields issue in the clinical record API for ASPL-169999.', 'durationMinutes': None}]}))
    result = asyncio.run(planner.make_plan('Fixed ASPL-169999 null fields.', date(2026, 9, 24), [ticket]))
    assert result.tasks[0].description == '[ASPL-169999] I fixed the null fields issue in the clinical record API.'


def test_build_day_plan_prefixes_ticket_and_keeps_evidence():
    items = [planner.PlannedItem(description='I fixed the vitals template rendering for doctors.', ticket='ASPL-172905',
                                 reason='Agent match', evidence='Daily note item 1', durationMinutes=None)]
    result = planner.build_day_plan(date(2026,10,26), items, [])
    task = result.tasks[0]
    assert task.description.startswith('[ASPL-172905] I fixed')
    assert task.evidence == 'Daily note item 1'
    assert result.workplace == 'Office'
    assert 540 <= sum(minutes(t.end) - minutes(t.start) for t in result.tasks) < 570


def test_build_day_plan_humanizes():
    items = [planner.PlannedItem(description='I updated planner.py (commit 3f9a2c1b) for the summary screen.',
                                 ticket=None, reason=None, evidence='x', durationMinutes=None)]
    desc = planner.build_day_plan(date(2026,10,26), items, []).tasks[0].description
    assert '.py' not in desc and '3f9a2c1b' not in desc
