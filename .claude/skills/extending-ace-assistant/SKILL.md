---
name: extending-ace-assistant
description: Use when adding or changing a feature in the ACE assistant app — a backend endpoint, a request model, a streaming progress view, a new tab, a cross-tab flow, a setting — or when a new endpoint returns 403/404 in the dev server.
---

# Extending the ACE assistant

## Backend endpoint checklist (`backend/main.py`)

| Need | Do |
|---|---|
| Request body | a `StrictModel` (extra keys rejected — so a stale backend rejects new fields) |
| Protection | POSTs automatically require header `X-ACE-Client: 1`; add GET paths that expose data to the list in `local_requests` |
| Dev server | add the path prefix to the proxy list in `frontend/vite.config.js`, or `npm run dev` returns 404 |
| Errors | raise `ProviderError` (→ 502, agents/Sarvam), `PortalError` (→ 409, ACE), `ValueError` (→ 422); messages are shown to the user, so write them for the user |
| ACE work | inside `session.lock` (the `Timesheets` / `TaskCreator` methods already take it); reads use `session.background(path)` |
| Settings | `backend.config.setting('NAME', default)`; document new ones in `.env.example` |
| Long work with progress | copy an SSE endpoint (`/agent/draft-stream`, `/status/refresh-stream`): `asyncio.Queue`, a `worker` task, `on_progress(step, detail, icon)` → `{'type': 'step'…}`, then `{'type': 'result'…}` or `{'type': 'error'…}`; the frontend reads it with `streamEvents` |

## Frontend

- `api(path, body)` (`frontend/src/api.js`) adds the header and turns errors into `Error(detail)`.
- Tabs are the `MODES` list in `main.jsx`; `Root` keeps every tab mounted. A flow between tabs is `Root` state
  holding `{...data, at: Date.now()}` passed down as a prop and handled in a `useEffect` (examples: `jump`,
  `ideaNotes`, `ticketJob`, `linked`).
- Pure logic goes in `plan.js` / `agent.js` with vitest tests; components stay thin.
- Agent pickers: `GET /agent/agents`, keep `installed && verified`, remember the choice with
  `readStored/writeStored('ace.agent')` (`agent.js`, wraps localStorage in try/catch).
- Action rows use `.plan-action` / `.plan-buttons` (they wrap); check the layout at ~900 px.

## Rules a feature must keep

Timesheets never saved; tickets saved only via `/tasks/create` for user-selected drafts; agents read-only; ACE
writes audited to `runtime/audit.jsonl`. See CLAUDE.md "Rules that must hold".

## Finish

Tests for new logic (pytest per file, vitest), `npm run build`, screenshot the UI with stubbed routes
(verifying-ace-app), update README.md and CLAUDE.md if behaviour changed, and tell the user to restart the backend.
