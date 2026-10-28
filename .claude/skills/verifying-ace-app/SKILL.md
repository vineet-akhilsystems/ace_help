---
name: verifying-ace-app
description: Use when checking that a change to the ACE assistant (backend, frontend or agent flow) works before calling it done — running its tests, building, or looking at the UI — or when pytest hangs, the UI looks broken, or the app shows errors after a change.
---

# Verifying changes to the ACE assistant

## Overview

Verify with the cheapest check that proves the change, and never by touching ACE in a way that writes. The user's
backend is usually running from `start.ps1`; it does **not** reload, so they must restart it to pick up backend
changes.

## Quick reference (repo root, PowerShell or Bash)

| Check | Command |
|---|---|
| Backend tests, one file | `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/test_tasks.py` |
| All backend tests (Bash) | `for f in tests/test_*.py; do timeout 120 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider $f \| tail -1; done` (run in background) |
| All backend tests (PowerShell) | `Get-ChildItem tests\test_*.py \| ForEach-Object { .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider $_.FullName \| Select-Object -Last 1 }` |
| Frontend tests | `cd frontend && npx vitest run` |
| Build | `cd frontend && npm run build` |

A single `pytest` over the whole suite has hung for many minutes here; per-file runs finish in ~2 minutes total
(`test_agent_runner.py` ≈ 50 s, `test_browser_fill.py` ≈ 20 s).

## Looking at the UI without ACE

The Vite dev server (`npm run dev`, port 5174) is often already running. Drive it with the venv's Playwright and
**stub the API** with `page.route`, so no backend or ACE call happens:

```python
import asyncio
from playwright.async_api import async_playwright

def reply(body):            # route handlers receive (route) — bind the body via a closure, not a lambda default
    async def handle(route): await route.fulfill(json=body)
    return handle

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1300, 'height': 900})
        await page.route('**/agent/agents', reply([{'id': 'antigravity', 'label': 'Antigravity', 'installed': True, 'verified': True}]))
        await page.goto('http://127.0.0.1:5174', wait_until='load')   # not 'networkidle': polling never idles
        await page.get_by_role('tab', name='Create tasks').click()
        await page.screenshot(path='<scratchpad>/tasks.png')
        print(await page.evaluate('document.documentElement.scrollWidth > innerWidth'))  # True = horizontal overflow
        await browser.close()
asyncio.run(main())
```

Build `/task-options` stubs from `runtime/ace_task_form.json`. Set `PYTHONIOENCODING=utf-8` when printing UI text
(arrows like ↗ crash the Windows console). Read the PNG to look at it; check at 1300 px and ~900 px widths.

## Live agent checks

`backend.services.providers.agent_json(agent, prompt, schema)` can be called directly with each of `antigravity`,
`claude`, `codex` (10–30 s each) to confirm structured drafting works end to end.

## Common mistakes

| Symptom | Cause |
|---|---|
| `agent: Extra inputs are not permitted`, or old error texts after a change | stale backend — ask the user to restart `start.ps1` |
| Python snippet behaves oddly after a Bash heredoc | the shell mangled `\b`/`\n` in string literals — use the Edit tool or `chr(92)` |
| Claiming ticket saving works | it can only be proven in real ACE by the user; say so instead |
