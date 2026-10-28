from datetime import date
from backend.app_models import Ticket
from backend.services import user_tickets as ut

ROWS = [
    {'ASPL#': 'ASPL-172905', 'Description': 'Claude skills', 'Module Name': 'Augastam ai', 'Task Name': 'Bug',
     'ASPL Status': 'Completed', 'Employee Name': 'Vineet  Kukreti', 'Assigned On': '26/10/2026 13:06',
     'Date': '26/10/2026', 'CompletedBy': 'Vineet  Kukreti', 'CompletedOn': '26/10/2026 13:06'},
    {'ASPL#': 'ASPL-170001', 'Description': 'Someone else', 'Module Name': 'Augastam ai', 'Task Name': 'Bug',
     'ASPL Status': 'Open', 'Employee Name': 'Amit Kumar', 'Assigned On': '20/10/2026 10:00',
     'Date': '20/10/2026', 'CompletedBy': None, 'CompletedOn': None},
    {'ASPL#': 'ASPL-170002', 'Description': 'Finished for Amit', 'Module Name': 'Augastam ai', 'Task Name': 'Activity',
     'ASPL Status': 'Completed', 'Employee Name': 'Amit Kumar', 'Assigned On': None,
     'Date': '01/10/2026', 'CompletedBy': 'vineet kukreti', 'CompletedOn': '02/10/2026 18:00'},
]


def test_rows_filter_by_assignee_with_double_space():
    tickets = ut.rows_to_user_tickets(ROWS, 'Vineet Kukreti')
    assert [t.ticket for t in tickets] == ['ASPL-172905', 'ASPL-170002']
    assert tickets[0].assignedOn == date(2026, 10, 26) and tickets[0].completedByMe
    assert tickets[1].completedByMe and tickets[1].assignedOn == date(2026, 10, 1)


def test_load_falls_back_when_db_import_fails(monkeypatch, tmp_path):
    monkeypatch.setenv('ACE_MCP_PATH', str(tmp_path / 'missing'))
    fallback = [Ticket(ticket='ASPL-169999', description='First task', module='Augastam ai', taskType='Bug', status='Open')]
    tickets, warning = ut.load_user_tickets(fallback)
    assert [t.ticket for t in tickets] == ['ASPL-169999'] and not tickets[0].completedByMe
    assert warning == 'ACE ticket database unavailable; using your scraped Assigned list.'


def test_rank_puts_open_and_near_dates_first():
    tickets = ut.rows_to_user_tickets(ROWS, 'Vineet Kukreti')
    tickets.append(ut.UserTicket(ticket='ASPL-160000', description='open old', status='Working',
                                 assignedOn=date(2026, 1, 1)))
    ranked = ut.rank_for_day(tickets, date(2026, 10, 3))
    assert [t.ticket for t in ranked] == ['ASPL-160000', 'ASPL-170002', 'ASPL-172905']
