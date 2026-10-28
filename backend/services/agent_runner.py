"""Runs a local coding agent CLI headless so it can draft one timesheet day through the ace-timesheet tools."""
import asyncio
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable
from backend.config import ROOT, RUNTIME, setting
from backend.services import agent_drafts
from backend.services.agent_drafts import ActiveRun
from backend.services.providers import ProviderError
from backend.services.safe_fs import scan_root

SHIM = ROOT / 'ace_timesheet_mcp.py'
PYTHON = ROOT / '.venv' / 'Scripts' / 'python.exe'
MAX_REJECTS = 3
AGY_WORKSPACE = ROOT / 'agent' / 'agy-workspace'
AGY_SETTINGS = Path.home() / '.gemini' / 'antigravity-cli' / 'settings.json'


@dataclass
class Recipe:
    id: str
    label: str
    exe: str
    build: Callable[[str, Path, Path], list[str]]  # (prompt, scan root, mcp config file) -> arguments
    cwd: Path | None = None  # defaults to the scan root


# Every recipe must keep the agent read-only: it may call the ace-timesheet MCP tools and nothing that writes.
# Checked on 2026-10-27 with a real draft and a write probe (setup_agents.ps1 registers the server first):
# - agy: runs from agent/agy-workspace, whose .agents/hooks.json denies every tool except ace-timesheet MCP calls
#   (built-in file reads need no permission otherwise); headless mode also auto-denies tools without an allow rule.
#   (--mode plan is ignored with --disable-slash-commands and still blocks MCP calls.)
# - claude: --tools "" removes built-in Read/Grep/Bash/Write; only the strict MCP config's tools remain.
# - codex: read-only sandbox, shell tool disabled, MCP tools pre-approved, ACE_BACKEND_URL forwarded to the server.
# - gemini: not verified; the CLI stops with IneligibleTierError for individual accounts.
RECIPES = {
    'antigravity': Recipe('antigravity', 'Antigravity', 'agy', lambda prompt, root, cfg: [
        '-p', prompt, '--output-format', 'text'], cwd=AGY_WORKSPACE),
    'claude': Recipe('claude', 'Claude Code', 'claude', lambda prompt, root, cfg: [
        '-p', prompt, '--mcp-config', str(cfg), '--strict-mcp-config', '--allowedTools', 'mcp__ace-timesheet',
        '--tools', '', '--permission-mode', 'dontAsk', '--output-format', 'text']),
    'codex': Recipe('codex', 'Codex', 'codex', lambda prompt, root, cfg: [
        'exec', '--json', '--skip-git-repo-check', '-s', 'read-only', '--disable', 'shell_tool', '-C', str(root),
        '-c', 'approval_policy="never"', '-c', 'mcp_servers.ace-timesheet.default_tools_approval_mode="approve"',
        '-c', 'mcp_servers.ace-timesheet.required=true', '-c', 'mcp_servers.ace-timesheet.tool_timeout_sec=60',
        '-c', 'mcp_servers.ace-timesheet.env_vars=["ACE_BACKEND_URL"]', prompt]),
    'gemini': Recipe('gemini', 'Gemini CLI', 'gemini', lambda prompt, root, cfg: [
        '-p', prompt, '--allowed-mcp-server-names', 'ace-timesheet', '--approval-mode', 'plan',
        '--output-format', 'text']),
}
VERIFIED = {'antigravity', 'claude', 'codex'}


def antigravity_read_only(settings: Path = AGY_SETTINGS) -> bool:
    """Headless agy is read-only only while its allow list holds nothing but the ace-timesheet tools."""
    try:
        allow = json.loads(settings.read_text(encoding='utf-8')).get('permissions', {}).get('allow', [])
    except (OSError, ValueError, AttributeError):
        return False
    return bool(allow) and all(str(rule).startswith('mcp(ace-timesheet/') for rule in allow)


def available_agents() -> list[dict]:
    order = [setting('AGENT_DEFAULT', 'antigravity')] + [k for k in RECIPES if k != setting('AGENT_DEFAULT', 'antigravity')]
    return [{'id': k, 'label': RECIPES[k].label, 'installed': bool(shutil.which(RECIPES[k].exe)),
             'verified': k in VERIFIED} for k in order if k in RECIPES]


