# ACE Timesheet Assistant — Bug & Fix Log

Living list of issues found during testing, their status, and the fix.

Legend: ✅ fixed · 🟡 open · 🔵 by-design (not a bug)

---

## ✅ 1. Playwright crash on Windows (`NotImplementedError`)
**Symptom:** Fill failed instantly; "server returned an unexpected response."
**Cause:** uvicorn `--reload` forces the Windows *Selector* event loop; Playwright needs the *Proactor* loop to spawn its browser subprocess.
**Fix:** Removed `--reload` from the run task; added a Proactor-policy safeguard in `main.py`. Also cleaned up a zombie reload-child process holding port 8765.

## ✅ 2. ACE login didn't complete
**Symptom:** "ACE login did not complete." on every fill.
**Cause:** ACE presents the login screen **twice** (the second is the "Online Bug Tracker" entry). The handler only submitted once.
**Fix:** `app_session.login()` now submits credentials up to 3 rounds until the password field disappears.

## ✅ 3. Setting the date/time widgets threw a Telerik strict-mode error
**Symptom:** "'caller', 'callee', 'arguments' … may not be accessed on strict mode functions."
**Cause:** RadDatePicker/RadTimePicker fire a synchronous ASP.NET postback whose internals read `arguments.callee`, which is illegal inside Playwright's strict-mode `evaluate`.
**Fix:** `set_widget` defers the mutating call to `setTimeout(0)` so the postback runs in normal (non-strict) scope. Widget/option existence is still checked synchronously.

## ✅ 4. Sarvam used a non–speech-to-text model
**Cause:** `saaras:v3` is Sarvam's *translate* model on the wrong endpoint.
**Fix:** Switched to `saarika:v2.5` on `/speech-to-text` (both `.env` and provider default).

## ✅ 5. Review plan showed the wrong date (selected 9 Sep → plan for 23)
**Symptom:** Change the date, but the preview still showed the previous date's plan.
**Cause (frontend):** The old plan stayed in state after the date changed; the backend was correct (sending 9 Sep returns 9 Sep).
**Fix:** The plan/results now **clear automatically whenever the date or range changes**, so the preview can only ever show the currently selected date. Rebuild required after a date change (by design).

## ✅ 6. Browser opened repeatedly / re-logged in on every action
**Symptom:** Multiple ACE windows/logins; slow, noisy.
**Cause:** `/plan` fetched assigned tickets every time, which opened the ACE browser and logged in — on every plan.
**Fix:** **Planning is now browser-free.** Tickets are loaded **on demand** via a new **"Load tickets (optional)"** button (opens ACE once and caches). `/plan` uses the cached tickets; the browser now opens **only when you click Fill** (or Load tickets). Verified: a plan takes ~7s with no browser.

## ✅ 7. "Skipped — existing entries" looked like a failure
**Fix:** Portal-handoff results now show color-coded status cards (green filled / amber skipped / red interrupted); a skipped day lists the existing ACE rows and explains nothing was added.

## ✅ 8. Assigned tickets loading failed when results were paginated
**Symptom:** Clicking "Load tickets" threw "Assigned tickets are paginated. Matching is unavailable until pagination is configured."
**Cause:** Searching from 2020-01-01 returns 20 records across 2 pages in ACE's GridView (`#ctl00_ContentPlaceHolder1_Tasks1_gvTasks`). An intentional safeguard in `backend/app_timesheet.py` aborted whenever `a[href*="Page$"]` was found.
**Fix:** Implemented automated ASP.NET GridView postback traversal across all pages (`Page$2`, `Page$3`, etc.) with deduplication (preferring open statuses) and graceful fallback. Verified live: successfully retrieves all 16 unique assigned tickets from ACE into cache and dropdown. Explicit and semantic ticket matching works seamlessly.

