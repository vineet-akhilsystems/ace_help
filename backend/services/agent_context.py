"""Everything a coding agent needs to draft one day's timesheet."""
import os
import re
from datetime import date, datetime
from pathlib import Path
from backend.app_rules import is_working_day, workplace
from backend.app_status import CACHE, leave_days, read_json
from backend.config import setting
from backend.services.activity_gatherer import scan_git_activity
from backend.services.safe_fs import AccessError, _git, excluded_folders, git_log, is_blocked_name, scan_root
from backend.services.user_tickets import load_user_tickets, rank_for_day

NOTE_NAME = re.compile(r'^(\d{1,2})[-_.](\d{1,2})[-_.](\d{2}|\d{4})$')
VOICE = ('Write each description the way the developer would write their own daily update to a manager: '
         'first person ("I"), plain natural English, past tense, full sentences, no bullet points, no marketing words. '
         'Cover, where the evidence supports it: what the task or ask was, what I actually did, where it stands now '
         '(done, in testing, still in progress), and any blocker or dependency, naming people exactly as the notes do. '
         'If little was done, say that honestly with the reason given. Aim for 350-480 characters when the evidence '
         'has enough detail; never pad with generic filler. Never invent work, outcomes, people or blockers.')
FORBIDDEN = ("file names, extensions, folder or repository names, paths, commit hashes, branch names, "
             "phrases like 'modified X file' or 'committed changes', and ticket numbers inside the text")


def find_daily_note(day: date, folder: Path) -> str | None:
    try:
        candidates = sorted(folder.iterdir())
    except OSError:
        return None
    for path in candidates:
        match = NOTE_NAME.match(path.stem)
        if not match or path.suffix.lower() not in ('.txt', '.md'):
            continue
        d, m, y = (int(g) for g in match.groups())
        try:
            if date(y + 2000 if y < 100 else y, m, d) == day:
                return path.read_text(encoding='utf-8', errors='replace')[:20000]
        except (ValueError, OSError):
            continue
    return None


def scan_project_files(day: date, root: Path, limit: int = 300) -> list[dict]:
    found = []
    skip = excluded_folders()
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith('.') and not is_blocked_name(d)
                   and Path(current, d).resolve() not in skip]
        base = Path(current)
        for name, kind in [(d, 'folder') for d in dirs] + [(f, 'file') for f in files]:
            if name.startswith('.') or is_blocked_name(name):
                continue
            try:
                stat = (base / name).stat()
            except OSError:
                continue
            modified, created = datetime.fromtimestamp(stat.st_mtime), datetime.fromtimestamp(stat.st_ctime)
            if day in (modified.date(), created.date()):
                stamp = modified if modified.date() == day else created
                found.append({'path': str(base / name), 'kind': kind, 'created': created.date() == day,
                              'time': stamp.strftime('%H:%M')})
    return sorted(found, key=lambda f: f['time'])[:limit]


def _excluded(path: Path) -> bool:
    path = path.resolve()
    return any(path == folder or folder in path.parents for folder in excluded_folders())


def is_me(author: str) -> bool:
    return bool(re.search(re.escape(setting('ACE_GIT_AUTHOR', 'vineet')), author or '', re.I))


def _repo_of(path: Path, root: Path, cache: dict) -> Path | None:
    for parent in path.parents:
        if parent == root.parent or root not in (parent, *parent.parents):
            return None
        if parent not in cache:
            cache[parent] = (parent / '.git').exists()
        if cache[parent]:
            return parent
    return None


def _my_repo_files(repo: Path, day: date, root: Path) -> set[Path]:
    """Files I committed that day plus files with uncommitted changes; pulled colleague changes are excluded."""
    mine = set()
    try:
        for commit in git_log(str(repo), day, root):
            if is_me(commit['author']):
                mine.update((repo / f).resolve() for f in commit['files'])
    except AccessError:
        pass
    try:
        status = _git(repo, ['status', '--porcelain', '--untracked-files=all'])
    except AccessError:
        status = ''
    for line in status.splitlines():
        mine.add((repo / line[3:].split(' -> ')[-1].strip('"')).resolve())
    return mine


def work_files(files: list[dict], day: date, root: Path, per_group: int = 15) -> list[dict]:
    """Groups the day's changed files by repository or folder, keeping only the user's own work."""
    repo_cache, mine_cache, groups = {}, {}, {}
    for entry in files:
        path = Path(entry['path'])
        repo = _repo_of(path, root, repo_cache)
        if repo:
            if repo not in mine_cache:
                mine_cache[repo] = _my_repo_files(repo, day, root)
            if path.resolve() not in mine_cache[repo]:
                continue
        elif entry['kind'] == 'folder' and not entry['created']:
            continue
        if not repo:
            parts = path.relative_to(root).parts
            repo = root.joinpath(*parts[:min(2, len(parts) - 1)]) if len(parts) > 1 else root
        groups.setdefault(str(repo), []).append(entry)
    result = []
    for folder, entries in groups.items():
        result.append({'folder': folder, 'files': [e['path'] for e in entries[:per_group]],
                       'more': max(len(entries) - per_group, 0),
                       'firstTime': entries[0]['time'], 'lastTime': entries[-1]['time']})
    return sorted(result, key=lambda g: g['firstTime'])[:40]


def day_context(day: date, user_notes: str | None, fallback_tickets) -> dict:
    root = scan_root()
    entry = read_json(CACHE, {}).get(day.isoformat()) or {}
    tickets, ticket_warning = load_user_tickets(fallback_tickets)
    return {
        'date': day.isoformat(),
        'isWorkingDay': is_working_day(day),
        'workplace': workplace(day),
        'alreadyFilled': entry.get('rows', 0) > 0,
        'onLeave': day.isoformat() in leave_days(),
        'userNotes': user_notes or None,
        'dailyNote': find_daily_note(day, root / 'my task updates'),
        'commits': [c for c in scan_git_activity(day.isoformat(), [root])
                    if c['is_user'] and not _excluded(Path(c['repoPath']))],
        'files': work_files(scan_project_files(day, root, limit=2000), day, root),
        'candidateTickets': [t.model_dump(mode='json') for t in rank_for_day(tickets, day)],
        'ticketWarning': ticket_warning,
        'rules': {'descriptionMaxChars': 480, 'descriptionMinChars': 40, 'voice': VOICE, 'forbidden': FORBIDDEN},
    }


def skip_reason(day: date) -> str | None:
    """Cheap check before starting an agent, so filled or leave days never cost a run."""
    if (read_json(CACHE, {}).get(day.isoformat()) or {}).get('rows', 0) > 0:
        return f'{day.isoformat()} already has entries in ACE; skipped.'
    if day.isoformat() in leave_days():
        return f'{day.isoformat()} is marked as leave; skipped.'
    return None
