"""Read-only file and git access for coding agents, limited to the agent scan root."""
import re
import os
import shutil
import subprocess
import tempfile
from datetime import date, datetime
from pathlib import Path
from backend.config import ROOT, setting

# Never listed or opened through the agent tools.
SKIP_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'runtime', 'dist', 'build', '.next',
             '.pytest_cache'}
SECRET_FILES = {'storage_state.json'}
SECRET_SUFFIXES = ('.pem', '.key', '.pfx', '.p12', '.jks', '.env')
GIT_READ_TIMEOUT_SECONDS = 10


def scan_root() -> Path:
    return Path(setting('AGENT_SCAN_ROOT') or Path.home() / 'Desktop' / 'akhil_system').resolve()


def excluded_folders() -> list[Path]:
    """Folders that are never ACE work: this assistant itself, plus any in AGENT_EXCLUDE (separated by ;)."""
    extra = [Path(p.strip()).resolve() for p in setting('AGENT_EXCLUDE').split(';') if p.strip()]
    return [ROOT.resolve(), *extra]


def is_excluded(path: Path) -> bool:
    return any(path == folder or folder in path.parents for folder in excluded_folders())


def is_blocked_name(name: str) -> bool:
    # Dot-names cover .env*, .git, .claude settings, .npmrc and similar files that often hold tokens.
    lower = name.lower()
    return (lower.startswith('.') or lower in SKIP_DIRS or lower in SECRET_FILES or lower.endswith(SECRET_SUFFIXES)
            or lower.startswith('id_rsa') or 'credential' in lower)


COMMIT = re.compile(r'^[0-9a-f]{7,40}$')
EXCLUDE_SECRETS = ['--', '.'] + [f':(exclude,glob,icase){pattern}' for pattern in (
    '**/.*', '**/.*/**', '**/runtime/**', '**/storage_state.json', '**/*.env', '**/*.pem', '**/*.key', '**/*.pfx',
    '**/*.p12', '**/*.jks', '**/id_rsa*', '**/*credential*')]


class AccessError(ValueError):
    pass


def allowed_path(path: str, root: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, ValueError):
        raise AccessError(f'{path} is outside the allowed folder ({root}) or does not exist.') from None
    if any(is_blocked_name(part) for part in relative.parts):
        raise AccessError(f'{path} is private or generated content and cannot be opened.')
    if is_excluded(resolved):
        raise AccessError(f'{path} is in a folder excluded from timesheet work (the ACE assistant itself).')
    return resolved


def list_dir(path: str, root: Path) -> list[dict]:
    folder = allowed_path(path, root)
    if not folder.is_dir():
        raise AccessError(f'{path} is not a folder.')
    entries = []
    for item in sorted(folder.iterdir()):
        if item.name.startswith('.') or is_blocked_name(item.name):
            continue
        try:
            stat = item.stat()
        except OSError:
            continue
        entries.append({'name': item.name, 'kind': 'folder' if item.is_dir() else 'file', 'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')})
    return entries[:500]


def read_file(path: str, root: Path, offset: int = 0, max_chars: int = 60_000) -> dict:
    target = allowed_path(path, root)
    if not target.is_file():
        raise AccessError(f'{path} is not a file.')
    with target.open('rb') as handle:
        if b'\x00' in handle.read(8192):
            raise AccessError('Binary file; describe it from its name and folder instead.')
    text = target.read_text(encoding='utf-8', errors='replace')
    chunk = text[max(offset, 0):max(offset, 0) + max_chars]
    return {'path': str(target), 'text': chunk, 'truncated': max(offset, 0) + max_chars < len(text)}


def _repo(repo: str, root: Path) -> Path:
    folder = allowed_path(repo, root)
    if not (folder / '.git').exists():
        raise AccessError(f'{repo} is not the top folder of a git repository.')
    return folder


def _git(folder: Path, args: list[str]) -> str:
    executable = Path(shutil.which('git') or 'git')
    # Git for Windows' cmd launcher spawns another git.exe. Use the real binary
    # when available, so a timeout cannot leave that child holding output pipes.
    native = executable.parent.parent / 'mingw64' / 'bin' / 'git.exe'
    if os.name == 'nt' and native.is_file():
        executable = native
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    env.update(GIT_TERMINAL_PROMPT='0', GIT_PAGER='cat', GIT_OPTIONAL_LOCKS='0')
    # Files avoid subprocess.run's unbounded post-timeout communicate() wait
    # when a Windows descendant inherits stdout/stderr and remains alive.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen([str(executable), '-C', str(folder), '-c', 'core.pager=cat', *args],
                                stdin=subprocess.DEVNULL, stdout=out, stderr=err, env=env)
        try:
            proc.wait(timeout=GIT_READ_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                try:
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if proc.poll() is None:
                proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            raise AccessError(f'Git read exceeded {GIT_READ_TIMEOUT_SECONDS:g} seconds. Use the commit summary or other sources; '
                              'do not repeat this read.') from None
        out.seek(0)
        err.seek(0)
        if proc.returncode != 0:
            raise AccessError('git could not read that: ' + err.read(800).decode('utf-8', errors='replace').strip()[:200])
        return out.read().decode('utf-8', errors='replace')


def git_log(repo: str, day: date, root: Path) -> list[dict]:
    out = _git(_repo(repo, root), ['log', f'--since={day} 00:00:00', f'--until={day} 23:59:59', '--name-only',
                                   '--pretty=format:%x1e%h|%an|%cI|%s'])
    commits = []
    for block in filter(str.strip, out.split('\x1e')):
        head, *files = block.strip().splitlines()
        chash, author, stamp, subject = (head.split('|', 3) + ['', '', ''])[:4]
        commits.append({'hash': chash, 'author': author, 'time': stamp[11:16], 'subject': subject,
                        'files': [f for f in files if f.strip() and not any(is_blocked_name(p) for p in f.split('/'))]})
    return commits


def git_show(repo: str, commit: str, root: Path, max_chars: int = 60_000) -> dict:
    if not COMMIT.match(commit or ''):
        raise AccessError('Give a commit hash of 7-40 hex characters.')
    text = _git(_repo(repo, root), ['show', '--stat', '--patch', '--no-ext-diff', '--no-color', commit,
                                    *EXCLUDE_SECRETS])
    return {'text': text[:max_chars], 'truncated': len(text) > max_chars}
