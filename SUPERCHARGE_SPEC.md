# Supercharge Spec — ACE Timesheet Voice Automator

**Owner:** Vineet Kukreti · **Status:** Spec (approved to build after sign-off) · **Date:** 2026-09-23

One-liner: **You describe your day (any date, or a date range); the app fills every task row directly in the ACE portal — dropdowns, descriptions, dates, times — and stops. You review the filled grid and click Save yourself.**

> **SAVE POLICY (hard rule):** The app **NEVER clicks Save.** It fills all rows into the ACE grid for the given date(s) and leaves them there, ready. **You** are the only one who reviews and submits. There is no auto-save, no "confirm to save" step performed by the app.

Companion docs: `ACE_Timesheet_Documentation.md` (site map + options), `TECHNICAL_ARCHITECTURE.md` (deep tech).

---

## 1. Goals & non-goals

**Goals**
- From one spoken/typed overview of a day, fill **all** tasks for that day into the ACE grid — every field, ordered and timed sensibly — ready for you to review.
- Support **any date** and a **date range** ("fill 1 Sep to 22 Sep").
- Never produce an invalid entry (wrong option, < 9h, end > 19:30, missing field).
- **The app never saves.** It fills and stops; you review and submit.

**Non-goals (v1)**
- Managing other people's timesheets.
- Full ticket lifecycle management (ticket status update is an optional stretch).
- Auto-submitting/saving anything.

---

## 2. Users & the core scenario

Single user (you). Two request shapes:

**A. Single day** — *"Open 22 September. I worked on task A, then B, then C, then D."*
1. You give the date + a brief overview of everything you did that day (in any order, with or without durations).
2. The app **orders the tasks logically**, **assigns sensible contiguous times itself** (start 09:45–10:00, total ≥ 9h, end ≤ 19:30), writes each description, applies the workplace rule, and tags any matching assigned ticket.
3. The app **fills every task as a row in the ACE grid** for that date (one **Add Row** per task) and **stops**.
4. **You review the filled grid and click Save.** The app never saves.

**B. Date range** — *"Fill tasks from 1 September to 22 September."*
- You provide what was done (per day, or a general description the app distributes). The app iterates each working date in the range, fills that day's grid, and stops — leaving each day for you to review and save.
- **Range day rule (locked): SKIP Saturday and Sunday** — you fill weekends separately. So a range fills **Mon–Fri only** (Fri as Home, Mon–Thu as Office).

**Timing is the app's job.** You just say what you did (e.g. "A, then B, then C, then D"); the app decides order and clock times so the day is valid and sums to ≥ 9 hours (never less), starting ~09:45–10:00. If you give durations, it honors them and pads to reach ≥ 9h; if not, it splits the day evenly.

---

## 3. Fixed rules (source of truth)

| Rule | Value |
|---|---|
| Client (always) | `Augastam (New Product)` |
| Module (always) | `Augastam ai` |
| Task Name (ALWAYS) | `New Requirement` — fixed for every entry, no exceptions |
| Work Place | `Home` if day == Friday, else `Office` |
| Day start | 09:45–10:00 (picker default 10:00) |
| Timezone | IST (Asia/Kolkata) — all dates/"today" |
| Existing entries | if date already has entries → **do not fill, notify user** |
| Date range | Mon–Fri only (skip Sat & Sun) |
| Voice input | included in v1 (mic from day one) |
| Day end | > 19:00 and ≤ 19:30 |
| Total hours | ≥ 9:00 (target ~9:30) |
| Description | ≤ 500 chars, professional prose |
| Save | only on explicit user confirm |

**Time engine:** if durations given → chain contiguously from 09:45, pad last task to land end in 19:00–19:30. If no durations → split 09:45→19:15 evenly across N tasks. Rows are contiguous (no gaps/overlap).

### 3.1 Ticket handling (clarified)

- Every entry uses Task Name `New Requirement` regardless of whether it has a ticket.
- At plan time the app **fetches your Assigned tickets** (`Tasks/TaskPageN.aspx`) — Ticket No, Module, Task Type, Status, Description.
- For each spoken task, the app tries to **match it to one of your assigned tickets** (by ticket number if you say one, else by semantic similarity of the description).
  - **Match found** → tag the row with `ASPL-XXXXXX` in the description (prefix, e.g. `[ASPL-169999] ...`). Ticket status (Open/Completed/anything) does **not** matter — just mention it.
  - **No match** → this is a **no-ticket task**; that is normal and fully valid. Leave it untagged. (Many tasks will be like this.)
- One task maps to **zero or one** ticket. Matching is a suggestion shown in the preview; you can add/remove/change the tag before confirming.
- Ticket matching never blocks or alters the timesheet fill — it only decorates the description.

---

## 4. System components

