# Timesheet status dashboard — design

Date: 2026-09-29 · Status: draft for review

## Goal

When the app opens, show at a glance how much of the ACE daily task report is filled: how many working days are
filled, which are still pending, and which have a problem. A month calendar colours every working day; clicking a day
opens the Timesheet tab with that date selected so it can be planned and filled straight away.

## What the user said vs. assumptions

Said: landing page after "login"; counts of filled vs pending; calendar that marks not filled / filled but something
is off / could not fill; click a date to go and fill it. Data source: check each day's ACE timesheet page (option A).

Assumed (change here if wrong):
- The app has no login of its own, so "after login" means the dashboard is the default first tab.
- Only Monday–Friday count, matching `working_dates`. Weekends are shown greyed and never counted.
- The full-day target is 9 hours, matching the fill checks.
- Holidays and leave are unknown to ACE, so the user can mark a day as leave locally; leave days are not counted as pending.
- Nothing is ever written to ACE by the dashboard. It only reads.

## Day statuses

| Status | Colour | Rule |
|---|---|---|
| Filled | green | ACE grid for the date has saved rows totalling ≥ 9:00 |
| Needs attention | amber | Saved rows total < 9:00, **or** the audit log has `filled_not_saved` for the date but ACE shows no saved rows (draft was filled and never saved) |
| Not filled | red | Working day, today or earlier, no saved rows, no audit fill |
| Could not fill | dark | Latest audit event for the date is `interrupted` and ACE shows no saved rows |
| Leave | blue outline | Marked as leave by the user |
| Not checked | striped grey | Never scanned yet |
| Future / weekend | muted | Not counted |

Each day card keeps the reason text, e.g. "Saved 6:30 of 9:00", "Filled by the app on 24 Sep but not saved in ACE",
"Stopped: ACE grid structure changed".

## Architecture

### Backend

New module `backend/app_status.py` (one purpose: work out day statuses).

- `classify(day, rows, audit_events, leave) -> dict` — pure function, no browser. Returns
  `{date, status, savedHours, rowCount, reason, checkedAt}`. Unit tested.
- `read_audit(day_from, day_to)` — reads `runtime/audit.jsonl`, keeps the latest relevant event per date.
- `StatusScanner(session)`:
  - `scan(dates)` opens **one** ACE timesheet tab, and for each date calls the existing `set_report_date` and
    `Timesheets.grid` (reused, not copied), sums row totals, classifies, and writes to the cache after each day so a
    stopped scan keeps what it found. Closes the tab when done. Holds `session.lock` so it never runs at the same time
    as a fill.
  - Reports progress per day through the same `on_progress` style used by planning.
- Cache `runtime/status_cache.json`: `{ "YYYY-MM-DD": {status fields…} }`. Leave marks in
  `runtime/leave_days.json`.

Which dates a refresh scans (keeps it fast after the first run):
- Days never scanned, plus
- days not green or leave, plus
- the last 5 working days (recent saves or edits).
Green days older than that are trusted from the cache. A "Rescan whole month" button forces every day.

New endpoints in `backend/main.py` (same local-only header rules as the others):
- `GET /status?month=YYYY-MM` — cached statuses for the month plus audit-derived hints, instant, no browser.
- `POST /status/refresh-stream` `{month, full: bool}` — server-sent events: one `step` per day, then `result`.
  Rejects months after the current month.
- `POST /status/leave` `{date, leave: bool}` — toggles a local leave mark.

### Frontend

New `frontend/src/dashboard.jsx`, added as the first tab **Dashboard** in the existing mode switch
(`Root` in `main.jsx`; remembered mode still wins if the user last chose another tab).

Layout, top to bottom:
1. **Summary row**: Working days so far this month · Filled · Needs attention · Not filled · Could not fill, plus a
   progress bar (filled ÷ working days so far). "Last checked" time and a **Check ACE** button.
2. **Oldest pending first** list: up to 5 red/amber/dark days with their reason and a **Fill this day** button.
3. **Month calendar** with previous/next month arrows. Each cell shows the day number, a colour, and saved hours.
   Clicking a cell opens a small panel with the reason and buttons **Fill this day** and **Mark as leave / Undo leave**.
4. While a scan runs: a progress line ("Checking 17 Sep… 12 of 21") using the existing step list styling.

**Fill this day**: switches to the Timesheet tab and sets its work date (single-day mode). `App` receives the date
through a small prop/callback from `Root`, so no global state is added.

On open the dashboard shows the cached month immediately; it does not start a browser scan by itself, because a scan
opens a visible ACE window. If nothing is cached it shows "Not checked yet — Check ACE".

## Errors

- ACE login expired or grid missing: scan stops, days already checked stay saved, the error is shown with a Retry.
- A fill is running: refresh returns 409 "ACE is busy filling a day. Try again when it finishes."
- Unexpected grid layout on one date: that date is marked "Not checked" with the message; the scan continues.

## Testing

- `tests/test_status.py`: `classify` for every row in the status table, the < 9 h amber case, the audit
  `filled_not_saved` / `interrupted` cases, leave, weekends, future dates; `read_audit` picks the latest event; the
  refresh date-selection rule.
- `tests/test_api.py`: `/status` month validation, local-header requirement, leave toggle round trip.
- `frontend/src/dashboard.test.js`: summary counts and oldest-pending ordering from a sample status map.
- Manual: one real refresh for September against ACE in the visible browser.

## Out of scope

- Writing or saving anything in ACE.
- Ticket status tracking on the dashboard.
- The Employee Wise Report export (option B).
- Official holiday calendars; leave is marked by hand.
