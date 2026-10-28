# ACE Timesheet Assistant

Local voice and text planner for the ACE daily task report. It creates editable day plans and fills rows in a visible Chromium window. It never clicks Save or updates tickets. Review and save each draft in ACE yourself.

## Run on Windows

From `D:\ace_portal_automation`, run:

```powershell
.\start.ps1
```

Then open <http://127.0.0.1:8765>. Keep the terminal and all ACE draft tabs open until you have reviewed and saved each day. The launcher installs Python and frontend dependencies and Playwright Chromium on the first run. The existing `.env` is read on the backend; `ACE_USERNAME`/`ACE_PASSWORD` or the legacy `USERNAME`/`PASSWORD` names work. See `.env.example` for all settings.

Describe a day or record a short voice clip, create a plan, adjust descriptions/tickets/times, check the review box, and choose **Fill in ACE**. For a range, shared notes repeat on each weekday; choose separate notes when work differed by day. The app opens one ACE tab per filled date so navigating to the next day does not replace an unsaved draft. Existing populated grid rows cause that date to be skipped.

## Create tasks (ACE New Task)

Switch to **Create tasks** in the header. Type or speak one or more tickets; the assistant uses only your text or voice (no git or file scan). **Draft tasks** turns them into ACE New Task drafts matched to the exact ACE Task Type, Priority, Client, Module, FRD Nature and Status names. Set defaults for anything you usually leave unsaid. Edit every field, tick the review box and choose **Fill in ACE**: each task opens in its own ACE tab, is filled and verified, and has you (`ACE_ASSIGNEE`, default `Vineet Kukreti`) ticked in **Assign To : Employee**. The app never clicks **Save & Leave Open**; do that yourself in each tab. **Refresh from ACE** re-reads the option lists into `runtime/ace_task_form.json`.

## Draft with your agent (no Gemini needed)

Your own coding agent can investigate a day and write the draft instead of Gemini. It reads your notes, your
`my task updates` note for the day, your own commits and the files you changed under
`C:\Users\HP\Desktop\akhil_system`, and tags only tickets assigned to or completed by you (from the `ace_mcp`
reporting database). It never fills ACE.

One-time setup:

```powershell
.\setup_agents.ps1
```

This registers the `ace-timesheet` MCP server with Claude Code, Antigravity, Codex and Gemini CLI and installs the
`ace-timesheet` skill where the agent supports skills.

- **One click:** on the Timesheet tab pick a date (or range), pick an agent and choose **Draft with agent**. The draft
  lands in the review table with a "Based on" line per task. Review, tick the box and **Fill in ACE** as usual.
- **From chat:** with the assistant running, ask your agent "fill my ACE for 27 Oct". The draft appears on the
  Timesheet tab within 15 seconds; choose **Load**.

Verified agents (they reach the tools unattended and cannot write files): Antigravity (default), Claude Code, Codex.
Gemini CLI is hidden because Google no longer supports it for individual accounts. Agents may open only folders under
`akhil_system`; `.env` files, `runtime/`, `.git/`, `node_modules/` and key files are always refused. Settings:
`AGENT_DEFAULT`, `AGENT_TIMEOUT_SECONDS` (180 per day), `AGENT_SCAN_ROOT`, `ACE_MCP_PATH`, `ACE_GIT_AUTHOR` (`vineet`).
Agents stop after 60 seconds without loading context (`AGENT_STARTUP_TIMEOUT_SECONDS`), 90 seconds without new
tool progress (`AGENT_IDLE_TIMEOUT_SECONDS`), or five repetitions of the same tool activity. There is no automatic
retry. Each run allows ten investigative reads, including ticket lookups; reloading context does not reset them.
Identical source reads reuse their first result and still consume the budget. The three-submission rejection
limit includes invalid JSON shapes, missing fields, and submissions for the wrong date, for every agent.
Context is scanned once per run and reused during validation; accepted drafts return immediately. Closing the
draft stream cancels its worker and stops the agent. Existing explicit timeout settings still take precedence.
Codex emits JSON tool lifecycle events, which the activity feed and idle timer track; repeated wait messages
do not count as progress. Its ACE MCP server is required and individual tool calls time out after 60 seconds.
Git evidence reads use the native Windows Git binary, disconnected stdin and file-backed output. They stop
after ten seconds and return an error instructing the agent to use existing summaries or another source.

## Safety and recovery

- There is no `/save` or ticket-write endpoint. The app does not know whether you later clicked Save in ACE. The local `runtime/audit.jsonl` records draft fill events and explicitly marks them unsubmitted.
- The server checks dates, fixed dropdown values, task descriptions, contiguous times and at least nine hours before browser fill. It checks the ACE grid before adding and verifies each new row against the plan.
- A retry in the same running process resumes only if the live ACE draft is an exact prefix of the plan. If the browser or process closes after rows were added, inspect ACE and the local audit before rebuilding; unsaved browser drafts can disappear.
- Assigned tickets are suggestions. The app searches the ACE Assigned view from 2020 through today. If lookup fails or the grid is paginated, the plan remains usable with no-ticket tasks and a warning. Explicit ticket numbers are used only when present in the loaded assigned list.
- Date ranges are limited to 63 calendar days and skip Sundays (Monday–Saturday are working days). The app stops after a day that is interrupted; dates with existing entries are reported and skipped.
- The backend binds to `127.0.0.1` and stores browser state, screenshots, and audit records in ignored `runtime/`. Keep `.env` and `runtime/` private.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm test
npm run build
```

The older `backend/run_fill.py` command-line prototype remains in place with its synchronous models and rules. The web app uses `backend/app_*.py` modules and does not depend on that prototype.
