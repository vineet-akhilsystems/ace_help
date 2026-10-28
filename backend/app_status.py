import json
from datetime import date, datetime, timedelta, timezone
from backend.app_rules import clock, is_working_day
from backend.app_session import PortalError
from backend.app_timesheet import PATH, set_report_date
from backend.config import RUNTIME

FULL_DAY = 9 * 60
RECENT_DAYS = 5
FILL_EVENTS = ('filled_not_saved', 'interrupted')
CACHE = RUNTIME / 'status_cache.json'
LEAVE = RUNTIME / 'leave_days.json'


def saved_minutes(rows):
    total = 0
    for row in rows:
        try:
            hours, mins = map(int, row.get('total', '').split(':'))
            total += hours * 60 + mins
        except ValueError:
            pass
    return total


def month_days(month, today):
    first = datetime.strptime(month, '%Y-%m').date()
    last = min((first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), today)
    return [first + timedelta(days=i) for i in range((last - first).days + 1)
            if is_working_day(first + timedelta(days=i))]


def calendar_days(month):
    first = datetime.strptime(month, '%Y-%m').date()
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def local_date(stamp):
    return datetime.fromisoformat(stamp).astimezone(timezone(timedelta(hours=5, minutes=30))).strftime('%d %b')


def classify(day, saved, event, leave, today, error=None, checked_at=None):
    base = {'date': day.isoformat(), 'savedHours': clock(saved) if saved else None, 'checkedAt': checked_at}
    if not is_working_day(day):
        return {**base, 'status': 'weekend', 'reason': 'Sunday off'}
    if day > today:
        return {**base, 'status': 'future', 'reason': 'Not due yet'}
    if leave:
        return {**base, 'status': 'leave', 'reason': 'Marked as leave in this app'}
    if saved is None:
        return {**base, 'status': 'unchecked',
                'reason': f'Could not check ACE: {error}' if error else 'Not checked in ACE yet'}
    if saved >= FULL_DAY:
        return {**base, 'status': 'filled', 'reason': f'Saved {clock(saved)} in ACE'}
    if saved:
        return {**base, 'status': 'partial', 'reason': f'Only {clock(saved)} of 09:00 saved in ACE'}
    if event and event['event'] == 'interrupted':
        return {**base, 'status': 'failed',
                'reason': f"App could not fill it on {local_date(event['at'])}: {event.get('detail') or 'fill was interrupted'}"}
    if event and event['event'] == 'filled_not_saved':
        # An unsaved draft is not an entry: ACE has 0 hours, so the day still needs filling.
        return {**base, 'status': 'missing',
                'reason': f"Nothing saved in ACE (0 hours). The app's draft from {local_date(event['at'])} was never saved"}
    return {**base, 'status': 'missing', 'reason': 'Nothing saved in ACE (0 hours)'}


def dates_to_scan(days, cache, leave, full):
    recent = set(days[-RECENT_DAYS:])
    chosen = []
    for day in days:
        key = day.isoformat()
        if key in leave:
            continue
        entry = cache.get(key)
        if full or day in recent or not entry or 'error' in entry or entry.get('minutes', 0) < FULL_DAY:
            chosen.append(day)
    return chosen


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path.parent.mkdir(exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def read_audit(path=None):
    latest = {}
    try:
        lines = (path or RUNTIME / 'audit.jsonl').read_text(encoding='utf-8').splitlines()
    except OSError:
        return latest
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        day = (record.get('plan') or {}).get('date')
        if day and record.get('event') in FILL_EVENTS:
            if day not in latest or record['at'] >= latest[day]['at']:
                latest[day] = record
    return latest


def leave_days():
    return set(read_json(LEAVE, []))


def set_leave(day, on):
    days = leave_days()
    days.add(day) if on else days.discard(day)
    write_json(LEAVE, sorted(days))


def month_status(month, today):
    cache, audit, leave = read_json(CACHE, {}), read_audit(), leave_days()
    days = []
    for day in calendar_days(month):
        key = day.isoformat()
        entry = cache.get(key, {})
        days.append(classify(day, entry.get('minutes'), audit.get(key), key in leave, today,
                             entry.get('error'), entry.get('checkedAt')))
    counted = [d for d in days if d['status'] not in ('weekend', 'future')]
    counts = {s: sum(d['status'] == s for d in counted)
              for s in ('filled', 'partial', 'missing', 'failed', 'unchecked', 'leave')}
    checked = [d['checkedAt'] for d in days if d['checkedAt']]
    return {'month': month, 'today': today.isoformat(), 'days': days, 'counts': counts,
            'workingDays': len(counted), 'lastChecked': max(checked) if checked else None}


class StatusScanner:
    def __init__(self, session, portal):
        self.session = session
        self.portal = portal

    async def scan_day(self, day):
        if self.session.lock.locked():
            raise PortalError('ACE is busy filling or loading. Try again when it finishes.')
        async with self.session.lock:
            page = await self.session.background(PATH)
            await set_report_date(page, day.isoformat())
            await self.portal.check_date(page, day.isoformat())
            rows = await self.portal.grid(page)
            entry = {'minutes': saved_minutes(rows), 'rows': len(rows),
                     'checkedAt': datetime.now(timezone.utc).isoformat()}
            cache = read_json(CACHE, {})
            cache[day.isoformat()] = entry
            write_json(CACHE, cache)
            return classify(day, entry['minutes'], read_audit().get(day.isoformat()),
                            day.isoformat() in leave_days(), day, checked_at=entry['checkedAt'])

    async def scan(self, month, today, full, on_progress):
        days = dates_to_scan(month_days(month, today), read_json(CACHE, {}), leave_days(), full)
        if not days:
            return 0
        if self.session.lock.locked():
            raise PortalError('ACE is busy filling or loading. Try again when it finishes.')
        async with self.session.lock:
            page = await self.session.background(PATH)
            for i, day in enumerate(days, start=1):
                on_progress(f'Checking {day.strftime("%a %d %b")}', f'{i} of {len(days)}', 'search')
                stamp = datetime.now(timezone.utc).isoformat()
                try:
                    await set_report_date(page, day.isoformat())
                    await self.portal.check_date(page, day.isoformat())
                    rows = await self.portal.grid(page)
                    entry = {'minutes': saved_minutes(rows), 'rows': len(rows), 'checkedAt': stamp}
                except PortalError as exc:
                    entry = {'error': str(exc), 'checkedAt': stamp}
                cache = read_json(CACHE, {})
                cache[day.isoformat()] = entry
                write_json(CACHE, cache)
                if 'error' in entry:
                    on_progress(f'Could not read {day.strftime("%d %b")}', entry['error'], 'warn')
        return len(days)