| Component | Tech | Responsibility |
|---|---|---|
| UI | **React JS** | mic capture, live transcript, editable preview table, confirm/save |
| API | **Python FastAPI** | orchestration, holds all secrets |
| STT | **Sarvam `saaras:v3`** | audio → transcript |
| Descriptions | **Gemini `gemini-3.5-flash`** | transcript slice → ≤500-char description |
| Decisions | **Jev (TypeSafe System One)** | ticket matching (`choice`/rerank over my assigned tickets + `noul` "does this task match this ticket?"), multi-task segmentation `noul`, post-fill verify `noul` |
| Rules/math | **Python** | times, workplace, validation (never an LLM) |
| Browser | **Playwright (Python, Chromium)** | drive ACE via Telerik client API; session reuse |

**LLM/code split (non-negotiable):** LLMs decide & generate; Python owns every rule, time calculation, and the click execution.

---

## 5. Data model

```
DayPlan {
  date: "YYYY-MM-DD"
  workplace: "Office" | "Home"        # derived
  totalHours: "HH:MM"                  # derived, must be >= 09:00
  tasks: Task[]
}
Task {
  client: "Augastam (New Product)"     # fixed
  module: "Augastam ai"                # fixed
  taskName: "New Requirement"          # fixed, always
  description: string (<=500)          # Gemini
  start: "HH:MM"                       # rules engine
  end: "HH:MM"                         # rules engine
  ticket?: "ASPL-XXXXXX"               # regex from transcript
}
```

---

## 6. API contract

