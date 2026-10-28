# ACE Timesheet Automator — Technical Architecture

**Goal:** Press a mic, speak your day → the system transcribes, understands, splits into tasks, computes times, writes 500-char descriptions, fills the ACE timesheet in the browser, shows a preview, and saves on your confirm.

**Stack (as chosen):**
- **Frontend:** React JS (mic capture + preview/confirm UI)
- **Backend:** Python **FastAPI**
- **Speech-to-text:** **Sarvam** `saaras:v3` (`SARVAM_API_KEY`)
- **Text generation:** **Gemini** `gemini-3.5-flash` (`GEMINI_API_KEY`) — polishes task descriptions
- **Decisions / routing:** **Jev** (TypeSafe System One, `JEV_API_KEY`) — fast typed yes/no · choice · score
- **Browser automation:** **Playwright (Python, Chromium)** against the ASP.NET/Telerik site
- Secrets live in `.env`, loaded server-side only. **Never sent to the React client.**

> Security note: `.env` holds the ACE login + 3 API keys. The backend reads them; the frontend never sees them. Add `.env` to `.gitignore`.

---

## 1. High-level flow

```
[React mic] --audio--> FastAPI /transcribe --Sarvam--> raw transcript
                           |
                           v
                 FastAPI /plan  ──► Jev (segment + classify + decide)
                           |        Gemini (write ≤500-char descriptions)
                           |        Python rules (times, workplace, ≥9h)
                           v
                 structured DayPlan (JSON) ──► React preview (editable)
                           |
                    user confirms
                           v
                 FastAPI /fill ──► Playwright drives ACE ──► screenshot back
                           |
                    user confirms Save
                           v
                 FastAPI /save ──► Playwright clicks Save
```

Division of labor (the key design principle): **LLMs decide/generate; Python owns rules, math, and execution.**

| Concern | Who | Why |
|---|---|---|
| Split dictation into N tasks | **Jev** (noul: "multiple tasks?") + code splitter | calibrated, fast |
| Pick Task Name from 24 options | **Jev** (choice) | select-not-generate, no hallucination |
| Detect `ASPL-xxxxx` ticket refs | **Python regex** | exact, free |
| Write ≤500-char description | **Gemini** | fluent prose |
| Start/end times, ≥9h, ≤19:30 | **Python** | deterministic, must be exact |
| Workplace (Fri=Home else Office) | **Python** | pure rule |
| Fill fields / navigate / verify | **Playwright** + **Jev** (noul checks) | robust |

---

## 2. The target site — what makes it tricky (and how we go fast)

**Tech:** ASP.NET WebForms + **Telerik RadControls**. Every action posts back with `__VIEWSTATE`/`__EVENTVALIDATION`; dropdowns are `RadComboBox` widgets (not `<select>`); dates/times are `RadDateInput`/`RadTimePicker`.

**Timesheet element IDs** (confirmed):
- Client `ctl00_ContentPlaceHolder1_ddlClientName`
- Task Name `ctl00_ContentPlaceHolder1_ddlTaskName`
- Module `ctl00_ContentPlaceHolder1_ddlModule`
- Work Place `ctl00_ContentPlaceHolder1_ddlWorkPlace`
- Start `ctl00_ContentPlaceHolder1_RadTimeFrom` · End `ctl00_ContentPlaceHolder1_RadTimeEnd`
- Date `ctl00_ContentPlaceHolder1_RadReportDate`
- Buttons: **Add Row**, **Save**.

### Speed strategy (three layers, fastest that works wins)

1. **Persist the authenticated session.** Log in once with Playwright, save `storage_state.json` (cookies). Every later run reuses it → no login round-trip. Re-login only on 401/redirect to login.

2. **Set Telerik combos via the client API, not UI clicks.** Instead of click-dropdown-scroll-click (slow, flaky), call the widget directly in-page:
   ```python
   await page.evaluate("""([id, text]) => {
       const cb = $find(id);
       const item = cb.findItemByText(text);
       if (!item) throw new Error('option not found: ' + text);
       item.select(); cb.commitChanges && cb.commitChanges();
   }""", [combo_id, "Augastam (New Product)"])
   ```
   Times set the same way via the RadTimePicker's `set_selectedDate`, or by typing `HH:MM` into the inner `_dateInput` and blurring.

3. **Wait on RadAjax, not on `sleep`.** Selecting Client may trigger a partial postback that repopulates Module. Hook the Telerik AJAX manager:
   ```python
   await page.evaluate("() => new Promise(r => { \
      const m = window.Sys && Sys.WebForms && Sys.WebForms.PageRequestManager.getInstance(); \
      if (!m) return r(); m.add_endRequest(function h(){ m.remove_endRequest(h); r(); }); })")
   ```
   Fallback: `wait_for_load_state('networkidle')`.

**Per-row fill sequence:** set Date (once/day) → for each task: set Client, Task Name, Module, Work Place, fill Description textarea, set Start, set End → click **Add Row** (wait for grid row to appear) → repeat. Never click **Save** until the user confirms.

> A faster raw-HTTP path (POST the form with harvested `__VIEWSTATE`) exists but is brittle against Telerik/viewstate changes. We use Playwright-with-client-API as the reliable default; raw HTTP is a later optimization only if needed.

