import re
import hashlib
from backend.app_rules import allocate, allocate_natural, clock, minutes, workplace
from backend.app_models import DayPlan, StrictModel, Task


FILE_EXTENSIONS = ('py|pyc|js|jsx|ts|tsx|json|md|txt|pdf|docx?|xlsx?|pptx?|png|jpe?g|gif|svg|csv|html?|css|scss|'
                   'ya?ml|sql|ipynb|ps1|sh|bat|env|zip|mp4|mp3|wav|webm|log|java|cs|go|rb|php|xml|toml|ini|lock|pen')
WINDOWS_PATH = re.compile(r'[A-Za-z]:\\[^\s,;)]*')
FILE_REFERENCE = re.compile(r'(?:[\w.-]+[/\\])*[\w-]+(?:\.[\w-]+)*\.(?:' + FILE_EXTENSIONS + r')\b', re.I)
UNIX_PATH = re.compile(r'(?<![\w.])(?:[\w.-]+/){2,}[\w.-]*')
COMMIT_HASH = re.compile(r'\b(?:commit\s+)?(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b', re.I)
TICKET_MENTION = re.compile(r'\s*(?:\b(?:for|on|in|under|of)\s+)?\[?ASPL-\d{5,8}\]?:?', re.I)


class PlannedItem(StrictModel):
    description: str
    ticket: str | None = None
    reason: str | None = None
    evidence: str | None = None
    durationMinutes: int | None = None


def humanize(text):
    """Removes file names, paths and commit hashes the model may still echo from system activity."""
    for pattern in (WINDOWS_PATH, FILE_REFERENCE, UNIX_PATH, COMMIT_HASH):
        text = pattern.sub('', text)
    text = re.sub(r'\(\s*[,;]?\s*\)', '', text)            # emptied brackets
    text = re.sub(r'(?:in|and|to|from|with)\s+(?=(?:and|in|with|to)|[,.;])', '', text)  # dangling joiners
    text = re.sub(r'\s+([,.;:])', r'', text)
    text = re.sub(r'([,;])(?=[,.;])', '', text)
    return re.sub(r'\s{2,}', ' ', text).strip()


def explicit_ticket(source: str, tickets) -> str | None:
    digits = {'zero':'0', 'one':'1', 'two':'2', 'three':'3', 'four':'4', 'five':'5',
              'six':'6', 'seven':'7', 'eight':'8', 'nine':'9'}
    normalized = source.lower()
    pattern = r'\b(?:(?:' + '|'.join(digits) + r')\s+){4,7}(?:' + '|'.join(digits) + r')\b'
    normalized = re.sub(pattern, lambda m: ''.join(digits[w] for w in m[0].split()), normalized)
    numbers = re.findall(r'(?<!\d)(\d{5,8})(?!\d)', normalized)
    matches = {t.ticket for t in tickets if t.ticket.split('-')[1] in numbers}
    return next(iter(matches)) if len(matches) == 1 else None


def build_day_plan(day, items, warnings, activity_summary=None):
    """Turns ordered task items into a validated DayPlan with natural contiguous times."""
    # Stable per day so regenerating the same plan does not shift its time window.
    seed = hashlib.sha256(day.isoformat().encode()).digest()
    target_minutes = 540 + int.from_bytes(seed[:2], 'big') % 30
    times = allocate_natural([i.durationMinutes for i in items],
                             [i.description for i in items], target_minutes)
    if any(i.durationMinutes is not None and minutes(end) - minutes(start) != i.durationMinutes
           for i, (start, end) in zip(items, times)):
        warnings.append('The final task was extended to meet the daily time window. Review the allocation.')
    tasks = []
    for item, (start, end) in zip(items, times):
        clean_desc = humanize(TICKET_MENTION.sub('', item.description))
        full_desc = (f'[{item.ticket}] ' + clean_desc if item.ticket else clean_desc)[:500]
        tasks.append(Task(description=full_desc, start=start, end=end,
                          ticket=item.ticket, matchReason=item.reason, evidence=item.evidence))
    return DayPlan(date=day, workplace=workplace(day),
                   totalHours=clock(minutes(times[-1][1]) - minutes(times[0][0])),
                   tasks=tasks, warnings=warnings, activitySummary=activity_summary)
