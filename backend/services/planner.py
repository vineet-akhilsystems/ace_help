import re
import hashlib
from backend.app_rules import allocate, allocate_natural, clock, minutes, workplace
from backend.app_models import DayPlan, Segments, StrictModel, Task
from backend.services.providers import gemini, jev, ProviderError


from backend.services.activity_gatherer import gather_day_activity, format_activity_digest, _notify


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


async def make_plan(transcript, day, tickets, ticket_warning=None, on_progress=None):
    warnings = [ticket_warning] if ticket_warning else []
    day_str = day.isoformat()
    _notify(on_progress, f"Analyzing system activity for {day_str}...", None, "search")
    activity = gather_day_activity(day_str, on_progress=on_progress)
    activity_digest = format_activity_digest(activity)

    activity_summary = None
    if activity.get('has_activity'):
        counts = []
        if activity['commits']:
            counts.append(f"{len(activity['commits'])} commit(s)")
        if activity['new_folders']:
            counts.append(f"{len(activity['new_folders'])} folder(s)")
        if activity['files']:
            counts.append(f"{len(activity['files'])} file(s)")
        activity_summary = f"Detected {', '.join(counts)} on your system for this date."
        print(f"[ACE Assistant] [SCAN] {activity_summary}", flush=True)

    if tickets:
        _notify(on_progress, "Checking assigned ACE tickets for context & module matching", f"Loaded {len(tickets)} assigned ticket(s) from cache", "ticket")
    else:
        _notify(on_progress, "Checking assigned ACE tickets", "Tickets not loaded yet (planning using system activity & notes)", "ticket")

    if transcript and transcript.strip():
        _notify(on_progress, "Analyzing user notes & speech transcript", f"{len(transcript.split())} words provided", "notes")

    tickets_context = '\n'.join([f"- {t.ticket} ({t.module}): {t.description[:250]}" for t in tickets[:25]]) if tickets else ''

    source_components = []
    if transcript and transcript.strip():
        source_components.append(f"USER NOTES / TRANSCRIPT:\n{transcript.strip()}")
    if activity_digest:
        source_components.append(activity_digest)
    if tickets_context:
        source_components.append(f"ASSIGNED ACE TICKETS CONTEXT:\n{tickets_context}")

    full_source_text = '\n\n'.join(source_components) if source_components else (transcript or 'No notes provided.')

    _notify(on_progress, "Synthesizing tasks with Gemini & computing natural 15-minute time blocks", "Correlating notes with real commits and documents", "ai")

    multiple = None
    try:
        judgments = await jev(transcript or activity_digest, {'multiple': {'type': 'noul',
            'instructions': 'These notes describe more than one distinct work task.'}})
        multiple = judgments['multiple']['noul'] >= .7
    except (ProviderError, KeyError, TypeError):
        warnings.append('Jev segmentation check unavailable; review the task boundaries.')
    try:
        segments = Segments.model_validate(await gemini(transcript, multiple, activity_digest, tickets_context)).tasks
    except ValueError:
        raise ProviderError('Generated tasks failed validation. Try clearer notes.') from None
    if any(s.source not in full_source_text for s in segments):
        raise ProviderError('Generated tasks could not be traced to the notes or detected activity. Please retry.')
    matches = []
    reasons = []
    for s in segments:
        m = explicit_ticket(s.source, tickets)
        if not m:
            t_match = re.search(r'ASPL-\d{5,8}', s.description, re.I)
            if t_match:
                cand = t_match.group(0).upper()
                if any(t.ticket == cand for t in tickets):
                    m = cand
        matches.append(m)
        reasons.append('Explicit number matched an assigned ticket.' if m else None)

    # Up to 254 candidates plus the explicit no-match option per the choice API.
    candidates = tickets[:254]
    questions = {f'task_{i}': {'type': 'choice',
        'instructions': f'Match task {i} only when it clearly describes the same work. Prefer none when uncertain.',
        'criteria': {'none': 'No matching assigned ticket', **{t.ticket: t.description[:1500] for t in candidates}}}
        for i in range(len(segments)) if not matches[i] and candidates}
    if questions:
        try:
            answers = await jev({'tasks': [s.source for s in segments]}, questions)
            checks = {}
            for i in range(len(segments)):
                answer = answers.get(f'task_{i}', {})
                selected = answer.get('choice')
                if selected in {t.ticket for t in candidates} and answer.get('confidence', 0) >= .85:
                    checks[f'task_{i}'] = {'type': 'noul', 'instructions':
                        f'Task {i} clearly describes the same work as {selected}: ' +
                        next(t.description for t in candidates if t.ticket == selected)}
            verified = await jev({'tasks': [s.source for s in segments]}, checks) if checks else {}
            for i in range(len(segments)):
                if verified.get(f'task_{i}', {}).get('noul', 0) >= .9:
                    matches[i] = answers[f'task_{i}']['choice']
                    reasons[i] = 'Semantic suggestion: confidence ≥85%, match check ≥90%. Please review.'
        except (ProviderError, TypeError):
            warnings.append('Semantic ticket matching unavailable; unmatched tasks remain valid without tickets.')
    items = [PlannedItem(description=s.description, ticket=m, reason=r, durationMinutes=s.durationMinutes)
             for s, m, r in zip(segments, matches, reasons)]
    plan = build_day_plan(day, items, warnings, activity_summary)
    _notify(on_progress, f"Plan generated for {day_str} ({len(plan.tasks)} tasks, {plan.totalHours} hrs)", f"All tasks grounded and allocated in natural 15m intervals", "done")
    return plan


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
