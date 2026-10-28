"""Checks, stores and tracks timesheet drafts submitted by coding agents."""
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from pydantic import Field
from backend.app_models import DayPlan, StrictModel
from backend.config import RUNTIME
from backend.services.planner import PlannedItem, TICKET_MENTION, build_day_plan, humanize

MIN_CHARS, MAX_CHARS = 40, 480


class AgentTask(StrictModel):
    description: str = Field(min_length=1, max_length=600)
    ticket: str | None = Field(default=None, pattern=r'^ASPL-\d{5,8}$')
    evidence: str = Field(min_length=1, max_length=600)
    durationMinutes: int | None = Field(default=None, ge=1, le=585)


class AgentDraft(StrictModel):
    date: date
    tasks: list[AgentTask] = Field(min_length=1, max_length=12)
    summary: str = Field(default='', max_length=600)


def accept_draft(draft: AgentDraft, user_tickets, context: dict) -> tuple[DayPlan | None, list[str]]:
    day = draft.date.isoformat()
    if not context['isWorkingDay']:
        return None, [f'{day} is not a working day.']
    if context['alreadyFilled']:
        return None, [f'{day} already has entries in ACE; nothing to draft.']
    if context['onLeave']:
        return None, [f'{day} is marked as leave.']
    mine = {t.ticket for t in user_tickets}
    errors, warnings, items = [], [], []
    for index, task in enumerate(draft.tasks, 1):
        text = humanize(TICKET_MENTION.sub('', task.description))
        if not MIN_CHARS <= len(text) <= MAX_CHARS:
            errors.append(f'Task {index}: description must be {MIN_CHARS}-{MAX_CHARS} characters after cleanup '
                          f'(got {len(text)}).')
        ticket = task.ticket
        if ticket and ticket not in mine:
            warnings.append(f'{ticket} is not one of your tickets, so it was removed.')
            ticket = None
        items.append(PlannedItem(description=text, ticket=ticket, evidence=task.evidence,
                                 durationMinutes=task.durationMinutes,
                                 reason='Matched by your agent. Please review.' if ticket else None))
    if errors:
        return None, errors
    try:
        return build_day_plan(draft.date, items, warnings, draft.summary or None), []
    except ValueError as error:
        return None, [str(error)]


class DraftStore:
    def __init__(self, folder: Path = RUNTIME / 'agent_drafts'):
        self.folder = folder

    def save(self, plan: DayPlan) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        record = {'createdAt': datetime.now(timezone.utc).isoformat(), 'plan': plan.model_dump(mode='json')}
        (self.folder / f'{plan.date.isoformat()}.json').write_text(json.dumps(record, ensure_ascii=False),
                                                                    encoding='utf-8')

    def _records(self):
        for path in self.folder.glob('*.json'):
            try:
                yield json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue

    def list(self) -> list[dict]:
        rows = [{'date': r['plan']['date'], 'createdAt': r['createdAt'], 'tasks': len(r['plan']['tasks'])}
                for r in self._records()]
        return sorted(rows, key=lambda r: r['createdAt'], reverse=True)

    def load(self, day: date) -> DayPlan | None:
        try:
            record = json.loads((self.folder / f'{day.isoformat()}.json').read_text(encoding='utf-8'))
            return DayPlan.model_validate(record['plan'])
        except (OSError, ValueError, KeyError):
            return None


@dataclass
class ActiveRun:
    day: date
    notes: str
    # Filled by request handlers, drained by the runner; deque appends are thread-safe.
    events: deque = field(default_factory=deque)
    plan: DayPlan | None = None
    rejects: int = 0
    last_errors: list[str] = field(default_factory=list)
    context_seen: bool = False
    context: dict | None = None
    context_lock: Lock = field(default_factory=Lock)
    cli_progress_at: float = 0
    cli_tool: str | None = None
    cli_tool_status: str | None = None


store = DraftStore()
current: ActiveRun | None = None
