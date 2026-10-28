# Agent-drafted timesheet — design

Date: 2026-10-27 · Status: approved 2026-10-27 · Owner: Vineet Kukreti

**Scan scope (user decision, 2026-10-27):** the agent may list and open only project folders under
`C:\Users\HP\Desktop\akhil_system` (which includes `my task updates`). Desktop loose items, Downloads and
`D:/ace_portal_automation` are excluded from the agent path. `runtime/`, `.env*` files and secrets are never readable
through the MCP tools.

## Why

Planning a day currently depends on the Gemini API (`providers.gemini_json`). When Gemini returns HTTP 503 the
Timesheet tab cannot produce a plan at all. Even when it works, the model only sees a thin digest (file names and
commit subjects from `activity_gatherer.py`), so descriptions are vague.

The user already runs capable coding agents locally — Claude Code (`claude`), Antigravity (`agy`), Codex (`codex`) and
Gemini CLI (`gemini`), all on PATH. Those agents can open the real files, diffs and notes. The goal is to let any of
them be the "brain" that investigates a day and writes the timesheet draft, while this app stays the "hands" that
enforces the rules and fills ACE. Descriptions are read by the user's managers, so they must be accurate, concise and
professional.

## What the user said vs. assumptions

Said:
- Use the coding agent (Antigravity first; any agent should work) instead of Gemini to fill ACE.
- One click from the existing UI; also usable by typing to the agent ("start helping me" / "fill my ACE for …").
- The agent works out what was done on that date from the files and folders created/changed that day (their
  metadata), and understands the work from them.
- Use tickets assigned to the user or already completed by the user so the right ASPL number is attached.
- Descriptions must be accurate, more informative, correct and concise — higher-ups read them.
- Approve in one place: the draft lands in the existing review table; the user clicks Fill in ACE. (Agreed.)
- MCP server + skill as the integration (agreed in playback).