def agent_prompt(day: date) -> str:
    return (f'Draft my ACE timesheet for {day.isoformat()}. First call the get_day_context tool of the ace-timesheet '
            f'MCP server for that date and follow the instructions it returns exactly. Use only the ace-timesheet '
            f'tools. Call get_day_context once; use notes directly when sufficient. Make at most 10 additional '
            f'reads, never repeat an identical tool call, and finish by calling submit_draft. '
            f'Fix a rejected draft at most twice. If there is no evidence, reply No work found for {day.isoformat()}.')


def _no_spaces(path: Path) -> str:
    """agy runs hooks through cmd /c and mangles quoted paths, so use the 8.3 short path when the path has spaces."""
    text = str(path)
    if ' ' in text and os.name == 'nt':
        import ctypes
        buffer = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(text, buffer, 1024):
            text = buffer.value
    return text if ' ' not in text else 'python'


def write_agy_hooks(workspace: Path = AGY_WORKSPACE) -> Path:
    """Points the workspace hook at this install's Python, so the deny-all-but-ACE gate always runs."""
    python = _no_spaces(PYTHON if PYTHON.exists() else Path(sys.executable))
    path = workspace / '.agents' / 'hooks.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'ace-only': {'PreToolUse': [{'matcher': '*', 'hooks': [
        {'type': 'command', 'command': f'{python} ace_only_hook.py', 'timeout': 10}]}]}}, indent=2), encoding='utf-8')
    return path


def write_mcp_config(base_url: str | None) -> Path:
    path = RUNTIME / 'agent_mcp.json'
    python = str(PYTHON if PYTHON.exists() else Path(sys.executable))
    server = {'command': python, 'args': [str(SHIM)], 'env': {'ACE_BACKEND_URL': base_url} if base_url else {}}
    path.write_text(json.dumps({'mcpServers': {'ace-timesheet': server}}), encoding='utf-8')
    return path


def _kill(proc) -> None:
    if proc.returncode is not None:
        return
    if os.name == 'nt':
        # .cmd shims start node children; kill the whole tree.
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
    else:
        proc.kill()


def _drain(run: ActiveRun, on_progress) -> list[str]:
    steps = []
    while run.events:
        event = run.events.popleft()
        on_progress(event['step'], event.get('detail'), event.get('icon'))
        steps.append(event['step'])
    return steps


async def _watch_cli(proc, run: ActiveRun, on_progress, label: str):
    """Drain both pipes continuously; observe lifecycle metadata, never persist source text."""
    seen = set()

    def observe(line):
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError):
            return
        if not isinstance(event, dict):
            return
        item = event.get('item') or {}
        if not isinstance(item, dict) or item.get('type') != 'mcp_tool_call':
            return
        key = (item.get('id'), event.get('type'))
        if key in seen:
            return
        seen.add(key)
        run.cli_progress_at = asyncio.get_running_loop().time()
        run.cli_tool = str(item.get('tool', 'MCP tool'))[:100]
        run.cli_tool_status = str(item.get('status', event.get('type')))[:50]
        on_progress(f'{label}: {run.cli_tool} {run.cli_tool_status}', None, 'ai')

    async def drain(stream):
        pending = b''
        while chunk := await stream.read(8192):
            pending += chunk
            while b'\n' in pending:
                line, pending = pending.split(b'\n', 1)
                observe(line)
            # Bound memory even for a provider emitting huge, non-JSON text.
            if len(pending) > 1_000_000:
                pending = b''
        if pending:
            observe(pending)

    await asyncio.gather(drain(proc.stdout), drain(proc.stderr))
    await proc.wait()


