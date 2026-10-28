from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def today_ist() -> date:
    return datetime.now(ZoneInfo('Asia/Kolkata')).date()


def is_working_day(day: date) -> bool:
    # Monday to Saturday are working days; only Sunday is off.
    return day.weekday() != 6


def workplace(day: date) -> str:
    return 'Home' if day.weekday() == 4 else 'Office'


def minutes(value: str) -> int:
    hour, minute = map(int, value.split(':'))
    return hour * 60 + minute


def clock(value: int) -> str:
    return f'{value // 60:02d}:{value % 60:02d}'


def working_dates(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)
            if is_working_day(start + timedelta(days=i))]


def allocate(durations: list[int | None], target_minutes: int = 555) -> list[tuple[str, str]]:
    if not 1 <= len(durations) <= 40:
        raise ValueError('Provide between 1 and 40 tasks.')
    if any(d is not None and (type(d) is not int or d <= 0) for d in durations):
        raise ValueError('Durations must be positive whole minutes.')
    known = sum(d or 0 for d in durations)
    missing = durations.count(None)
    if not 540 <= target_minutes < 570 or known + missing >= 570:
        raise ValueError('Daily time must be at least 09:00 and below 09:30.')
    target = max(target_minutes, known + missing)
    allocated = list(durations)
    if missing:
        share, extra = divmod(target - known, missing)
        for i, duration in enumerate(allocated):
            if duration is None:
                allocated[i] = share + (1 if extra else 0)
                extra = max(0, extra - 1)
    else:
        allocated[-1] += target - known
    cursor = 585
    rows = []
    for duration in allocated:
        rows.append((clock(cursor), clock(cursor + duration)))
        cursor += duration
    return rows


def allocate_natural(durations: list[int | None], descriptions: list[str] | None = None,
                     target_minutes: int = 555) -> list[tuple[str, str]]:
    if not 1 <= len(durations) <= 40:
        raise ValueError('Provide between 1 and 40 tasks.')
    if any(d is not None and (type(d) is not int or d <= 0) for d in durations):
        raise ValueError('Durations must be positive whole minutes.')
    missing_indices = [i for i, d in enumerate(durations) if d is None]
    if not missing_indices:
        return allocate(durations, target_minutes)
    known = sum(d or 0 for d in durations)
    if not 540 <= target_minutes < 570 or known + len(missing_indices) >= 570:
        raise ValueError('Daily time must be at least 09:00 and below 09:30.')
    if known + len(missing_indices) * 15 >= 570:
        return allocate(durations, target_minutes)
    target = max(target_minutes, known + len(missing_indices) * 15)
    remaining = target - known
    remaining_blocks = remaining // 15
    rem_minutes = remaining % 15
    if remaining_blocks < len(missing_indices):
        return allocate(durations, target_minutes)

    heavy_kw = ('develop', 'coding', 'implement', 'fix', 'bug', 'resolv', 'investigat',
                'schema', 'architect', 'build', 'creat', 'migrat', 'optim')
    light_kw = ('meet', 'call', 'sync', 'demo', 'standup', 'guidance', 'mentor',
                'discuss', 'review', 'feedback', 'document')
    weights = []
    for i in missing_indices:
        desc = (descriptions[i] if descriptions and i < len(descriptions) else '').lower()
        if any(k in desc for k in heavy_kw):
            weights.append(1.35)
        elif any(k in desc for k in light_kw):
            weights.append(0.75)
        else:
            weights.append(1.0)
    if len(set(weights)) == 1 and len(weights) > 1:
        variation_profiles = {
            2: [1.15, 0.85],
            3: [1.2, 1.0, 0.8],
            4: [1.15, 1.05, 0.95, 0.85],
            5: [1.2, 1.05, 0.85, 0.9, 1.0],
            6: [1.15, 1.05, 0.95, 0.9, 0.95, 1.0],
            7: [1.15, 1.05, 1.0, 0.9, 0.95, 0.95, 1.0],
        }
        var = variation_profiles.get(len(weights))
        if var:
            weights = [w * v for w, v in zip(weights, var)]
    tot_w = sum(weights)
    min_b = 2 if remaining_blocks >= len(missing_indices) * 2 else 1
    blocks = [max(min_b, round((w / tot_w) * remaining_blocks)) for w in weights]
    diff = remaining_blocks - sum(blocks)
    while diff != 0:
        if diff > 0:
            idx = max(range(len(blocks)), key=lambda i: (weights[i], -blocks[i]))
            blocks[idx] += 1
            diff -= 1
        else:
            candidates = [i for i in range(len(blocks)) if blocks[i] > min_b]
            if not candidates:
                candidates = list(range(len(blocks)))
            idx = max(candidates, key=lambda i: blocks[i])
            blocks[idx] -= 1
            diff += 1
    allocated = list(durations)
    for idx, b in zip(missing_indices, blocks):
        allocated[idx] = b * 15
    if rem_minutes:
        allocated[missing_indices[-1]] += rem_minutes
    cursor = 585
    rows = []
    for d in allocated:
        rows.append((clock(cursor), clock(cursor + d)))
        cursor += d
    return rows


def validate_day(plan) -> None:
    if plan.workplace != workplace(plan.date):
        raise ValueError('Workplace must be Home on Friday and Office otherwise.')
    cursor = minutes(plan.tasks[0].start)
    first = cursor
    if not 585 <= first <= 600:
        raise ValueError('The first task must start between 09:45 and 10:00.')
    for task in plan.tasks:
        start, end = minutes(task.start), minutes(task.end)
        if start != cursor or end <= start:
            raise ValueError('Tasks must have positive duration and be contiguous without gaps or overlaps.')
        cursor = end
    if not 540 <= cursor - first < 570 or plan.totalHours != clock(cursor - first):
        raise ValueError('Total hours must match the rows and be at least 09:00 but below 09:30.')