Assumed (builder's/my calls — change here if wrong):
- Default agent is Antigravity (`agy`); the UI offers a dropdown for Claude Code / Codex / Gemini CLI.
- Ticket source is the `ace_mcp` reporting database (sibling project `../ace_mcp`), falling back to the scraped
  Assigned list (`runtime/tickets_cache.json` / `GET /tickets`) when the DB is unreachable.
- The user's daily note in `C:\Users\HP\Desktop\akhil_system\my task updates\` is the most trusted source when present.
- The existing "plan from my notes/voice" flow stays as it is (Gemini/agy prompt). This adds a new path; it does not
  remove the old one.
- New Task creation (Create tasks tab) is out of scope for v1.
- **Agents get no shell (my call).** `agy` has no tool allow-list or per-run MCP config (`--help` shows only
  `--mode plan`, `--sandbox`, `--dangerously-skip-permissions`), so read-only cannot be enforced through each CLI's own
  shell. Instead the MCP server provides read-only tools (`git_log`, `git_show`, `read_file`, `list_dir`), each
  limited to the allowed scan roots, and every agent runs with MCP tools only (plus its own read-only file tools
  where the CLI can restrict to them). The builder must verify that MCP tool calls are not blocked by permission
  prompts in each CLI's headless mode. An agent that cannot run unattended this way is hidden from the dropdown.
- **Tickets are restricted to the user's own (my call, from the anti-goal).** A ticket can be attached only if it is
  in the user's set: assigned to the user (`Employee Name` contains `ACE_ASSIGNEE`) or completed by the user, at any
  date. `get_ticket` searches only that set. Any other ASPL number is dropped with a warning.
- **Typed or dictated notes go to the agent (my call).** `POST /agent/draft` accepts the same `notes` / `perDay`
  fields as `RangeRequest`. When present, they are the most trusted source, ahead of the daily-note file.
- **Ticket DB verified 2026-10-27:** the `ace_mcp` view returns 21 tickets for `Vineet  Kukreti` (note the double
  space; match by `find_employee`/contains), 13 of them completed by him, e.g. ASPL-172905 (26/10/2026). So it works
  as the primary source.

## Goals

1. **Draft with agent** button on the Timesheet tab: pick date (or range), pick agent, click. Draft appears in the
   existing editable review table with live progress while the agent works.
2. Same capability from chat: in any MCP-capable agent, "fill my ACE for 27 Oct" uses the same skill and tools and the
   draft shows up in the same review table.
3. Each task carries an ASPL ticket when the work clearly matches one assigned to / completed by the user, and a short
   **based on** line (evidence) visible only in the review UI.
4. No dependency on Gemini or Jev for this path.

## Non-goals

- The agent never fills ACE, never clicks Save, never writes to ACE tickets. Filling stays behind the existing
  review checkbox and **Fill in ACE** button (`POST /fill`) with all its current checks.
- No change to time rules, workplace rule, ≥ 9h check, existing-entries skip, or the Fill engine.
- No hosted service; everything is local (backend stays bound to 127.0.0.1).

## Anti-goals (failure even if it "works")

- A description states work that did not happen, or misattributes a ticket. Prefer no ticket over a wrong one;
  prefer fewer, true tasks over padded ones.
- Descriptions containing file names, paths, repo names, commit hashes, or "modified X file" phrasing (existing
  `humanize` rules and the voice in `providers.gemini` prompt apply).
- The headless agent changes anything on disk (it must be read-only).
- Personal or unrelated files (e.g. Downloads clutter) leak into a description.

## How it fits

```
UI "Draft with agent" ──► POST /agent/draft {date(s), agent}
                              │  backend spawns agent CLI headless (read-only, cwd = akhil_system root)
                              ▼
                    agent + skill "ace-timesheet" ──► MCP server "ace-timesheet" (stdio, this repo)
                              │   get_day_context(date)   → rules, daily note, activity, candidate tickets
                              │   (agent reads files / git diffs itself to understand the work)
                              │   submit_draft(date, tasks) → backend validates + allocates times
                              ▼
                    backend stores draft ─► UI picks it up (SSE) ─► review table ─► Fill in ACE (unchanged)

Chat path: user's agent (already configured with the MCP server + skill) calls the same two tools; the UI shows the
draft under "Drafts from your agent".
```

### 1. MCP server (`ace-timesheet`)

A small stdio MCP server in this repo (Python, FastMCP — same style as `../ace_mcp`). It talks to the running local
backend over HTTP (with the `x-ace-client: 1` header the middleware requires). If the backend is not running, tools
return a clear "start the ACE assistant (`start.ps1`)" error. Tools:

- **`get_day_context(date)`** → one JSON object:
  - `date`, `isWorkingDay`, `workplace`, `alreadyFilled` (from status cache / live check), `onLeave`.
  - `dailyNote`: text of the matching file in `my task updates` (file names vary: `17-9-2026.txt`, `18-9-26.txt`;
    match D-M-YYYY and D-M-YY), else null.
  - `activity`: git commits on that date across scan roots **with repo absolute path, full message, timestamp and
    changed files** (so the agent can `git show` them), plus files/folders created or modified that date **with full
    paths and mtimes** — a richer version of `gather_day_activity` (recurse inside project folders, skip
    `node_modules`, `.venv`, `.git`, `dist`, `build`, `__pycache__`, `runtime`).
  - `candidateTickets`: tickets assigned to the user (any status) plus tickets completed/updated by the user within
    ±7 days of the date, each with ASPL number, description, module, task type, status, relevant dates.
  - `rules`: description length limit (480 chars before the ticket prefix), voice rules, "no file names" rule — so
    the agent does not depend on the skill text alone.
- **`get_ticket(aspl)`** → full details for one ticket (to confirm a match).
- **`submit_draft(date, tasks[], summary)`** where each task is `{description, ticket|null, evidence,
  durationMinutes|null, order}`:
  - Backend applies `humanize`, ticket prefix `[ASPL-…] `, `allocate_natural` times, workplace, and `DayPlan`
    validation. Ticket must exist in the candidate set or be confirmed by `get_ticket`, else it is dropped with a
    warning.
  - Returns the validated plan, or a precise list of errors so the agent can fix and resubmit.
  - Stores the draft (`runtime/agent_drafts/<date>.json`, latest wins) and notifies the UI.

No `fill` or `save` tool exists on purpose.

### 2. Skill (`ace-timesheet`)

One instruction file, written agent-neutral, installed where each agent looks for it (Claude Code skill folder,
Antigravity/Gemini/Codex equivalents or their AGENTS.md/GEMINI.md). It tells the agent how to work:

1. Call `get_day_context`. If not a working day, already filled, or on leave → report and stop.
2. Start from the daily note if present; then open the actual changes (`git show`, read changed files, skim new
   documents) to understand *what the work was* in functional terms.
3. Group activity into distinct tasks (meetings, guidance, reviews from the note count too). Order logically; give
   `durationMinutes` only when evidence supports it (e.g. commit time spread); otherwise null.
4. Match tickets conservatively: only when the work clearly is that ticket; call `get_ticket` to confirm.
5. Write descriptions in the established voice (first person, past tense, plain English, what/what I did/where it
   stands/blockers, 350–480 chars when evidence allows, no filler, no file names). Never invent people, outcomes or
   blockers.
6. `submit_draft`; fix any errors; finish with a two-line summary.
7. Never edit files, never run commands that change anything, never fill ACE.

If no activity and no note exist for the date, submit nothing and say so (the UI then suggests dictating instead).

### 3. Backend changes

- `POST /agent/draft {dates[], agent}` — spawns the chosen agent CLI headless, one run per date, sequentially, under
  the existing `planning_lock`. Streams progress over SSE (reuse the `plan-stream` event shape: `step`, `result`,
  `error`). Progress comes from (a) MCP tool calls hitting the backend ("Agent read the day context", "Agent submitted
  a draft"), and (b) the agent's streamed output where the CLI supports it. Timeout per date (default 5 min,
  configurable). Ranges keep the 63-day limit and skip Sundays.
- Per-agent launch recipe (config, not code-hardwired where possible): command, prompt flag, how to pass the MCP
  config, how to restrict to read-only tools, model/effort flags. Read-only enforcement is required for each agent.
- Internal endpoints used by the MCP server: day context, ticket lookup, draft submit, draft list. Same local-only
  middleware.
- `Task` model gets an optional `evidence` field (shown in UI, never typed into ACE). `fill` ignores it.
- Ticket provider: query `../ace_mcp` DB (path via `ACE_MCP_PATH` setting) for the user (`ACE_ASSIGNEE`, default
  `Vineet Kukreti`); fall back to the scraped list with a warning.
- One-time setup script (`setup_agents.ps1`) registering the MCP server and installing the skill for each installed
  agent, idempotent.

### 4. UI changes (Timesheet tab)

- Next to the existing plan button: agent dropdown (remembered locally) + **Draft with agent**.
- Live progress list (existing progress component).
- Review table unchanged, plus a muted "based on: …" line under each task and the ticket tag.
- A small "Drafts from your agent" notice when a draft arrived from the chat path; clicking loads it into the table.

## Errors and edge cases

- Agent CLI missing / not logged in / times out / exits non-zero → clear message naming the agent; suggest another
  agent from the dropdown.
- Agent submits nothing → "No work found for <date>; dictate the day instead."
- Agent submits invalid draft repeatedly → after 3 rejected submits, surface the last errors to the user.
- ACE MCP DB unreachable → fallback tickets + warning in the draft.
- Same date drafted twice → latest draft replaces earlier one in the UI only after the user confirms if they had
  edited the current one.

## Testing

- Unit: daily-note filename matching; activity collection on a temp git repo; `submit_draft` validation (ticket
  prefix, unknown ticket dropped, humanize, time allocation, ≥ 9h); evidence field excluded from fill.
- MCP server: tool calls against a test backend.
- Launcher: each agent recipe builds the expected command line; read-only flags present.
- Manual end-to-end: one real past date with each installed agent; compare quality against what the user filled.

## Left to the builder

Exact headless flags per agent CLI (verify against each tool's current `--help`), SSE plumbing, file layout, how the
MCP server discovers the backend port (`runtime/port.json` exists), and UI styling consistent with the current app.