async def run_for_day(agent: str, day: date, notes: str, on_progress, base_url: str | None = None,
                      timeout: float | None = None):
    recipe = RECIPES[agent]
    exe = shutil.which(recipe.exe)
    if not exe:
        raise ProviderError(f'{recipe.label} is not installed or not on PATH. Pick another agent.')
    timeout = timeout if timeout is not None else float(setting('AGENT_TIMEOUT_SECONDS', '180'))
    startup_timeout = float(setting('AGENT_STARTUP_TIMEOUT_SECONDS', '60'))
    idle_timeout = float(setting('AGENT_IDLE_TIMEOUT_SECONDS', '90'))
    if agent == 'antigravity':
        write_agy_hooks()
    if agent == 'antigravity' and not antigravity_read_only():
        raise ProviderError('Antigravity has extra allow rules in ~/.gemini/antigravity-cli/settings.json, so it could '
                            'change files when run unattended. Run setup_agents.ps1 or pick another agent.')
    root = scan_root()
    config = write_mcp_config(base_url)
    env = {**os.environ, **({'ACE_BACKEND_URL': base_url} if base_url else {})}
    run = agent_drafts.current = ActiveRun(day=day, notes=notes)
    proc = None
    waiter = None
    try:
        proc = await asyncio.create_subprocess_exec(
            exe, *recipe.build(agent_prompt(day), root, config), cwd=str(recipe.cwd or root), env=env,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        on_progress(f'{recipe.label} is investigating {day.isoformat()}', None, 'ai')
        waiter = asyncio.create_task(_watch_cli(proc, run, on_progress, recipe.label))
        clock = asyncio.get_running_loop().time
        started = last_progress = clock()
        deadline = started + timeout
        seen_steps = set()
        repeats = {}
        context_seen = False
        while not waiter.done() and run.plan is None and run.rejects < MAX_REJECTS:
            steps = _drain(run, on_progress)
            if any(step not in seen_steps for step in steps) or run.context_seen != context_seen:
                last_progress = clock()
            last_progress = max(last_progress, run.cli_progress_at)
            seen_steps.update(steps)
            for step in steps:
                repeats[step] = repeats.get(step, 0) + 1
            context_seen = run.context_seen
            if any(count >= 5 for count in repeats.values()):
                raise ProviderError(f'{recipe.label} repeated the same tool activity 5 times and was stopped '
                                    'to prevent a loop. Try another agent or provide more specific notes.')
            if clock() > deadline:
                raise ProviderError(f'{recipe.label} took longer than {timeout / 60:g} minutes and was stopped. '
                                    'No automatic retry was started. Try shorter notes or another agent.')
            if not run.context_seen and clock() - started > startup_timeout:
                raise ProviderError(f'{recipe.label} did not load the day context within {startup_timeout:g} seconds '
                                    'and was stopped. Check its login and MCP setup, or pick another agent.')
            if clock() - last_progress > idle_timeout:
                detail = (f' Last CLI tool: {run.cli_tool} ({run.cli_tool_status}).' if run.cli_tool else '')
                raise ProviderError(f'{recipe.label} produced no new tool events for {idle_timeout:g} seconds '
                                    f'and was stopped.{detail} This does not establish a loop; '
                                    'the tool connection or model may be waiting.')
            await asyncio.wait({waiter}, timeout=0.5)
        _drain(run, on_progress)
        if waiter.done():
            waiter.result()
        if run.plan is not None:
            # The accepted draft is the result; do not wait for a CLI closing message.
            return run.plan
        if run.rejects >= MAX_REJECTS:
            _kill(proc)
            raise ProviderError(f"Your agent's draft was rejected {MAX_REJECTS} times: " + '; '.join(run.last_errors))
        if not run.context_seen:
            if proc.returncode:
                raise ProviderError(f'{recipe.label} stopped with an error. Check it is logged in, or pick another agent.')
            raise ProviderError(f'{recipe.label} did not reach the ACE tools. Run setup_agents.ps1, then retry.')
        if proc.returncode:
            raise ProviderError(f'{recipe.label} stopped with an error. Check it is logged in, or pick another agent.')
        if run.rejects:
            raise ProviderError(f"Your agent's draft was not accepted: " + '; '.join(run.last_errors))
        return None
    finally:
        agent_drafts.current = None
        if proc is not None:
            _kill(proc)
        if waiter is not None:
            try:
                await asyncio.wait_for(asyncio.shield(waiter), 5)
            except asyncio.TimeoutError:
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
