# Agent-Drafted Timesheet Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let any local coding agent (Antigravity default; Claude Code, Codex, Gemini CLI) investigate a day's work and submit a timesheet draft into the existing review table, replacing the Gemini dependency for this path.

**Architecture:** A stdio MCP server (`ace-timesheet`) exposes read-only investigation tools plus `get_day_context` / `get_ticket` / `submit_draft`; it forwards to the running FastAPI backend over HTTP. The backend owns tickets, day context, draft validation (reusing the planner's time allocation), draft storage, and spawning agent CLIs headless for the one-click path. The React Timesheet tab gets an agent dropdown, a **Draft with agent** button and an evidence line. Fill is unchanged.

**Tech Stack:** Python 3 / FastAPI / pydantic v2 / pytest; `mcp[cli]==1.28.1` (FastMCP, same as `../ace_mcp`); `pyodbc` (to import `../ace_mcp`); React 19 / Vite / vitest.

**Spec:** `docs/superpowers/specs/2026-10-27-agent-drafted-timesheet-design.md`

**Repo note:** this folder is not a git repository. Where a task says "Checkpoint", run the full test suite instead of committing: `.\.venv\Scripts\python.exe -m pytest -q` (and `cd frontend; npm test` for frontend tasks).

## Global Constraints

- The agent path never fills ACE, never clicks Save, never writes tickets. No `fill`/`save` MCP tool; `test_no_save_or_ticket_update_capability` must keep passing.
- Agent may list/open only paths under `AGENT_SCAN_ROOT` (default `C:\Users\HP\Desktop\akhil_system`). Never readable: anything under `runtime/`, `.git/`, `node_modules/`, `.venv/`, `venv/`, `__pycache__/`; names starting `.env`; `storage_state.json`; `*.pem`, `*.key`, `*.pfx`. Desktop loose items, Downloads and `D:/ace_portal_automation` are excluded from the agent path.
- Description from the agent: 40–480 chars before the `[ASPL-…] ` prefix; final description ≤ 500 (existing `Task` limit). `humanize()` is applied to every agent description.
- Tickets may be attached only if in the user's set: `Employee Name` or `CompletedBy` equals `ACE_ASSIGNEE` (default `Vineet Kukreti`) after whitespace-collapse + casefold (DB stores `Vineet  Kukreti` with two spaces). Others are dropped with a warning.
- `evidence` is shown in the UI only; it is never typed into ACE.
- Backend stays bound to 127.0.0.1; every `/agent/*` route requires the `x-ace-client: 1` header (GET included).
- Working days are Monday–Saturday (`is_working_day`); ranges ≤ 63 calendar days.
- Headless agent per-date timeout: `AGENT_TIMEOUT_SECONDS`, default `300`. Max rejected `submit_draft` calls per run: 3.
- Default agent: `antigravity`. Agent ids: `antigravity`, `claude`, `codex`, `gemini`.
- Existing "Create my plan" (Gemini/agy prompt) flow stays unchanged.

## Review Focus

1. **Date with no activity and no note** — agent submits nothing; UI must show "No work found for <date>; dictate the day instead." not a spinner forever or a generic error. Test in Task 7 (`test_run_without_submit_reports_no_work`).
2. **Agent tries a path outside the root via `..` or a symlink/junction** — refused with a clear error, never read. Test in Task 4 (`test_rejects_escape_via_dotdot_and_symlink`).
3. **Backend not running when the chat-path agent calls a tool** — tool returns "ACE assistant is not running. Start it with start.ps1." instead of a stack trace. Test in Task 6 (`test_tools_report_backend_down`).
4. **Day already filled / Sunday / leave** — `submit_draft` refuses with the reason; context shows it first so the agent stops early. Test in Task 5 (`test_submit_refuses_filled_or_non_working_day`).
5. **User edited the current plan, then a chat-path draft arrives for the same date** — UI must not overwrite edits silently; it shows a notice and loads only on click. Test in Task 9 (`mergeIncomingDraft keeps edited plan`).

---

### Task 1: Planner refactor — reusable day assembly + `evidence` field

**Files:**
- Modify: `backend/app_models.py` (class `Task`)
- Modify: `backend/services/planner.py` (extract from `make_plan`, lines ~119–152)
- Test: `tests/test_planner.py`

**Interfaces:**
- Produces: `Task.evidence: str | None = Field(default=None, max_length=600)`
- Produces: `planner.PlannedItem` — pydantic `StrictModel` with `description: str`, `ticket: str | None`, `reason: str | None`, `evidence: str | None`, `durationMinutes: int | None`
- Produces: `planner.build_day_plan(day: date, items: list[PlannedItem], warnings: list[str], activity_summary: str | None = None) -> DayPlan` — applies `humanize(TICKET_MENTION.sub('', description))`, ticket prefix, `allocate_natural` with the existing per-day seed (`540 + sha256(day)%30`), the "final task was extended" warning, `workplace(day)`, `totalHours`.

- [ ] **Step 1: Write failing tests**

```python
def test_build_day_plan_prefixes_ticket_and_keeps_evidence():
    items = [planner.PlannedItem(description='I fixed the vitals template rendering for doctors.', ticket='ASPL-172905',
                                 reason='Agent match', evidence='Daily note item 1', durationMinutes=None)]
    result = planner.build_day_plan(date(2026,10,26), items, [])
    task = result.tasks[0]
    assert task.description.startswith('[ASPL-172905] I fixed')
    assert task.evidence == 'Daily note item 1'
    assert 540 <= sum(minutes(t.end) - minutes(t.start) for t in result.tasks) < 570

def test_build_day_plan_humanizes():
    items = [planner.PlannedItem(description='I updated planner.py (commit 3f9a2c1b) for the summary screen.',
                                 ticket=None, reason=None, evidence='x', durationMinutes=None)]
    desc = planner.build_day_plan(date(2026,10,26), items, []).tasks[0].description
    assert '.py' not in desc and '3f9a2c1b' not in desc
```

- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_planner.py -q` — Expected: the two new tests FAIL (`PlannedItem` missing).
- [ ] **Step 3: Implement** `Task.evidence`, `PlannedItem`, `build_day_plan`; make `make_plan` call `build_day_plan` (behaviour unchanged).
- [ ] **Step 4: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_planner.py tests/test_rules.py tests/test_browser_fill.py -q` — Expected: all PASS (old planner tests prove no regression; fill tests prove `evidence` is ignored by `expected_rows`).
- [ ] **Step 5: Checkpoint** — full suite passes.

---

### Task 2: User ticket provider (`ace_mcp` DB with fallback)

**Files:**
- Create: `backend/services/user_tickets.py`
- Modify: `requirements.txt` (add `pyodbc` and `mcp[cli]==1.28.1` — the latter used from Task 6)
- Modify: `.env.example` (add `ACE_MCP_PATH=`, `AGENT_SCAN_ROOT=`, `AGENT_DEFAULT=antigravity`, `AGENT_TIMEOUT_SECONDS=300`)
- Test: `tests/test_user_tickets.py`

**Interfaces:**
- Produces: `UserTicket(StrictModel)`: `ticket: str` (pattern `^ASPL-\d{5,8}$`), `description: str`, `module: str = ''`, `taskType: str = ''`, `status: str = ''`, `assignedOn: date | None`, `completedOn: date | None`, `completedByMe: bool = False`
- Produces: `rows_to_user_tickets(rows: list[dict], assignee: str) -> list[UserTicket]` — pure; columns `ASPL#`, `Description`, `Module Name`, `Task Name`, `ASPL Status`, `Employee Name`, `CompletedBy`, `Assigned On` / `Date` (`dd/mm/yyyy[ HH:MM]`), `CompletedOn`.
- Produces: `load_user_tickets(fallback: list[Ticket]) -> tuple[list[UserTicket], str | None]` — imports `ace.tools` from `ACE_MCP_PATH` (default `ROOT.parent / 'ace_mcp'`) via `sys.path`, calls `tools.search_tickets(limit=5000)['rows']`; on any exception returns fallback converted (`completedByMe=False`) plus warning `'ACE ticket database unavailable; using your scraped Assigned list.'`
- Produces: `rank_for_day(tickets: list[UserTicket], day: date, limit: int = 60) -> list[UserTicket]` — open (status not in `Completed`, `Delivered`, `Verified`, `Closed`) first, then by distance of `completedOn or assignedOn` to `day`.

- [ ] **Step 1: Write failing tests** — `test_rows_filter_by_assignee_with_double_space` (row with `'Employee Name': 'Vineet  Kukreti'` kept; `'Amit Kumar'` dropped; row with `'CompletedBy': 'Vineet  Kukreti'` kept with `completedByMe is True`); `test_load_falls_back_when_db_import_fails` (monkeypatch `ACE_MCP_PATH` to a missing dir → returns fallback + warning text above); `test_rank_puts_open_and_near_dates_first`.
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_user_tickets.py -q` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement**; `pip install -r requirements.txt`.
- [ ] **Step 4: Run** the tests — Expected: PASS. Then live check: `.\.venv\Scripts\python.exe -c "from backend.services.user_tickets import load_user_tickets as l; t,w=l([]); print(len(t), w)"` — Expected: `21 None` or more (21 verified on 2026-10-27).
- [ ] **Step 5: Checkpoint.**

---

### Task 3: Day context for the agent

**Files:**
- Create: `backend/services/agent_context.py`
- Modify: `backend/services/activity_gatherer.py` (`scan_git_activity` items gain `repoPath` and `time`)
- Test: `tests/test_agent_context.py`, `tests/test_activity_gatherer.py`

**Interfaces:**
- Consumes: `load_user_tickets`, `rank_for_day` (Task 2); `is_working_day`, `workplace` (`app_rules`); `read_json`, `leave_days` (`app_status`).
- Produces: `scan_root() -> Path` — `AGENT_SCAN_ROOT` or `Path.home()/'Desktop'/'akhil_system'`, resolved.
- Produces: `find_daily_note(day: date, folder: Path) -> str | None` — stem matches `^(\d{1,2})[-_.](\d{1,2})[-_.](\d{2}|\d{4})$` (2-digit year → 2000+), ext `.txt`/`.md`; returns text (≤ 20 000 chars).
- Produces: `scan_project_files(day: date, root: Path, limit: int = 300) -> list[dict]` — recursive; items `{path: str, kind: 'file'|'folder', created: bool, time: 'HH:MM'}` for local-date mtime/ctime == day; skips Global Constraints' never-readable names plus `dist`, `build`, `.next`, `.pytest_cache`, dot-names; sorted by time.
- Produces: `scan_git_activity` item keys add `repoPath: str` (absolute) and `time: 'HH:MM'` (pretty format becomes `%h|%an|%cI|%s`, split with `maxsplit=3`).
- Produces: `day_context(day: date, user_notes: str | None, fallback_tickets: list[Ticket]) -> dict` with keys exactly: `date`, `isWorkingDay`, `workplace`, `alreadyFilled` (status cache entry for the date has `rows > 0`), `onLeave`, `userNotes`, `dailyNote`, `commits` (from `scan_git_activity(day, [scan_root()])`), `files`, `candidateTickets` (ranked, `model_dump(mode='json')`), `ticketWarning`, `rules` (dict: `descriptionMaxChars: 480`, `descriptionMinChars: 40`, `voice`: the voice paragraph copied verbatim from `providers.gemini` prompt, `forbidden`: "file names, extensions, folder/repo names, paths, commit hashes, branch names, 'modified X file', ticket numbers in text").

- [ ] **Step 1: Write failing tests** — `test_find_daily_note_formats` (files `17-9-2026.txt`, `18-9-26.txt` in `tmp_path`; `date(2026,9,18)` returns the second's text; `date(2026,9,19)` → `None`); `test_scan_project_files_skips_secrets_and_vendor` (tmp tree with `proj/app.py`, `proj/.env`, `proj/node_modules/x.js`, `proj/runtime/a.json` all touched today → only `app.py`); `test_day_context_flags_filled_and_sunday` (monkeypatch status cache read to `{'2026-10-26': {'rows': 3}}`; `date(2026,10,26)` → `alreadyFilled True`; `date(2026,10,25)` → `isWorkingDay False`); `test_git_items_have_repo_path_and_time` (tmp git repo with one commit today).
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_agent_context.py tests/test_activity_gatherer.py -q` — Expected: new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the same command — Expected: PASS (including old gatherer tests).
- [ ] **Step 5: Checkpoint.**

---

### Task 4: Read-only investigation tools (`safe_fs`)

**Files:**
- Create: `backend/services/safe_fs.py`
- Test: `tests/test_safe_fs.py`

**Interfaces:**
- Consumes: `scan_root()` (Task 3) and the never-readable rules.
- Produces (all raise `AccessError(ValueError)` with a human message on refusal):
  - `allowed_path(path: str, root: Path) -> Path` — resolves (`strict=True`, follows symlinks/junctions), must be `is_relative_to(root)` and pass the never-readable rules.
  - `list_dir(path: str, root: Path) -> list[dict]` — `{name, kind, size, modified: 'YYYY-MM-DD HH:MM'}`, hidden/never-readable entries omitted, max 500.
  - `read_file(path: str, root: Path, offset: int = 0, max_chars: int = 60_000) -> dict` — `{path, text, truncated}`; refuses binary (NUL byte in first 8 KB) with "Binary file; describe it from its name and folder instead."
  - `git_log(repo: str, day: date, root: Path) -> list[dict]` — `{hash, author, time, subject, files}` via `git -C <repo> log --since="<day> 00:00" --until="<day> 23:59:59" --name-only`.
  - `git_show(repo: str, commit: str, root: Path, max_chars: int = 60_000) -> dict` — `commit` must match `^[0-9a-f]{7,40}$`; runs `git -C <repo> show --stat --patch --no-ext-diff --no-color <commit>`; diffs of never-readable paths are excluded with `-- . ':(exclude)*.env*' ':(exclude)**/runtime/**'`; `{text, truncated}`.

- [ ] **Step 1: Write failing tests** — `test_rejects_escape_via_dotdot_and_symlink` (`root/../secret.txt` refused; a symlink inside root pointing outside refused — skip the symlink half with `pytest.skip` if `os.symlink` raises `OSError` on Windows); `test_refuses_env_and_runtime`; `test_read_file_truncates_and_refuses_binary`; `test_git_show_rejects_non_hash` (`'HEAD; rm -rf'` → `AccessError`); `test_git_log_and_show_on_tmp_repo`.
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_safe_fs.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement** (subprocess with list args, `timeout=30`, `encoding='utf-8', errors='replace'`).
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 5: Draft acceptance, run state and `/agent/*` endpoints

**Files:**
- Create: `backend/services/agent_drafts.py`
- Modify: `backend/main.py` (routes + middleware header rule: require header when `request.url.path.startswith('/agent/')`)
- Test: `tests/test_agent_drafts.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `build_day_plan`, `PlannedItem` (Task 1); `load_user_tickets` (Task 2); `day_context` (Task 3); `optional_tickets()` in `main.py` as fallback list.
- Produces models: `AgentTask(StrictModel)`: `description: str` (1–600 raw; length rule enforced after humanize), `ticket: str | None`, `evidence: str` (1–600), `durationMinutes: int | None` (1–585). `AgentDraft(StrictModel)`: `date: date`, `tasks: list[AgentTask]` (1–12), `summary: str = ''` (≤ 600).
- Produces: `accept_draft(draft: AgentDraft, user_tickets: list[UserTicket], context: dict) -> tuple[DayPlan | None, list[str]]` — returns `(None, errors)` when: not working day ("<date> is not a working day."), `alreadyFilled` ("<date> already has entries in ACE; nothing to draft."), `onLeave`, any humanized description outside 40–480 chars (error names the task index), or `DayPlan` validation fails (message text). Unknown tickets → ticket set to `None` and warning `"ASPL-X is not one of your tickets, so it was removed."`. Otherwise `(plan, [])` with `matchReason='Matched by your agent. Please review.'` for tagged tasks.
- Produces: `DraftStore(folder: Path = RUNTIME/'agent_drafts')` with `save(plan: DayPlan) -> None` (file `<date>.json`, includes `createdAt` ISO), `list() -> list[dict]` (`{date, createdAt, tasks}` newest first), `load(day: date) -> DayPlan | None`.
- Produces: `ActiveRun` dataclass: `day: date`, `notes: str`, `events: asyncio.Queue`, `plan: DayPlan | None = None`, `rejects: int = 0`, `last_errors: list[str]`, `context_seen: bool = False`; module-level `current: ActiveRun | None`.
- Routes (all JSON, local-only, header required):
  - `GET /agent/context?date=YYYY-MM-DD` → `day_context(...)` with `userNotes` from `current` when `current.day == date`; sets `current.context_seen`.
  - `GET /agent/tickets/{aspl}` → the `UserTicket` or 404 "Not one of your tickets."
  - `POST /agent/submit` body `AgentDraft` → 200 `{plan}` (saved to store; sets `current.plan` when dates match) or 422 `{detail: errors}` (increments `current.rejects`, stores `last_errors`).
  - `POST /agent/event` body `{message: str (≤ 200)}` → puts a `step` event on `current.events` if a run is active; 204 otherwise.
  - `GET /agent/drafts` → `DraftStore.list()`; `GET /agent/drafts/{date}` → plan or 404.

- [ ] **Step 1: Write failing tests** — `test_submit_refuses_filled_or_non_working_day`; `test_unknown_ticket_dropped_with_warning`; `test_short_description_rejected_with_index`; `test_accepts_and_stores_draft` (TestClient POST `/agent/submit` → 200, then `GET /agent/drafts` lists the date); `test_agent_routes_require_header` (GET `/agent/drafts` without header → 403). Monkeypatch `day_context` and `load_user_tickets` in tests.
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_agent_drafts.py tests/test_api.py -q` — Expected: new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS, including `test_no_save_or_ticket_update_capability`.
- [ ] **Step 5: Checkpoint.**

---

### Task 6: MCP server, launcher shim and the skill

**Files:**
- Create: `backend/mcp_server.py`
- Create: `ace_timesheet_mcp.py` (root shim: inserts its own folder into `sys.path`, calls `backend.mcp_server.main()`)
- Create: `agent/ace-timesheet/SKILL.md`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `/agent/*` routes (Task 5) over HTTP; `safe_fs` functions and `scan_root()` directly (in-process, no backend needed for reads).
- Produces: `backend_url() -> str` from `runtime/port.json` (`http://{host}:{port}`); missing file or connection error → `BackendDown("ACE assistant is not running. Start it with start.ps1.")`.
- Produces MCP tools on `FastMCP('ace-timesheet')`: `get_day_context(date: str) -> dict`, `get_ticket(aspl: str) -> dict`, `submit_draft(date: str, tasks: list[dict], summary: str = '') -> dict` (returns `{ok: True, plan}` or `{ok: False, errors}` — never raises on 422 so the agent can fix), `list_dir(path: str) -> list[dict]`, `read_file(path: str, offset: int = 0) -> dict`, `git_log(repo: str, date: str) -> list[dict]`, `git_show(repo: str, commit: str) -> dict`. Every tool first POSTs a best-effort `/agent/event` (e.g. `"Reading <last two path parts>"`, `"Looking at commit <hash> in <repo name>"`, `"Submitting draft"`), swallowing errors. `AccessError` / `BackendDown` become `{error: message}` results.
- Produces MCP prompt `fill_ace_day(date: str)` returning the SKILL.md body with the date filled in.
- `SKILL.md`: frontmatter `name: ace-timesheet`, `description: Draft the user's ACE daily timesheet for a date from their real work (notes, files, commits) and send it to the ACE assistant for review. Use when asked to fill/draft ACE or the timesheet for a day.` Body = the seven steps in spec §2 verbatim in substance, plus: "User notes (userNotes) and the daily note are the most trusted sources", "Use only the ace-timesheet tools; do not use shell or edit tools", "If context says not a working day, already filled or on leave, stop and say so", "If nothing was found, do not submit; say 'No work found for <date>'".

- [ ] **Step 1: Write failing tests** — `test_tools_report_backend_down` (no `port.json` in a tmp runtime → `get_day_context` returns `{'error': 'ACE assistant is not running. Start it with start.ps1.'}`); `test_submit_returns_errors_not_exception` (monkeypatch the HTTP call to a 422 with `detail: ['x']` → `{'ok': False, 'errors': ['x']}`); `test_read_file_refuses_outside_root`; `test_prompt_contains_date`. Call tool functions directly (FastMCP decorators keep the plain function callable; if not, test the undecorated helpers they wrap).
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_mcp_server.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS. Then smoke: start backend (`.\.venv\Scripts\python.exe -m backend.run`), and in another shell `npx @modelcontextprotocol/inspector .\.venv\Scripts\python.exe ace_timesheet_mcp.py` (or `mcp dev`) — call `get_day_context` for `2026-10-26`; Expected: JSON with `candidateTickets` containing `ASPL-172905` and `alreadyFilled` as per ACE.
- [ ] **Step 5: Checkpoint.**

---

### Task 7: Agent runner and `/agent/draft-stream`

**Files:**
- Create: `backend/services/agent_runner.py`
- Modify: `backend/main.py` (routes)
- Test: `tests/test_agent_runner.py`, `tests/fake_agent.py` (test helper: a Python script that, given `--submit` or `--silent`, calls the backend `/agent/context` and optionally `/agent/submit` with a fixed valid draft)

**Interfaces:**
- Consumes: `ActiveRun`, `current`, `DraftStore` (Task 5); SKILL.md (Task 6).
- Produces: `Recipe` dataclass `{id, label, exe: str, build: Callable[[str, Path, Path], list[str]]}` (prompt, scan root, mcp-config path) and `RECIPES: dict[str, Recipe]` for the four ids. Initial command shapes (Task 8 verifies and corrects them):
  - `claude`: `claude -p <prompt> --mcp-config <runtime/agent_mcp.json> --strict-mcp-config --allowedTools mcp__ace-timesheet --permission-mode dontAsk --output-format text`
  - `antigravity`: `agy -p <prompt> --mode plan --disable-slash-commands --output-format text` (server registered by setup)
  - `codex`: `codex exec --skip-git-repo-check -s read-only -C <root> -c approval_policy="never" -c mcp_servers.ace-timesheet.command="<python>" -c mcp_servers.ace-timesheet.args=["<shim>"] <prompt>`
  - `gemini`: `gemini -p <prompt> --allowed-mcp-server-names ace-timesheet --approval-mode plan --output-format text` (server registered by setup)
- Produces: `available_agents() -> list[dict]` — `{id, label, installed: bool, verified: bool}`; `verified` comes from a constant set updated in Task 8 (only verified agents are selectable).
- Produces: `agent_prompt(day: date) -> str` — SKILL body + `"Draft the ACE timesheet for {day}. Use the ace-timesheet MCP tools only. Finish by calling submit_draft."` (notes travel via `/agent/context`, never on the command line).
- Produces: `async run_for_day(agent: str, day: date, notes: str, on_progress) -> DayPlan | None` — writes `runtime/agent_mcp.json`, sets `current`, spawns with `asyncio.create_subprocess_exec` (cwd = scan root, stdout/stderr captured), relays `current.events` to `on_progress` while waiting, kills on timeout. Outcomes: plan submitted → return plan; `rejects >= 3` → kill, raise `ProviderError("Your agent's draft was rejected 3 times: " + '; '.join(last_errors))`; exit without submit and `context_seen` → return `None`; exit without ever calling context → `ProviderError("<label> did not reach the ACE tools. Run setup_agents.ps1, then retry.")`; non-zero exit → `ProviderError("<label> stopped with an error. Check it is logged in, or pick another agent.")`; timeout → `ProviderError("<label> took longer than <n> minutes and was stopped.")`. Always clears `current`.
- Routes: `GET /agent/agents` → `available_agents()`; `POST /agent/draft-stream` body `{fromDate, toDate|null, agent, notes, perDay}` (reuse `RangeRequest` validation when `toDate` given; reject unverified agent with 422) → SSE using existing event shape; per date: `step` events, then on `None` a `step` "No work found for <date>; dictate the day instead." and the date is listed in `result.noWork`; final `{'type':'result','plans':[...], 'noWork':[...]}`. Runs under `planning_lock`, dates sequential.

- [ ] **Step 1: Write failing tests** — `test_recipes_are_read_only` (assert `--permission-mode dontAsk` in claude, `--mode plan` in agy, `-s read-only` in codex, `--approval-mode plan` in gemini; no recipe contains `dangerously` or `yolo`); `test_prompt_has_no_notes`; `test_run_returns_submitted_plan` and `test_run_without_submit_reports_no_work` (monkeypatch `RECIPES` with a recipe running `sys.executable tests/fake_agent.py --submit|--silent` against a `TestClient`-free live uvicorn on a free port, or patch the HTTP base so the fake agent posts directly to the app via `httpx.ASGITransport`—builder's choice); `test_timeout_kills_agent` (fake agent sleeps; timeout 2 s → `ProviderError` with "was stopped").
- [ ] **Step 2: Run** `.\.venv\Scripts\python.exe -m pytest tests/test_agent_runner.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Checkpoint.**

---

### Task 8: Verify real agents + `setup_agents.ps1`

**Files:**
- Create: `setup_agents.ps1`
- Modify: `backend/services/agent_runner.py` (correct recipe flags; set `VERIFIED`)
- Modify: `README.md` (new "Draft with your agent" section)

**Interfaces:**
- Consumes: `ace_timesheet_mcp.py`, `agent/ace-timesheet/SKILL.md`.
- Produces: `setup_agents.ps1` — idempotent; for each installed CLI: remove-then-add MCP server `ace-timesheet` → `<repo>\.venv\Scripts\python.exe <repo>\ace_timesheet_mcp.py` (`claude mcp add --scope user`, `agy mcp add`, `gemini mcp add` with user scope, `codex mcp add`); install the skill where the CLI supports skills (`~/.claude/skills/ace-timesheet/SKILL.md`; Gemini via `gemini skills` per its `--help`; Codex/Antigravity per their `--help` — if no skill mechanism, skip and print "uses the MCP prompt fill_ace_day instead"). Prints a per-agent summary line.

- [ ] **Step 1:** Run `.\setup_agents.ps1` with the backend running — Expected: one "ok" line per installed agent.
- [ ] **Step 2: Per agent, two manual checks** (run each through `/agent/draft-stream` or a small `python -c` calling `run_for_day`):
  - (a) Reaches tools unattended: draft for `2026-10-26` → events show "Reading …" and a draft is submitted or "No work found"; no hang waiting for a permission prompt.
  - (b) Cannot write: run the recipe with prompt `"Create the file C:\Users\HP\Desktop\akhil_system\agent_write_probe.txt containing hi, then say DONE."` → file must not exist afterwards.
- [ ] **Step 3:** Fix recipe flags until both pass. If an agent cannot pass (b) without losing (a), leave it out of `VERIFIED` and note it in README. Record exact working command lines in a comment above `RECIPES`.
- [ ] **Step 4:** Update `test_recipes_are_read_only` to the final flags; run `.\.venv\Scripts\python.exe -m pytest -q` — Expected: PASS.
- [ ] **Step 5: Checkpoint.** Report to the user which agents are verified (Antigravity is the one they care about most).

---

### Task 9: UI — Draft with agent, evidence line, incoming drafts

**Files:**
- Create: `frontend/src/agent.js` (pure helpers), `frontend/src/agent.test.js`
- Modify: `frontend/src/main.jsx` (plan-action area ~line 253, task card ~line 410, new polling effect)
- Modify: `frontend/src/style.css`

**Interfaces:**
- Consumes: `GET /agent/agents`, `POST /agent/draft-stream`, `GET /agent/drafts`, `GET /agent/drafts/{date}`; `streamEvents` from `api.js`.
- Produces: `agentPayload({date, toDate, range, notes, perDayMode, perDay, agent})` → `{fromDate, toDate: range ? toDate : null, agent, notes: perDayMode ? '' : notes, perDay: perDayMode ? perDay : {}}`.
- Produces: `newDrafts(list, seen)` → drafts whose `createdAt` > `seen[date]` (seen persisted in `localStorage` key `ace.agentDraftsSeen`, wrapped in try/catch).
- Produces: `mergeIncomingDraft(plans, draft, edited)` → `{plans, notice}`: if no plan for that date → append; if a plan exists and `edited` is false → replace; if `edited` → unchanged plans and `notice: 'A new draft from your agent for <date> is ready. Load it?'`.
- UI: agent `<select>` (verified agents only; default from `/agent/agents` order with `antigravity` first; choice remembered in `localStorage` key `ace.agent`) and **Draft with agent** button next to **Create my plan**, same disabled rules minus the per-day-notes requirement; progress uses the existing `agent-progress` panel. `noWork` dates shown as a hint line. Under each task: `{t.evidence && <small className="evidence">Based on: {t.evidence}</small>}`. Poll `/agent/drafts` every 15 s while the Timesheet tab is open and no run is active; show the notice with a **Load** button.

- [ ] **Step 1: Write failing tests** in `agent.test.js`: `agentPayload` single-day and per-day cases; `newDrafts` ignores seen; `mergeIncomingDraft keeps edited plan` (returns same `plans` array and the notice text); `mergeIncomingDraft replaces unedited plan`.
- [ ] **Step 2: Run** `cd frontend; npm test` — Expected: FAIL.
- [ ] **Step 3: Implement** helpers and UI.
- [ ] **Step 4: Run** `npm test` and `npm run build` — Expected: PASS, build succeeds.
- [ ] **Step 5: Checkpoint.**

---

### Task 10: End-to-end on a real past date

**Files:** none new (fixes go to the owning task's files).

- [ ] **Step 1:** `.\start.ps1`; open http://127.0.0.1:8765; Timesheet tab; date = a recent working day the user has already filled in ACE (e.g. 2026-10-24 — expect "already has entries" refusal, proving the guard) and one not yet filled (pick from the dashboard's red days).
- [ ] **Step 2:** Agent = Antigravity → **Draft with agent**. Expected: live steps ("Reading …", "Looking at commit …", "Submitting draft"), then the review table with tasks, ASPL tags only from the user's tickets, "Based on:" lines, total 9:00–9:29, no file names in descriptions.
- [ ] **Step 3:** Chat path: in Claude Code type "fill my ACE for <same unfilled date>" → draft notice appears in the UI within 15 s; **Load** shows it.
- [ ] **Step 4:** Do **not** click Fill in ACE during testing unless the user asks; show the user the drafted descriptions for a quality check against what they would have written.
- [ ] **Step 5:** Full checks: `.\.venv\Scripts\python.exe -m pytest -q`; `cd frontend; npm test; npm run build` — Expected: all PASS.
