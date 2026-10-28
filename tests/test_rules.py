from datetime import date
import pytest
from pydantic import ValidationError
from backend.app_rules import allocate, allocate_natural, workplace, working_dates, minutes
from backend.app_models import DayPlan, Task, Ticket
from backend.app_timesheet import parse_grid, prefix_matches
from backend.app_session import PortalError
from backend.services.planner import explicit_ticket


def plan():
    return DayPlan(date=date(2026, 9, 23), workplace='Office', totalHours='09:15',
                   tasks=[Task(description='Updated documentation.', start='09:45', end='19:00')])


@pytest.mark.parametrize('count', [1, 2, 3, 7, 17, 40])
def test_even_allocation(count):
    rows = allocate([None] * count)
    assert rows[0][0] == '09:45' and rows[-1][1] == '19:00'
    assert all(left[1] == right[0] for left, right in zip(rows, rows[1:]))
    lengths = [minutes(end) - minutes(start) for start, end in rows]
    assert max(lengths) - min(lengths) <= 1


def test_explicit_durations_and_padding():
    assert allocate([120, 180]) == [('09:45', '11:45'), ('11:45', '19:00')]
    assert allocate([120, None, 60]) == [('09:45', '11:45'), ('11:45', '18:00'), ('18:00', '19:00')]
    assert allocate([560]) == [('09:45', '19:05')]
    assert allocate([558, None])[-1][1] == '19:04'


@pytest.mark.parametrize('count', [1, 2, 3, 4, 5, 6, 7])
def test_allocate_natural_realistic_blocks(count):
    rows = allocate_natural([None] * count)
    assert rows[0][0] == '09:45' and rows[-1][1] == '19:00'
    assert all(left[1] == right[0] for left, right in zip(rows, rows[1:]))
    lengths = [minutes(end) - minutes(start) for start, end in rows]
    assert sum(lengths) == 555
    assert all(l % 15 == 0 for l in lengths)
    for start, end in rows:
        assert minutes(start) % 15 == 0
        assert minutes(end) % 15 == 0
    if count == 5:
        assert 114 not in lengths
        assert len(set(lengths)) > 1


def test_allocate_natural_with_task_descriptions():
    descriptions = [
        'Investigated and resolved software bugs related to the patient visit summary.',
        'Reviewed the discharge summary API data to identify errors, which were subsequently corrected by Amit.',
        'Mentored and provided technical guidance to intern Harsh Tiagi.',
        'Met with the intern to discuss product features, AI capabilities, and other project details.',
        'Gathered feedback and insights from Satyendra regarding the analytic dashboard and initiated work on the unassigned ticket.'
    ]
    rows = allocate_natural([None] * 5, descriptions)
    assert rows[0][0] == '09:45' and rows[-1][1] == '19:00'
    lengths = [minutes(end) - minutes(start) for start, end in rows]
    assert sum(lengths) == 555
    assert all(l % 15 == 0 for l in lengths)
    assert 114 not in lengths
    assert lengths[0] > lengths[2]


@pytest.mark.parametrize('durations', [[], [0], [-1], [570], [569, None], [1.5], [None]*41, [True]])
def test_reject_impossible_allocation(durations):
    with pytest.raises(ValueError): allocate(durations)


def test_weekday_rules():
    assert workplace(date(2026, 9, 25)) == 'Home'
    assert workplace(date(2026, 9, 26)) == 'Office'
    assert working_dates(date(2026,9,25), date(2026,9,28)) == [date(2026,9,25),date(2026,9,26),date(2026,9,28)]


@pytest.mark.parametrize('changes', [
    {'workplace':'Home'}, {'totalHours':'08:00'},
    {'tasks':[{'description':'x','start':'09:45','end':'18:44'}]},
    {'tasks':[{'description':'x','start':'09:45','end':'19:31'}]},
    {'tasks':[{'description':'x','start':'09:44','end':'19:15'}]},
    {'tasks':[{'description':'x','start':'10:01','end':'19:15'}]},
    {'tasks':[{'description':'x','start':'09:45','end':'19:15','taskName':'Bug'}]},
    {'tasks':[{'description':' '*5,'start':'09:45','end':'19:15'}]},
    {'tasks':[{'description':'x'*501,'start':'09:45','end':'19:15'}]},
    {'tasks':[{'description':'Missing prefix','start':'09:45','end':'19:15','ticket':'ASPL-169999'}]},
    {'tasks':[{'description':'x','start':'09:45','end':'12:00'}, {'description':'y','start':'12:01','end':'19:15'}]},
])
def test_fill_validation(changes):
    payload = plan().model_dump()
    payload.update(changes)
    with pytest.raises(ValidationError): DayPlan.model_validate(payload)


def test_placeholder_and_partial_existing_rows():
    assert parse_grid([['1'] + [''] * 8 + ['Edit', 'Remove']]) == []
    assert len(parse_grid([['1','Existing client'] + ['']*7 + ['Edit','Remove']])) == 1
    with pytest.raises(PortalError): parse_grid([['unexpected']])


def test_resume_requires_exact_prefix():
    expected = [{'description':'first','start':'09:45'}, {'description':'second','start':'12:00'}]
    assert prefix_matches([expected[0]], expected)
    assert not prefix_matches([expected[1]], expected)
    assert not prefix_matches(expected + [expected[0]], expected)


def test_ticket_validation_and_spoken_digits():
    tickets = [Ticket(ticket='ASPL-169999', description='fix'), Ticket(ticket='ASPL-169209', description='change')]
    assert explicit_ticket('Fixed 169999', tickets) == 'ASPL-169999'
    assert explicit_ticket('one six nine nine nine nine', tickets) == 'ASPL-169999'
    assert explicit_ticket('ASPL-999999', tickets) is None
    assert explicit_ticket('169999 and 169209', tickets) is None
