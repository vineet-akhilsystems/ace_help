from datetime import date
from backend.services import planner
from backend.app_rules import minutes


def test_humanize_strips_files_paths_and_hashes():
    text = ('I fixed the vitals table in PatientSummary.jsx and backend/services/planner.py (commit 3f9a2c1b) '
            r'and shared C:\Users\HP\docs\handover.docx with Nitin.')
    clean = planner.humanize(text)
    for bad in ('.jsx', '.py', '3f9a2c1b', 'C:', 'handover'):
        assert bad not in clean
    assert clean.startswith('I fixed the vitals table') and clean.endswith('with Nitin.')
    assert planner.humanize('Tested API v2.0 on 12 Sep with Rahul.') == 'Tested API v2.0 on 12 Sep with Rahul.'


def test_ticket_description_has_no_worked_on_prefix():
    items = [planner.PlannedItem(description='I fixed the null fields issue in the clinical record API for ASPL-169999.',
                                 ticket='ASPL-169999')]
    result = planner.build_day_plan(date(2026, 9, 24), items, [])
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
