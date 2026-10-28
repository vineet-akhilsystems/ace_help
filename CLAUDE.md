# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local Windows app (FastAPI + React) that drafts the user's ACE (`http://ace.akhilsystems.com`) daily task report
and ACE tickets from their real work, then drives ACE in a Playwright-controlled Chrome. ACE is the user's real
company portal: every action there is outward-facing.

## Commands

All commands from the repo root in PowerShell unless noted. Python is always the project venv.

| What | Command |
|---|---|
| First run / full start (installs deps, builds frontend, serves on :8765) | `.\start.ps1` |
| Backend only | `.\.venv\Scripts\python.exe -m backend.run` (picks the next free port if 8765 is taken and writes it to `runtime/port.json`) |
| Frontend dev server (hot reload, proxies API to the port in `runtime/port.json`) | `cd frontend; npm run dev` → http://127.0.0.1:5174 |
| Frontend build (served by the backend from `frontend/dist`) | `cd frontend; npm run build` |
| Frontend tests | `cd frontend; npm test` (vitest; one file: `npx vitest run src/plan.test.js`) |
| Backend tests, one file | `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_tasks.py` |
| One backend test | `.\.venv\Scripts\python.exe -m pytest -q tests/test_tasks.py::test_keywords_fit_ace_25_characters` |
| Register the `ace-timesheet` MCP server + skill with Claude Code / Antigravity / Codex | `.\setup_agents.ps1` |

- Run backend tests **file by file** (e.g. a loop over `tests/test_*.py` with a timeout). A single `pytest` run of the
  whole suite has hung for many minutes in this environment while each file passes in seconds;
  `tests/test_agent_runner.py` (~50 s) and `tests/test_browser_fill.py` (~20 s) are the slow ones.
- The backend has no auto-reload. After backend changes the user must restart `start.ps1` / `backend.run`; a stale
  backend with a fresh frontend shows errors like `agent: Extra inputs are not permitted`.
- No linter is configured.

## Architecture

**Backend (`backend/`)** — one FastAPI app in `main.py` holding singletons: `Session` (ACE browser), `Timesheets`
(daily report), `TaskCreator` (ACE New Task), `StatusScanner` (month status). A middleware only accepts
localhost origins and requires the `X-ACE-Client: 1` header on POSTs, `/tasks*`, `/status`, `/agent/*` — every
frontend/agent call must send it. Long operations stream Server-Sent Events (`*-stream` endpoints; the frontend
reads them with `streamEvents` in `frontend/src/api.js`).

- `app_session.py` — Playwright with the system Chrome (`ACE_BROWSER_CHANNEL`, default `chrome`). A **visible**
  browser for tabs the user must see (fills) and a **headless reader** (`session.background(path)`) for ticket and
  status reads. Login state is cached in `runtime/storage_state.json`; ACE's login form has to be submitted twice.
  `session.lock` serialises all ACE work.
- `app_timesheet.py` — Daily Task Report (`/TimeSheet/TimeSheet.aspx?Mpg=P3`): fills rows, verifies the grid, keeps
  one tab per date, **never saves**. Also scrapes the user's Assigned tickets (`tickets()`, cached in
  `runtime/tickets_cache.json`).
- `app_tasks.py` — ACE New Task form (`/Tasks/TaskPageN.aspx?Mpg=P171`, field ids prefixed `T =
  'ctl00_ContentPlaceHolder1_Tasks1_'`; option lists cached in `runtime/ace_task_form.json`). Drafting
  (`make_task_drafts` → coding agent), deterministic drafts for untagged timesheet rows, filling, verifying every
  field, and saving (`save=True` only via `POST /tasks/create`). `TaskCreator.saved` remembers each saved draft so a
  retry never creates a duplicate ticket. Each ticket is processed independently; one failure doesn't stop the rest.
- `app_rules.py` — business rules (see below). `app_models.py` — pydantic models (`StrictModel` forbids extra keys).
- `services/providers.py` — `agent_json(agent, prompt, schema)` gets structured JSON from a local coding agent CLI
  (`agy`, `claude -p --json-schema`, `codex exec --output-schema`) with no tools; Codex is a `.cmd` shim, so its prompt
  goes through stdin and its schema through `strict_schema`. Also Sarvam speech-to-text. There is no Gemini API use.
- Timesheet drafting by agent: `services/agent_runner.py` spawns the chosen CLI headless with a read-only recipe; the
  agent talks to the `ace-timesheet` MCP server (`ace_timesheet_mcp.py` → `backend/mcp_server.py`), which reads
  files/git under `AGENT_SCAN_ROOT` via `services/safe_fs.py` and calls back into the backend over HTTP (URL from
  `runtime/port.json`). `services/agent_context.py` builds the day context; `services/agent_drafts.py` validates a
  submitted draft and turns it into a `DayPlan` via `services/planner.build_day_plan` (time allocation, ticket
  prefix, `humanize` strips file names/paths/hashes). The agent instructions live in `agent/ace-timesheet/SKILL.md`.
