---
name: testing-agent-drafts
description: Use when testing how the coding agents (Antigravity, Claude Code, Codex) draft timesheets or tickets — Draft with agent, agent_runner, the ace-timesheet MCP server, agent_json — or when an agent run times out, loops, gets rejected, finds "No work", or writes poor descriptions.
---

# Testing agent drafts

## Overview

Two agent paths, tested differently:

| Path | Entry | Agent gets | Output |
|---|---|---|---|
| Timesheet day | `agent_runner.run_for_day(agent, day, notes, on_progress, base_url)` (UI: Draft with agent → `/agent/draft-stream`) | the `ace-timesheet` MCP tools (`get_day_context`, `git_log`, `git_show`, `read_file`, `list_dir`, `get_ticket`, `submit_draft`) | a draft checked by `agent_drafts.accept_draft` |
| Tickets | `providers.agent_json(agent, prompt, schema)` via `app_tasks.make_task_drafts` (UI: Draft tasks) | one prompt, no tools | JSON matching `Suggestions` |

## Layer 1 — deterministic (always run)

`tests/test_agent_runner.py` swaps in `tests/fake_agent.py` as a `fake` recipe. Modes: `submit`, `silent`,
`reject`, `invalid-shape`, `idle`, `loop`, `linger`, `sleep`, `fail`. Add a mode there to reproduce a new agent
behaviour instead of calling a real CLI. Guards under test: 3 rejected submissions stop the run; 10-read budget per
run; startup 60 s, idle 90 s, total 180 s (`AGENT_*_TIMEOUT_SECONDS`); five identical tool events = loop.
`tests/test_agent_drafts.py` pins draft rules: 40–480 chars after `humanize`, ticket kept only if it is the user's,
no draft for Sundays, filled days or leave.

## Layer 2 — live (ask first: real CLIs, 10–180 s each, uses the user's agent quota)

- Tickets: call `make_task_drafts(notes, TaskDefaults(...), date, agent=...)` from the venv for each of
  `antigravity`, `claude`, `codex` with the same notes. Last measured: 19 s / 11 s / 28 s, all valid.
- Timesheet: needs a running backend (the MCP server calls back to the URL in `runtime/port.json`); call
  `run_for_day(..., base_url=that URL)` or POST `/agent/draft-stream` with `{"fromDate": "YYYY-MM-DD", "agent": "...", "notes": "..."}`.
  Pick a past working day that is not yet filled in ACE.

## Judging a live draft

| Check | Pass when |
|---|---|
| Grounded | every task traces to notes, daily note, commits or files (`evidence` / `source`) |
| Clean text | no file names, paths, repo names, hashes, ticket numbers in the description (`agent_context.FORBIDDEN`) |
| Voice | first person, past tense, says ask → action → status → blocker (`agent_context.VOICE`) |
| Tickets | only clearly matching ASPL numbers; none is better than a wrong one; `existingTicket` only from the user's list |
| Run health | no rejections, within the read budget, time per agent noted |

Run the same input on every agent and compare; one sample is not a result.

## Common mistakes

- Testing a live timesheet run with the backend stopped — the agent can't reach its tools and ends as "No work found".
- Passing a multi-line prompt as a CLI argument: Windows `.cmd` shims (codex) mangle it; it goes via stdin.
- Fixing a quality problem only in the prompt when a code check (`accept_draft`, `humanize`) could enforce it.