| Method | Path | In | Out |
|---|---|---|---|
| POST | `/transcribe` | audio blob | `{transcript}` |
| POST | `/plan` | `{transcript, date}` | `DayPlan` |
| POST | `/plan-range` | `{fromDate, toDate, notes}` | `DayPlan[]` |
| POST | `/fill` | `DayPlan` or `DayPlan[]` | fills ALL rows into ACE grid per date (Add Row each), returns `{screenshotUrl, gridRows}` — **never saves** |
| GET | `/tickets` | — | assigned tickets |
| POST | `/ticket/update` | `{ticket,status,remarks}` | `{status}` — **[DECISION #2: stretch]** |

`/plan` = fetch assigned tickets + Python regex (explicit ticket numbers) + Jev (segmentation + ticket matching, batched) + Gemini (per-task description) + rules engine. `GET /tickets` is called inside `/plan`; also exposed for the preview UI.

---

## 7. ACE integration facts (validated 2026-09-23)

- Timesheet: `TimeSheet.aspx?Mpg=P3`. IDs: `ddlClientName`, `ddlTaskName`, `ddlModule`, `ddlWorkPlace`, `RadTimeFrom`, `RadTimeEnd`, `RadReportDate` (all `ctl00_ContentPlaceHolder1_` prefixed), `txtTaskDescription`; buttons **Add Row**, **Save**.
- **Proven:** combos set via `$find(id).findItemByText(text).select()`; times via `$find(id).set_selectedDate(date)`; ACE auto-computed Total Hours = 09:30 for 09:45→19:15. ✅
- Session: login once → persist `storage_state.json` → reuse. Wait on Telerik `PageRequestManager.endRequest` between actions, not `sleep`.
- Tickets: `Tasks/TaskPageN.aspx` — Assigned/Sent/New Task; **Select** opens Update (status dropdown → Completed + Employee Remarks → **Update**); New Task has 188-person assign checklist.

---

## 8. Acceptance criteria

1. Describing one multi-task day produces correct task count, **logically ordered** tasks, contiguous times, start ~09:45–10:00, total ≥9h, end ≤19:30 — filled into the ACE grid.
2. Workplace = Office Mon–Thu/Sat, Home Fri — automatically.
3. Every dropdown value is a real ACE option (zero invalid selections).
4. Descriptions ≤500 chars, readable, no invented facts.
5. `/fill` adds every task as a grid row in ACE for the correct date and **stops — the app never clicks Save**; you review and submit.
8. A date range fills each Mon–Fri day's grid (skips Sat/Sun), leaving all ready for your review.
9. If a date already has entries, the app does NOT fill it — it reports that date back to you instead.
6. Spoken ticket numbers (e.g. "169999") are validated against your assigned-ticket list, normalized to `ASPL-169999`, and tagged; unmatched tasks stay untagged (no-ticket, valid).
7. Secrets never reach the browser client.

---

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Telerik postback repopulates Module after Client | wait on `endRequest`; set Module after Client |
| Viewstate/session expiry | detect login redirect → re-login → retry |
| STT mishears ticket numbers | show in preview for edit; regex + confirm |
| Over-eager ticket tagging | Jev confidence threshold; below it = no-ticket; preview shows/removes tag |
| Accidental save | app has NO save capability at all — Save is physically only reachable by the user in the ACE UI |
| Total < 9h edge cases | rules engine hard-validates before `/fill`; block if invalid |

---

## 10. Milestones (build order — not started yet)

1. **M1 — Playwright fill** (hardcoded DayPlan): session reuse + fill today's row reliably, no save. *(fast-fill already proven manually)*
2. **M2 — rules.py**: time engine + workplace + validation, with unit tests.
3. **M3 — Jev**: task-name choice + multi-task/ticket noul (batched).
4. **M4 — Gemini**: description writer + 500-char guard.
5. **M5 — FastAPI**: wire `/plan`, `/fill`, `/save`, `/tickets`.
6. **M6 — React**: overview input + editable preview + "Fill in ACE" button (NO save button — save happens in ACE by you).
7. **M7 — Sarvam**: mic → transcript.
8. **M8 (stretch)**: ticket status auto-update.

---

## 11. Open decisions (need your call before M3)

1. ~~Bug work~~ → **RESOLVED: Task Name is always `New Requirement`.**
2. ~~Ticket auto-update~~ → **RESOLVED: v1 is timesheet-only. Ticket status update is DEFERRED to a later version (see §14).**

**All decisions resolved. Spec is final and ready to build.**
3. ~~v1 input~~ → **RESOLVED: mic from day one (v1 includes voice).**
4. ~~Duplicate day~~ → **RESOLVED: if the date already has entries in ACE, do NOT fill — stop and notify the user; user rectifies in ACE.**
5. ~~Timezone~~ → **RESOLVED: "today" = IST.**
6. ~~Date range day-skipping~~ → **RESOLVED: skip Saturday & Sunday** (filled separately by you); range = Mon–Fri only.

---

## 13. Critical review — important things previously missing

Reviewed the plan critically; these matter and are now in scope:

1. **Duplicate-day protection (LOCKED).** Before filling any date, the app **reads the current grid for that date**. If entries already exist, the app **does NOT fill** — it **stops and notifies you** with what it found (so you rectify in ACE). It never appends or overwrites existing entries. For a date range, it skips such days and lists them in the summary.
2. **"Today" timezone (LOCKED).** Target date is always computed in **IST**, so the date field and the Fri=Home/weekday=Office rule are correct even near midnight.
3. **Ticket matching confidence.** Semantic matching can over-eager-tag. Use a Jev confidence **threshold**; below it, treat the task as no-ticket rather than guessing. Always show the match (and why) in the preview for one-click removal. Never invent a ticket number the STT didn't produce or that isn't in your assigned list.
4. **STT number reliability.** Ticket numbers spoken aloud ("one six nine nine nine nine") are error-prone. Regex-extract candidates, **validate against your actual assigned-ticket list**, and surface them for confirmation — don't trust a raw transcript number.
5. **Hard validation gate before fill.** The rules engine must **refuse** to hand a DayPlan to Playwright unless: total ≥ 9:00, end ≤ 19:30, start ≥ 09:45, rows contiguous, every field non-empty, each description ≤ 500 chars. Fail loud in the preview, don't half-fill ACE.
6. **Partial-fill / crash recovery.** If Playwright dies mid-day (e.g. after 2 of 3 Add Rows), the app should detect already-added rows and resume, not restart and duplicate.
7. **Session expiry mid-run.** Detect redirect-to-login, re-login from `.env`, retry the failed step once.
8. **Language mix.** You may dictate Hindi/English mixed; Sarvam `saaras:v3` handles it, but Gemini must always output a **professional English** description. State this in the Gemini prompt.
9. **No-ticket tasks are first-class.** The UI and matching must treat "no ticket" as a normal, common outcome — not an error or a blank to fill.
10. **Secrets hygiene.** `.env` (ACE password + 3 API keys) must be `.gitignore`d and only read server-side; the React bundle must never embed any key. (Flagged because the ACE password sits in plaintext in `.env`.)
11. **Description grounding.** Gemini must only rephrase what you said — never add fabricated tasks/detail to pad 500 chars. Short is fine.
12. **Audit trail.** Log each saved DayPlan (date, tasks, times, tickets) locally so you can prove/repeat what was submitted.

---

## 14. Deferred to a later version (DO NOT FORGET)

These are intentionally **not** in v1, but are committed for the future — keep them on the roadmap:

1. **Ticket status auto-update.** When you say you finished a ticket, the app opens `Tasks/TaskPageN.aspx` → **Select** the ticket → set **Change Task Status → Completed/Delivered** → fill **Employee Remarks** → click **Update**. (Flow already explored and documented in `ACE_Timesheet_Documentation.md` §Update Task and `TECHNICAL_ARCHITECTURE.md`.) This is milestone **M8**.
2. Possible later: create/assign new tickets, multi-day analytics, mobile.

v1 scope = **timesheet fill only** (voice → ordered/timed rows in the ACE grid, no save, no ticket writes).

---

## 12. Out of scope for v1
Multi-day backfill, analytics/reporting, mobile app, multi-user, offline mode.
```
```