- `services/ticket_ideas.py` scans local files/commits for a date range; `services/user_tickets.py` reads the user's
  tickets from the sibling `ace_mcp` reporting DB (`ACE_MCP_PATH`), falling back to the scraped Assigned list.

**Frontend (`frontend/src/`)** — React 19 + Vite, no router. `main.jsx` `Root` keeps all four tabs mounted
(Dashboard, Timesheet `App`, Ticket ideas, Create tasks `TaskApp`) so switching never loses state; cross-tab flows
pass `{..., at: Date.now()}` props through `Root` (e.g. Timesheet "Create tickets" → `ticketJob` → Create tasks;
saved tickets → `linked` → Timesheet rows tagged). Pure logic lives in `plan.js` / `agent.js` with vitest tests;
keep new logic there rather than in components.

## Rules that must hold

- **Timesheets are never saved by the app.** The user saves each day in ACE.
- **ACE tickets are saved only** for drafts the user reviewed, ticked, and sent with "Create selected in ACE"
  (`/tasks/create`); "Fill only" (`/tasks/fill`) never saves. Every fill/save is appended to `runtime/audit.jsonl`.
- Ticket defaults for the user's own work: Task Type `New Requirement`, Priority `Medium`, Client
  `Augastam (New Product)`, Module `Augastam ai`, FRD `Medium`, Status `Open` (or `Completed` when the user answers
  "Have you completed this?" yes), Client/Employee Remarks `.`, assignee `ACE_ASSIGNEE` (default `Vineet Kukreti`)
  ticked in Assign To. Before proposing a ticket for own work, check the user's assigned tickets.
- Timesheet day rules (`app_rules.py`, mirrored in `plan.js`): working days Mon–Sat; workplace `Home` on Friday,
  `Office` otherwise; first task starts 09:45–10:00; contiguous rows; total ≥ 9:00 and < 9:30; a tagged row's
  description starts with `[ASPL-NNNNNN] `; descriptions ≤ 500 chars with no file names, paths or commit hashes.
- Coding agents used by the app stay read-only (no shell, no writes); keep recipes in `agent_runner.py` that way.
- **This repo is never the user's work.** Every scan (git commits, files, ticket ideas, agent `list_dir`/`read_file`/
  `git_*`) must go through `safe_fs.is_excluded`, which skips this folder, any copy named `ace_portal_automation`,
  and `AGENT_EXCLUDE` folders. New scanners must use it too.

## ACE portal gotchas

- ASP.NET WebForms + Telerik: set dropdowns through `set_widget` (`window.$find(id)`), then `await settle(page)` to
  wait for async postbacks; typing into the RadDateTimePicker is needed for the visible text to stick.
- ACE silently truncates: **Keyword max 25 chars** (`KEYWORD_MAX`). Field checks compare what ACE kept.
- After "Save & Leave Open", ACE shows green "Saved" in `lbltaskMsg` and clears the form; it does **not** show the
  new ASPL number — it is found afterwards in the Assigned list by description (`match_new_tickets`).
- Exploring ACE: use the headless reader (`Session().background(PATH)`) for read-only probes and never click
  Save/Submit while investigating. See `docs/ace-portal-reference.md` for element ids and page behaviour.

## Project skills (`.claude/skills/`)

| Skill | Use for |
|---|---|
| `creating-ace-tickets` | drafting/creating ACE tickets, ticket field rules |
| `driving-ace-portal` | exploring or automating ACE pages safely |
| `debugging-ace-fills` | "ACE did not keep…", failed saves, audit log, screenshots |
| `verifying-ace-app` | running tests, build, UI screenshots with stubbed API |
| `testing-agent-drafts` | deterministic and live tests of the agent drafting paths |
| `testing-voice-transcription` | `/transcribe`, Sarvam, generating test speech |
| `optimizing-agent-prompts` | improving agent prompts with a fixed test set |
| `extending-ace-assistant` | adding endpoints, tabs, cross-tab flows, settings |
| `creating-project-skills` | adding or updating these skills |

`agent/ace-timesheet/SKILL.md` is not a developer skill: it instructs the read-only drafting agents.

## Working here

- `.env` (gitignored) holds `ACE_USERNAME`/`ACE_PASSWORD`/`ACE_BASE_URL` (legacy `USERNAME`/`PASSWORD`/`BASE_URL`
  still read), `SARVAM_API_KEY`, agent settings (`AGENT_DEFAULT`, `AGENT_*_TIMEOUT_SECONDS`, `AGENT_SCAN_ROOT`,
  `ACE_MCP_PATH`, `ACE_GIT_AUTHOR`). Read settings with `backend.config.setting()`, never `os.environ` directly
  (Windows defines `USERNAME` itself).
- `runtime/` (gitignored) holds all state: login, caches, audit log, screenshots, agent drafts, `port.json`.
- In the Bash tool, heredoc Python with `\b`, `\n` etc. inside string literals gets mangled; use the Edit tool for
  code containing backslashes.
- Design docs and plans live in `docs/superpowers/` (specs, plans).