## ✅ 9. Port 8765 conflict / `[Errno 10048]` crash
**Symptom:** Backend failed on restart with `[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8765): only one usage of each socket address is normally permitted`.
**Cause:** An orphaned Python/uvicorn background process or TIME_WAIT socket held port 8765 when restarting the terminal task.
**Fix:** Added [`backend/run.py`](file:///D:/ace_portal_automation/backend/run.py) which checks port availability; if 8765 is occupied, it automatically increments and binds to the next free port (8766, 8767, etc.) and writes `runtime/port.json`. Updated [`backend/main.py`](file:///D:/ace_portal_automation/backend/main.py) to accept any local port origin and [`frontend/vite.config.js`](file:///D:/ace_portal_automation/frontend/vite.config.js) to dynamically route proxy requests to whichever port the backend selected. Updated `.vscode/tasks.json` and `start.ps1` to launch via `backend.run`.

## ✅ 10. Selected past date skipped because ACE grid didn't reload from server
**Symptom:** Selecting 9 Sep skipped filling and claimed "5 entries already exist" (showing tasks that actually belonged to 23 Sep).
**Cause:** When `/TimeSheet/TimeSheet.aspx` opens, it defaults to today (23 Sep) and populates the grid with today's 5 entries. Telerik's `RadReportDate` input is readonly; mutating the client-side JavaScript date object with `set_selectedDate()` updated the widget's in-memory value, but **did not fire the ASP.NET postback**. The server never sent the new grid, so the app inspected the stale grid for 23 Sep and assumed 9 Sep already had entries.
**Fix:** Added [`set_report_date()`](file:///D:/ace_portal_automation/backend/app_timesheet.py#L99-L139) which opens the native calendar popup, navigates to the target month/year, and clicks the target date cell. This triggers Telerik's native ASP.NET postback (`POST /TimeSheet/TimeSheet.aspx`), accurately reloading the server grid for that specific date before inspecting existing entries. Verified live: selecting 9 Sep correctly loads 0 entries and proceeds to fill.

## ✅ 11. Terminal logs not streaming to the user's console
**Symptom:** User noticed frontend and backend logs were not appearing in their VS Code terminal window.
**Cause:** The backend server and Vite processes were running as detached background processes spawned during previous automated tool runs, rather than inside the user's interactive VS Code terminal panel. Output was streaming into agent background buffers instead of the user's visible terminal. Furthermore, backend operations had minimal console logging.
**Fix:** Added comprehensive, step-by-step console logging (`[ACE Assistant]`) for browser launch, ticket fetching, date navigation, per-task row insertion, grid verification, and handoff instructions. Cleaned up all background processes so starting the server via `Ctrl+Shift+B` or `.\start.ps1` runs directly in the user's interactive terminal window with live streaming output.

## ✅ 12. Confusion around "Verify / resume fill" button and handoff state
**Symptom:** User clicked "Verify / resume fill" and thought filling was not working because clicking it again did not add anything or appeared unresponsive.
**Cause:** The initial "Fill in ACE" click had *already succeeded* and added all 5-6 tasks into the ACE browser draft grid (as confirmed by `runtime/audit.jsonl` and screenshots). The UI subsequently switched the button text to "Verify / resume fill". Because Chromium opened behind VS Code and the button label implied an incomplete state, the user clicked it again; since all rows were already present in the draft, no new rows were added.
**Fix:**
1. Added `--start-maximized` and window focus calls on Chromium launch and post-fill.
2. Updated the result card to show an explicit green action banner telling the user to switch to their ACE window and click the blue "Save" button.
3. Added a direct button linking to the screenshot proof for full visibility.
4. Updated the button state when all rows are already filled to read `"Re-verify ACE draft ↗"`, with backend messaging explicitly confirming: *"All X tasks are already in your ACE browser grid. Switch to ACE and click Save."*
5. Added real-time terminal output announcing each task row as it is filled and notifying the user when the draft is ready for manual saving.

## ✅ 13. Suspicious and unnatural identical task durations (`01:54` on every task)
**Symptom:** In screenshot `runtime/2026-09-14-e9384fd2a72d.png`, every single one of the 5 tasks showed `Total Hours: 01:54` with odd boundary timestamps (`09:45AM - 11:39AM`, `11:39AM - 01:33PM`, `01:33PM - 03:27PM`, `03:27PM - 05:21PM`, `05:21PM - 07:15PM`). This appeared synthetic, robotic, and suspicious for a workplace timesheet.
**Cause:** When task notes did not specify explicit durations, the system divided the 570 daily minutes (9h 30m) mathematically: `570 // 5 = 114` minutes (`01:54`).
**Fix:** Implemented [`allocate_natural()`](file:///D:/ace_portal_automation/backend/app_rules.py) which:
1. Allocates durations strictly in clean **15-minute multiples** (:00, :15, :30, :45).
2. Uses natural human variation and task weighting (e.g. 2h 15m or 2h 30m for bug fixes/development, 1h 30m or 1h 45m for meetings/reviews/mentoring).
3. Ensures all start/end boundaries land on natural clock times (e.g. `09:45 - 12:15`, `12:15 - 14:15`, `14:15 - 15:45`, `15:45 - 17:15`, `17:15 - 19:15`).
4. Replaced `allocate()` in the planner with `allocate_natural()`. Added full test suite in `tests/test_rules.py` verifying 15-minute alignment, realistic block variation, and total time correctness.

## ✅ 14. Intelligent Local Activity Gatherer & Deep Ticket Context Engine
**Feature Addition:** Automatically gathers real-world triggers from the user's system for any chosen date to enrich brief notes into factual, detailed timesheet tasks.
**Capabilities Added:**
1. **Git Commit Detection:** Scans all 10+ local repositories in `Desktop/akhil_system`, `Desktop`, and workspace for commits authored on that date. Gathers commit hashes, commit messages, modified files list (`git show --stat`), and detected ticket numbers.
2. **Created / Touched Files:** Detects new folders (e.g. `test_project`, `jev-testing`), documents (`.pdf`, `.docx`, `.xlsx`, `.csv`), demo videos (`.mp4`), and notebooks created or downloaded on that date (e.g. `Harsh Tyagi Report.docx`, `Master-Data-Request.pdf`, `AI-Dashboard.mp4`).
3. **Ticket Context Integration:** Auto-caches ACE tickets with full summaries into `runtime/tickets_cache.json`. When a task relates to a ticket, it attaches the ticket context and prefixes the task description with `[ASPL-XXXXXX] Worked on ASPL-XXXXXX: <details>` while auto-selecting the ticket in the dropdown.
4. **Natural Human Time Allocation:** Formulates contiguous tasks with natural 15-minute time blocks (`allocate_natural`), avoiding cookie-cutter durations.
5. **UI Visibility:** Displays an activity badge on the Review card: `🔍 Detected X commit(s), Y file(s) on your system for this date`.

## ✅ 15. Real-Time SSE Agent Activity & Inspection Stream
**Feature Addition:** Users wanted full visual transparency into what the assistant agent is reading and parsing across their machine while the plan is generating (reading commits, code changes, touched documents, ACE ticket cache, and Gemini synthesis).
**Capabilities Added:**
1. **Server-Sent Events (SSE) Streaming Endpoints:** Added `/plan-stream` and `/plan-range-stream` in [`backend/main.py`](file:///D:/ace_portal_automation/backend/main.py) which stream real-time progress steps (`text/event-stream`).
2. **Granular Machine Inspection Steps:**
   - Discovers all git repositories in `Desktop/akhil_system`, `Desktop`, and workspace.
   - Emits events for specific commits found in each repo (commit message + hash).
   - Emits events for modified files and diffs inspected (`git show --stat`).
   - Emits events for created folders and touched documents/spreadsheets/media (`.docx`, `.pdf`, `.mp4`).
   - Emits events for assigned ACE ticket cache matching.
   - Emits events for Gemini task synthesis and natural 15-minute interval allocation.
3. **Frontend Live Agent Progress Feed:**
   - Integrated `streamPlan` in [`frontend/src/main.jsx`](file:///D:/ace_portal_automation/frontend/src/main.jsx) with chunked SSE reader.
   - Renders a live **Assistant Agent Active** card with a pulsing green indicator, active spinner on the currently executing step, and timestamps.
   - Includes an auto-scrolling live step feed.
   - Added an expandable audit toggle on the review card: `▼ View agent activity log (N events parsed)` so users can re-inspect the agent's work anytime.
4. **Automated Verification:** Added unit test `test_plan_stream_events` in [`tests/test_api.py`](file:///D:/ace_portal_automation/tests/test_api.py). All 54 backend tests and 7 frontend tests pass.

## ✅ 16. A second ACE tab opened after every fill, on the same date with an empty grid
**Symptom:** Fill opened Chrome and filled the day, then another tab appeared showing the same Daily Task Report date with no rows. It looked like a second, failed fill.
**Cause:** After a fill the app polls ACE to see whether the day was saved (`/status/check-day`). That check ran in a visible tab of the same Chrome window. The ticket read at app start also opened a visible window.
**Fix:** `Session.background()` now uses a second, headless Chrome for status checks, month scans and ticket reads. The visible window holds only the draft tabs. Verified live: one visible tab after fill, saved-check and ticket read; draft rows untouched.

## ✅ 17. "Previously verified rows disappeared" / "report date changed" dead end
**Symptom:** Clicking fill again returned the same error every time until the backend was restarted (10 Oct draft on 13 Oct).
**Cause:** ACE's own **New** button empties the unsaved grid but keeps the date, and after Save ACE moves the tab to another date. `fill_one` treated both as fatal and kept the stale draft forever.
**Fix:** An emptied draft is refilled in the same tab (the prefix check still prevents duplicates). A tab that left the date is dropped and the day is re-read from a fresh page, so saved rows make it skip. Verified live with the New button.

## ✅ 18. A date that already had entries was closed before it could be checked
**Symptom:** Fill reported "Skipped" and the ACE tab vanished, so the saved rows could not be seen.
**Fix:** The skipped date stays open in the ACE browser and comes to the front. The message says whether the saved rows match the plan. A repeat click replaces that tab.

## ✅ 19. Calendar click timed out: "element is outside of the viewport"
**Symptom:** `Locator.click: Timeout 15000ms exceeded` on `RadReportDate_popupButton`.
**Cause:** Not reproduced. ACE lays the page out in fixed-size Telerik splitter panes that clip without scrolling, and the calendar button and Add Row sit at the far right edge, so a mouse click depends on that layout.
**Fix:** `dom_click()` clicks the calendar button, month arrows, day cell and Add Row in the DOM, which does not depend on where the element is on screen. The popup button is only clicked when the calendar is closed. Verified live for fill, previous-month navigation and the hidden reader.

## ✅ 20. Sign-in timed out when ACE's login page was slow
**Symptom:** `Page.goto: Timeout 15000ms exceeded` (seen 4 times in live testing on 13 Oct). The login document took 12s and its background image more than 14s.
**Fix:** Navigation waits for the document only (45s allowed) on the login page; a signed-in page still waits to settle. Verified live: 3 fresh sign-ins in a row.

---

## 🔵 By-design (not bugs)
- **A day with existing entries is not filled.** The app reads the grid first and skips (amber card), per the locked rule "if a date already has entries, don't fill — notify." To refill, remove the entries in ACE first.
- **The app never clicks Save.** It fills all rows and stops; you review and Save in ACE.
- **Weekends are skipped in ranges** (Sat/Sun filled separately).

---

## 🟡 Open / to verify
1. **Sarvam voice** not yet tested with a real audio clip end-to-end.
2. **Session longevity.** After long idle, ACE may expire the session; re-login path exists but hasn't been exercised over a long session.

---

## How to run (streamlined)
- **Ctrl+Shift+B** in VS Code → starts backend (:8765) + frontend (:5174).
- Open **http://127.0.0.1:5174** → pick date → speak/type → **Create my plan** (no browser) → optionally **Load tickets** (loads and caches all 16+ assigned tickets) → **Fill in ACE** (browser opens once, double-logs-in, fills, stops) → review & **Save yourself** in ACE.
