"""ace-timesheet MCP server: lets any coding agent investigate a day and submit an ACE timesheet draft.

Reads (files, folders, git) run here, limited to the agent scan root. Context, tickets and drafts go through the
running ACE assistant backend. There is deliberately no fill or save tool.
"""
import json
from datetime import date as Date
from pathlib import Path
import httpx
from mcp.server.fastmcp import FastMCP
from backend.config import ROOT, RUNTIME, setting
from backend.services import safe_fs
from backend.services.safe_fs import AccessError, scan_root

PORT_FILE = RUNTIME / 'port.json'
SKILL = ROOT / 'agent' / 'ace-timesheet' / 'SKILL.md'
BACKEND_DOWN = 'ACE assistant is not running. Start it with start.ps1.'
HEADERS = {'X-ACE-Client': '1'}
# One MCP process belongs to one run. Re-fetching context must not refill its budget.
READ_BUDGET = 10
OUT_OF_READS = (f'Reading budget of {READ_BUDGET} reads used up. Write the tasks from what you already know and call '
                'submit_draft now.')
_reads = 0
_read_results = {}

mcp = FastMCP('ace-timesheet')


class BackendDown(RuntimeError):
    pass


def backend_url() -> str:
    if setting('ACE_BACKEND_URL'):
        return setting('ACE_BACKEND_URL').rstrip('/')
    try:
        info = json.loads(PORT_FILE.read_text(encoding='utf-8'))
        return f"http://{info['host']}:{info['port']}"
    except (OSError, ValueError, KeyError):
        raise BackendDown(BACKEND_DOWN) from None


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    try:
        return httpx.request(method, backend_url() + path, headers=HEADERS, timeout=180, **kwargs)
    except httpx.RequestError:
        raise BackendDown(BACKEND_DOWN) from None


def _event(message: str) -> None:
    try:
        httpx.post(backend_url() + '/agent/event', json={'message': message}, headers=HEADERS, timeout=2)
    except (BackendDown, httpx.HTTPError):
        pass


def skill_text() -> str:
    return SKILL.read_text(encoding='utf-8').split('---', 2)[-1].strip()


def _read(message: str, fn, *args):
    global _reads
    _event(message)
    if _reads >= READ_BUDGET:
        return {'error': OUT_OF_READS}
    _reads += 1
    # Agents sometimes ask for the same source repeatedly. Never redo its I/O.
    key = (fn.__module__, fn.__qualname__, message, tuple(str(arg) for arg in args))
    if key not in _read_results:
        _read_results[key] = _guard(fn, *args)
    return _read_results[key]


def _guard(fn, *args):
    try:
        return fn(*args)
    except (AccessError, BackendDown) as error:
        return {'error': str(error)}


@mcp.tool()
def get_day_context(date: str) -> dict:
    """Start here. Returns step-by-step instructions, the rules, the user's notes and daily note, their commits,
    changed files grouped by project, and their own tickets for one date (YYYY-MM-DD), plus whether the day is a
    working day, already filled or leave. Follow the returned instructions exactly."""
    def run():
        _event(f'Reading your notes, commits, files and tickets for {date}')
        response = _request('GET', '/agent/context', params={'date': date})
        if not response.is_success:
            return {'error': response.json().get('detail')}
        return {'instructions': skill_text(), **response.json()}
    return _guard(run)


@mcp.tool()
def get_ticket(aspl: str) -> dict:
    """Full details of one of the user's tickets, e.g. ASPL-172905. Returns an error for tickets that are not theirs."""
    def run():
        response = _request('GET', f'/agent/tickets/{aspl}')
        return response.json() if response.is_success else {'error': response.json().get('detail')}
    return _read(f'Checking ticket {aspl}', run)


@mcp.tool()
def submit_draft(date: str, tasks: list[dict], summary: str = '') -> dict:
    """Submit the day's draft. Each task: description (40-480 chars), ticket (ASPL-number or null), evidence (short
    note of what it is based on), durationMinutes (number or null). Returns ok and the plan, or ok false with
    errors to fix and resubmit."""
    def run():
        _event('Submitting the draft')
        response = _request('POST', '/agent/submit', json={'date': date, 'tasks': tasks, 'summary': summary})
        if response.is_success:
            return {'ok': True, 'plan': response.json()['plan']}
        detail = response.json().get('detail')
        if not isinstance(detail, list):
            detail = [detail]
        return {'ok': False, 'errors': [d if isinstance(d, str) else f"{'.'.join(map(str, d.get('loc', [])))}: "
                                        f"{d.get('msg')}" for d in detail]}
    return _guard(run)


@mcp.tool()
def list_dir(path: str) -> list[dict] | dict:
    """List a folder inside the user's work folder (private and generated folders are hidden)."""
    return _read(f'Looking in {path}', safe_fs.list_dir, path, scan_root())


@mcp.tool()
def read_file(path: str, offset: int = 0) -> dict:
    """Read a text file inside the user's work folder, up to 60,000 characters from offset."""
    return _read(f'Reading {path} at offset {offset}', safe_fs.read_file, path, scan_root(), offset)


@mcp.tool()
def git_log(repo: str, date: str) -> list[dict] | dict:
    """Commits made on a date (YYYY-MM-DD) in a repository folder (use repoPath from the day context)."""
    try:
        day = Date.fromisoformat(date)
    except ValueError:
        return {'error': 'Use a YYYY-MM-DD date.'}
    return _read(f'Checking commits in {repo} for {date}', safe_fs.git_log, repo, day, scan_root())


@mcp.tool()
def git_show(repo: str, commit: str) -> dict:
    """Show one commit's message, changed files and diff (secrets excluded)."""
    return _read(f'Looking at commit {commit} in {repo}', safe_fs.git_show, repo, commit, scan_root())


@mcp.prompt()
def fill_ace_day(date: str) -> str:
    """Draft the ACE timesheet for one date."""
    return f'{skill_text()}\n\nDraft the ACE timesheet for {date}.'


def main():
    mcp.run()
