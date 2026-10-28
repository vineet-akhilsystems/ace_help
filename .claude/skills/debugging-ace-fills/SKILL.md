---
name: debugging-ace-fills
description: Use when filling or saving in ACE goes wrong — "ACE did not keep: …", "Stopped after a problem", "Check this ACE tab", a day skipped, a ticket number not found, the New Task form not opening, session expired — or when the user sends a screenshot of an ACE tab.
---

# Debugging ACE fills

## Overview

Every fill and save is checked against what ACE kept, logged, and screenshotted. Start from the evidence, then probe
ACE read-only. **REQUIRED:** use superpowers:systematic-debugging for anything not in the table below.

## Evidence

| Source | What it holds |
|---|---|
| `runtime/audit.jsonl` | one JSON line per event: `at`, `event`, `task`/plan, `detail`, `submitted`. Timesheet events: `before_add`, `row_verified`, `filled_not_saved`, `skipped_existing`, `interrupted`. Ticket events: `task_filled_not_saved`, `task_interrupted`, `task_saved`, `task_save_unconfirmed` (`detail` holds ACE's reply) |
| `runtime/*.png` | screenshots (`YYYY-MM-DD-<hash>.png` per day, `task-<hash>.png` per ticket, taken just before Save); served at `/screenshots/<name>` |
| backend console | `[ACE Assistant] [TAB]`, `[TASK] Filling/Saving task N`, `[TICKETS]`, `[BROWSER]` lines |
| `runtime/ace_task_form.json`, `runtime/tickets_cache.json` | cached ACE option lists and the user's Assigned tickets |

Read the last lines of the audit with a short Python script that prints `at`, `event`, `detail` and
`task['keyword']` (tickets) or the plan date (timesheets). "Ticket N" in the UI is the card number; match it to the
audit by keyword and time, since the audit stores no card number. No audit file, or no line for that ticket, means
the app never reached ACE for it.

## Known messages

| Message | Usual cause | Fix |
|---|---|---|
| `ACE did not keep: keyword` | ACE Keyword max 25 chars, text cut | `short_keyword`; draft check rejects > 25 |
| `ACE did not keep: client` / `module` | ACE option text has extra spaces or changed | `snap` to exact option text; "Refresh from ACE" re-reads options |
| `ACE did not keep: targetDate (visible)` | RadDateTimePicker text not typed | `fill_page` types `dd/mm/YYYY HH:MM` then Tab |
| `ACE did not keep: assignTo` | another employee ticked or name mismatch | `ACE_ASSIGNEE` must equal the label exactly |
| `Check this ACE tab` (unconfirmed) | Save clicked, no "Saved"/number seen (validation stopped it?) | look at the tab; **do not retry before checking Assigned** — retry could duplicate |
| `Skipped — this date already has entries` | the day's grid already has rows | user clears them in ACE first; never overwrite |
| `ACE session expired` | login cookie stale | `Session.login` re-logs in; ACE's login form needs two submits |
| ticket saved but no ASPL number | ACE shows only "Saved" | `match_new_tickets` finds it by description in the Assigned list |

## Probing ACE

Use the headless reader to look without writing:
`page = await Session().background('/Tasks/TaskPageN.aspx?Mpg=P171')`, then `page.evaluate(...)` to read values,
`maxLength`, labels. Never click Save/Submit while investigating. Field ids: see `docs/ace-portal-reference.md`.

## Before telling the user it's fixed

Reproduce the failure in a test (e.g. a draft that ACE would cut), fix, rerun tests per file, and tell the user to
restart the backend and check their Assigned list for anything saved during the failed run.