---

## 3. Jev (TypeSafe System One) — where it's used

Jev returns **typed judgments** (not text): `noul` (yes/no prob), `choice` (one-of-set + probabilities/confidence), `score`. Perfect for the many small right/wrong decisions in this workflow.

**API contract:**
```
POST https://api.typesafe.ai/v1/systemone
Authorization: Bearer $JEV_API_KEY
Content-Type: application/json
{ "state": <string|object>, "model": "jev-latest",
  "questions": { "<id>": { "type":"noul|choice|score", "instructions":"...", "criteria":{...} } } }
```
Response: `answers[id]` → `{noul: 0.95}` or `{choice:"x", probabilities:{...}, confidence:0.8}`.

**Independent questions over the same state are batched into ONE request** (they run in parallel). Uses per plan:

- **Task Name selection** (choice over the 24 options) — map each spoken segment to `New Requirement` / `Bug` / `Testing` / `Meeting` / etc. Select-not-generate = no invalid values.
- **Multi-task detection** (noul: "Does this describe more than one distinct task?") to guide splitting.
- **Ticket-done detection** (noul: "Does the speaker say they finished/completed a ticket?") → offer to update `ASPL-xxxxx` status to Completed.
- **Post-fill verification** (noul over the page text: "Did the row save with the correct client and times?") — cheap guardrail after each Playwright action instead of trusting blindly.

State passed to Jev = the transcript segment + the list of allowed options in `criteria`. Keep exact math/rules OUT of Jev.

---

## 4. Gemini — text generation

`gemini-3.5-flash`, one call per task segment: input = raw transcript slice (+ ticket no if any); output = a clean, professional task description **≤ 500 chars**. Python hard-truncates/validates length after. Prompt keeps it factual — no invented work. (Google Generative Language REST API with `GEMINI_API_KEY`; key stays server-side.)

---

## 5. Sarvam — speech to text

`saaras:v3` (Saaras speech model) handles English + Indian-language mixed dictation → transcript. React records mic audio (`MediaRecorder`), POSTs the blob to FastAPI `/transcribe`, backend forwards to Sarvam, returns transcript. Then `/plan` runs Jev+Gemini+rules.

---

## 6. Business rules (pure Python — `logic/rules.py`)

Fixed per entry: Client=`Augastam (New Product)`, Module=`Augastam ai`, Task Name default=`New Requirement`.

**Workplace:** `"Home" if weekday == Friday else "Office"`.

**Time engine:**
- Day starts **09:45** (picker default 10:00 → we use 09:45/10:00).
- Must total **≥ 9h**; last task ends **>19:00 and ≤19:30** (so ~09:45→19:15 ≈ 9.5h).
- If user gives durations → chain them contiguously from start; pad the final task so end lands in the 19:00–19:30 window and total ≥9h.
- If no durations → split the 09:45→19:15 window evenly across N tasks.
- Output each row's `start`/`end` as `HH:MM`.

Example (2 tasks, no times given): T1 09:45→14:30, T2 14:30→19:15 (total 9:30).

---

## 7. FastAPI surface

| Endpoint | In | Out |
|---|---|---|
| `POST /transcribe` | audio blob | `{transcript}` |
| `POST /plan` | `{transcript, date}` | `DayPlan{date, workplace, tasks[{taskName,module,client,description,start,end,ticket?}], totalHours}` |
| `POST /fill` | `DayPlan` (confirmed) | fills browser, returns `{screenshot, gridRows}` — **no save** |
| `POST /save` | `{confirm:true}` | clicks Save, returns result |
| `GET /tickets` | — | current Assigned tickets (for ticket-done UX) |
| `POST /ticket/update` | `{ticket, status, remarks}` | updates a ticket (Select→status→Update) |

`/plan` orchestrates Jev (batched) + Gemini (per task) + rules. Playwright runs as a long-lived browser context in the backend process (or a small worker), reusing `storage_state`.

---

## 8. Repo layout

```
ace_portal_automation/
├─ .env                     # secrets (gitignored)
├─ backend/
│  ├─ main.py               # FastAPI app + routes
│  ├─ services/
│  │  ├─ sarvam.py          # STT
│  │  ├─ gemini.py          # description generation
│  │  └─ jev.py             # System One client (batched questions)
│  ├─ logic/
│  │  └─ rules.py           # time engine + workplace + validation
│  ├─ automation/
│  │  ├─ session.py         # login + storage_state reuse
│  │  └─ timesheet.py       # Playwright fill/save (Telerik client API)
│  └─ models/schemas.py     # Pydantic DayPlan, Task
└─ frontend/                # React (mic, preview table, confirm/save)
```

---

## 9. Build order (milestones)
1. **Playwright session + fill** (hardcoded sample DayPlan) → prove we can fill today's row reliably. ← do first
2. **rules.py** time engine + tests.
3. **Jev** task-name choice + multi-task noul.
4. **Gemini** description writer.
5. **FastAPI** wiring `/plan` + `/fill` + `/save`.
6. **React** preview/confirm.
7. **Sarvam** mic → transcript.
8. Ticket update flow (optional).

Milestone 1 is what we validate today with a no-save test fill in the browser.
```
```
