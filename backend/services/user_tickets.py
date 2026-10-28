"""The user's own ACE tickets (assigned to or completed by them) from the ace_mcp reporting database."""
import sys
from datetime import date, datetime
from pathlib import Path
from pydantic import Field
from backend.app_models import StrictModel
from backend.config import ROOT, setting

DONE_STATES = {'completed', 'delivered', 'verified', 'closed'}
FALLBACK_WARNING = 'ACE ticket database unavailable; using your scraped Assigned list.'


class UserTicket(StrictModel):
    ticket: str = Field(pattern=r'^ASPL-\d{5,8}$')
    description: str
    module: str = ''
    taskType: str = ''
    status: str = ''
    assignedOn: date | None = None
    completedOn: date | None = None
    completedByMe: bool = False


def _norm(name) -> str:
    return ' '.join(str(name or '').split()).casefold()


def _day(value) -> date | None:
    text = str(value or '').strip().split(' ')[0]
    try:
        return datetime.strptime(text, '%d/%m/%Y').date()
    except ValueError:
        return None


def rows_to_user_tickets(rows: list[dict], assignee: str) -> list[UserTicket]:
    me = _norm(assignee)
    tickets = []
    for row in rows:
        mine, completed = _norm(row.get('Employee Name')) == me, _norm(row.get('CompletedBy')) == me
        if not (mine or completed):
            continue
        try:
            tickets.append(UserTicket(
                ticket=str(row.get('ASPL#') or '').strip().upper(), description=str(row.get('Description') or ''),
                module=str(row.get('Module Name') or ''), taskType=str(row.get('Task Name') or ''),
                status=str(row.get('ASPL Status') or ''),
                assignedOn=_day(row.get('Assigned On')) or _day(row.get('Date')),
                completedOn=_day(row.get('CompletedOn')), completedByMe=completed))
        except ValueError:
            continue
    return tickets


def load_user_tickets(fallback) -> tuple[list[UserTicket], str | None]:
    path = Path(setting('ACE_MCP_PATH') or ROOT.parent / 'ace_mcp')
    try:
        if not (path / 'ace' / 'tools.py').exists():
            raise ImportError(path)
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
        from ace import tools
        rows = tools.search_tickets(limit=5000)['rows']
        return rows_to_user_tickets(rows, setting('ACE_ASSIGNEE', 'Vineet Kukreti')), None
    except Exception:
        return [UserTicket(ticket=t.ticket, description=t.description, module=t.module,
                           taskType=t.taskType, status=t.status) for t in fallback], FALLBACK_WARNING


def rank_for_day(tickets: list[UserTicket], day: date, limit: int = 60) -> list[UserTicket]:
    def key(t):
        when = t.completedOn or t.assignedOn
        return (t.status.casefold() in DONE_STATES, abs((when - day).days) if when else 10_000)
    return sorted(tickets, key=key)[:limit]
