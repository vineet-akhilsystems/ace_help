---
name: driving-ace-portal
description: Use when exploring, probing or automating any ACE page (ace.akhilsystems.com) — TaskPageN tasks/tickets, TimeSheet daily task report, menus, Telerik dropdowns, grids — or when an ACE selector, option text or page behaviour is unknown.
---

# Driving the ACE portal

## Overview

ACE is the user's real company portal (ASP.NET WebForms + Telerik + UpdatePanels). Look first, read-only; write
only through the app's existing fill/save paths. Full element ids, option lists and menu URLs:
`docs/ace-portal-reference.md` (facts marked observed / from code / inferred).

## Read-only probing

This logs in to the real ACE with the user's `.env` credentials (network needed) but changes nothing.

```python
import asyncio, sys; sys.path.insert(0, '.')
from backend.app_session import Session
from backend.app_tasks import PATH, T          # '/Tasks/TaskPageN.aspx?Mpg=P171', 'ctl00_ContentPlaceHolder1_Tasks1_'
from backend.app_timesheet import settle
async def main():
    s = Session(); page = await s.background(PATH)     # headless, logs in from .env
    await page.locator('#' + T + 'btnNewTask').click(); await settle(page)
    print(await page.evaluate('(p) => document.getElementById(p + "txtKeyword").maxLength', T))
    await page.close(); await s.close()
asyncio.run(main())
```

`runtime/portal_dump/scripts/probe.py` is a reusable harness that aborts any POST naming Save/Update/Delete/Add.

## Facts that bite

| Fact | Consequence |
|---|---|
| `btnSent` = **Assigned** view (`gvTasks`, 16 cols); `btnPosted` = **Sent** view (`grvPosted`, 14 cols) | names are swapped; column indexes differ per grid |
| "Select" in the **Sent** grid hangs and locks the ACE session ~1–2 min (all browsers sharing the cookies) | never click it |
| After "Select" in Assigned, `Save` becomes **"Update"** on that ticket | before creating: `btnNewTask`, then `hdnTaskId == '0'` and Save = "Save & Leave Open" (enforced in `save_page`) |
| Task Type defaults to **Bug**; Target Date, Effort, Assign To have no client validator | always set them explicitly |
| Missing required fields → a browser `alert()` listing them | handle `page.on('dialog')` |
| Keyword `maxLength` 25; text cut silently | keep ≤ 25 |
| Option texts carry stray/double spaces; "NABH" exists twice | snap to exact text; use values when ambiguous |
| Assigned search: 10 rows/page via `Page$N`, record counter wrong, duplicates, date range defaults to 30 days | page by links, de-duplicate, set the dates |
| Menu module choice is server-side session state | navigate by URL (Mpg codes in the reference) |
| Timesheet loads zero-length rows for tickets (`hdnRowId=0`); real saved rows have a real `hdnRowId` | judge "saved" by `hdnRowId` |
| Telerik widgets | set via `set_widget` / `window.$find(id)`, then `await settle(page)` |

## Never

Click Save/Update/Delete/Approve while exploring; type into a form and submit; print credentials or cookies; write
probe dumps outside `runtime/` (gitignored).
