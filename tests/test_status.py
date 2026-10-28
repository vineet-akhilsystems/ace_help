from datetime import date
from backend.app_status import classify, dates_to_scan, month_days, saved_minutes

FULL = [{'total': '02:55'}, {'total': '02:55'}, {'total': '02:55'}, {'total': '00:30'}, {'total': '00:15'}]
TODAY = date(2026, 9, 29)


def test_saved_minutes_sums_total_column():
    assert saved_minutes(FULL) == 570
    assert saved_minutes([{'total': ''}, {'total': 'bad'}]) == 0


def test_full_day_is_filled():
    result = classify(date(2026, 9, 22), 570, None, False, TODAY)
    assert result['status'] == 'filled' and result['savedHours'] == '09:30'


def test_zero_hours_is_not_filled():
    assert classify(date(2026, 9, 21), 0, None, False, TODAY)['status'] == 'missing'


def test_under_nine_hours_needs_attention():
    result = classify(date(2026, 9, 21), 350, None, False, TODAY)
    assert result['status'] == 'partial' and '05:50' in result['reason']


def test_unsaved_app_draft_is_still_missing():
    # ACE has 0 hours; an old unsaved draft must not look like an existing entry.
    event = {'event': 'filled_not_saved', 'at': '2026-09-21T12:00:00+00:00'}
    result = classify(date(2026, 9, 21), 0, event, False, TODAY)
    assert result['status'] == 'missing' and 'never saved' in result['reason']


def test_interrupted_fill_is_failed():
    event = {'event': 'interrupted', 'at': '2026-09-21T12:00:00+00:00', 'detail': 'ACE grid structure changed.'}
    result = classify(date(2026, 9, 21), 0, event, False, TODAY)
    assert result['status'] == 'failed' and 'grid structure' in result['reason']


def test_saved_rows_beat_old_audit_problems():
    event = {'event': 'interrupted', 'at': '2026-09-21T12:00:00+00:00', 'detail': 'x'}
    assert classify(date(2026, 9, 21), 570, event, False, TODAY)['status'] == 'filled'


def test_leave_weekend_and_future():
    assert classify(date(2026, 9, 21), 0, None, True, TODAY)['status'] == 'leave'
    assert classify(date(2026, 9, 26), 0, None, False, TODAY)['status'] == 'missing'
    assert classify(date(2026, 9, 27), 0, None, False, TODAY)['status'] == 'weekend'
    assert classify(date(2026, 9, 30), 0, None, False, TODAY)['status'] == 'future'


def test_month_days_stop_at_today():
    days = month_days('2026-09', TODAY)
    assert days[0] == date(2026, 9, 1) and days[-1] == TODAY
    assert date(2026, 9, 26) in days and all(d.weekday() < 6 for d in days)
    assert month_days('2026-10', TODAY) == []


def test_refresh_skips_old_green_days_only():
    days = month_days('2026-09', TODAY)
    cache = {d.isoformat(): {'minutes': 570, 'rows': 5} for d in days}
    cache['2026-09-02'] = {'minutes': 0, 'rows': 0}
    cache['2026-09-04'] = {'error': 'grid missing'}
    del cache['2026-09-07']
    leave = {'2026-09-03'}
    chosen = dates_to_scan(days, cache, leave, full=False)
    assert date(2026, 9, 1) not in chosen and date(2026, 9, 3) not in chosen
    assert {date(2026, 9, 2), date(2026, 9, 4), date(2026, 9, 7)} <= set(chosen)
    assert days[-5:] == chosen[-5:]
    assert dates_to_scan(days, cache, leave, full=True) == [d for d in days if d != date(2026, 9, 3)]


def test_scan_error_is_not_checked():
    result = classify(date(2026, 9, 21), None, None, False, TODAY, error='Unexpected ACE grid columns.')
    assert result['status'] == 'unchecked' and 'Unexpected' in result['reason']
    assert classify(date(2026, 9, 21), None, None, False, TODAY)['status'] == 'unchecked'


def test_read_audit_keeps_latest_fill_event(tmp_path):
    import json
    from backend.app_status import read_audit
    log = tmp_path / 'audit.jsonl'
    lines = [{'at': '2026-09-21T10:00:00+00:00', 'event': 'interrupted', 'plan': {'date': '2026-09-21'}, 'detail': 'x'},
             {'at': '2026-09-21T11:00:00+00:00', 'event': 'row_verified', 'plan': {'date': '2026-09-21'}},
             {'at': '2026-09-21T12:00:00+00:00', 'event': 'filled_not_saved', 'plan': {'date': '2026-09-21'}},
             {'at': '2026-09-21T12:00:00+00:00', 'event': 'task_filled_not_saved', 'task': {}}]
    log.write_text('\n'.join(json.dumps(l) for l in lines) + '\nnot json\n', encoding='utf-8')
    assert read_audit(log) == {'2026-09-21': lines[2]}


def test_zero_hour_ace_auto_rows_are_ignored():
    from backend.app_timesheet import parse_grid
    auto = ['1', 'Augastam (New Product)', 'Bug', 'Augastam ai', 'Office', '"ASPL-169999" In the API', '11:57PM', '11:57PM', '00:00', 'Edit', 'Remove']
    real = ['1', 'Augastam (New Product)', 'New Requirement', 'Augastam ai', 'Office', 'Fixed bugs', '10:00AM', '7:30PM', '09:30', 'Edit', 'Remove']
    assert parse_grid([auto]) == []
    rows = parse_grid([real, auto])
    assert len(rows) == 1 and rows[0]['start'] == '10:00' and rows[0]['end'] == '19:30'
