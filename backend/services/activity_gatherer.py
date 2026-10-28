import os
import re
from datetime import datetime
from pathlib import Path
from backend.services.safe_fs import _git, is_excluded


def get_scan_roots() -> list[Path]:
    """Returns candidate root directories to scan for git repositories and files."""
    roots = []
    user_home = Path(os.path.expanduser('~'))
    desktop = user_home / 'Desktop'
    downloads = user_home / 'Downloads'
    akhil = desktop / 'akhil_system'

    for p in [akhil, desktop, downloads]:
        if p.exists() and p not in roots:
            roots.append(p)
    return roots


def _notify(callback, step: str, detail: str | None = None, icon: str | None = None):
    """Safely invokes progress callback if provided."""
    if not callback:
        return
    try:
        callback(step, detail, icon)
    except Exception:
        pass


def scan_git_activity(target_date: str, scan_roots: list[Path] | None = None, on_progress=None) -> list[dict]:
    """Scans git repositories for commits authored or committed on target_date."""
    if scan_roots is None:
        scan_roots = get_scan_roots()

    _notify(on_progress, "Scanning repositories in Desktop, akhil_system & workspace...", None, "git")

    git_repos = []
    skip_dirs = {'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build', '.next'}

    for root_dir in scan_roots:
        if not root_dir.exists() or is_excluded(root_dir):
            continue
        try:
            for root, dirs, _ in os.walk(root_dir, topdown=True, followlinks=False):
                if '.git' in dirs:
                    git_repos.append(Path(root))
                    dirs.remove('.git')
                # This assistant's own repo is never the user's work: don't even read its history.
                dirs[:] = [d for d in dirs if d not in skip_dirs and not is_excluded(Path(root, d))]
        except (OSError, PermissionError):
            pass

    unique_repos = sorted(list(set(git_repos)), key=lambda p: str(p))
    _notify(on_progress, f"Inspecting {len(unique_repos)} git repositories for {target_date} commits", None, "git")

    commits = []
    seen_hashes = set()
    repos_with_commits = set()

    for repo in unique_repos:
        try:
            args = [
                'log',
                f'--since={target_date} 00:00:00',
                f'--until={target_date} 23:59:59',
                '--pretty=format:%h|%an|%cI|%s',
                '--date=iso'
            ]
            out = _git(repo, args).strip()
            if not out:
                continue

            repo_commits = []
            for line in out.splitlines():
                parts = line.split('|', 3)
                if len(parts) == 4:
                    chash, author, stamp, msg = parts
                else:
                    chash, author, stamp, msg = parts[0], '', '', parts[-1]

                if chash in seen_hashes:
                    continue
                seen_hashes.add(chash)

                # Fetch changed files
                changed_files = []
                try:
                    show_out = _git(repo, ['show', '--stat', '--oneline', chash]).strip()
                    file_lines = [l.strip() for l in show_out.splitlines()[1:] if '|' in l]
                    changed_files = [l.split('|')[0].strip() for l in file_lines[:-1]] if len(file_lines) > 1 else [l.split('|')[0].strip() for l in file_lines]
                except Exception:
                    pass

                # Extract ticket ID if present in commit message or branch
                ticket_match = re.search(r'(ASPL-\d{5,8})', msg, re.I)

                item = {
                    'repo': repo.name,
                    'repoPath': str(repo),
                    'time': stamp[11:16],
                    'hash': chash,
                    'author': author,
                    'message': msg,
                    'changed_files': changed_files[:8],
                    'ticket': ticket_match.group(1).upper() if ticket_match else None,
                    'is_user': bool(re.search(r'vineet', author, re.I))
                }
                commits.append(item)
                repo_commits.append(item)

            if repo_commits:
                repos_with_commits.add(repo.name)
                first_msg = repo_commits[0]['message'][:65]
                _notify(on_progress, f"Found {len(repo_commits)} commit(s) in {repo.name}", f'"{first_msg}"', "commit")
                changed = []
                for rc in repo_commits:
                    changed.extend(rc['changed_files'])
                if changed:
                    _notify(on_progress, f"Reading code changes & diffs in {repo.name}", f"Modified: {', '.join(changed[:5])}", "code")

        except Exception:
            pass

    if commits:
        _notify(on_progress, f"Parsed {len(commits)} commit(s) across {len(repos_with_commits)} repository/repositories", f"Commits: {', '.join([c['hash'] for c in commits[:4]])}", "commit")
    else:
        _notify(on_progress, "No git commits found for this date", "Checked Desktop, akhil_system and workspace", "git")

    # Sort so user's own commits appear first
    commits.sort(key=lambda c: (not c['is_user'], c['repo'], c['hash']))
    return commits


def scan_file_activity(target_date: str, on_progress=None) -> dict:
    """Finds folders created and files modified/created on target_date."""
    user_home = Path(os.path.expanduser('~'))
    desktop = user_home / 'Desktop'
    downloads = user_home / 'Downloads'
    akhil = desktop / 'akhil_system'

    _notify(on_progress, "Scanning Desktop & Downloads for folders, documents & demo videos...", None, "folder")

    result = {'new_folders': [], 'files': []}
    skip_names = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build'}

    for base in [desktop, akhil, downloads]:
        if not base.exists():
            continue
        try:
            for item in base.glob('*'):
                if item.name in skip_names or item.name.startswith('.') or is_excluded(item):
                    continue
                try:
                    stat = item.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d')
                    ctime = datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d')
                    if mtime == target_date or ctime == target_date:
                        if item.is_dir():
                            result['new_folders'].append(item.name)
                        else:
                            ext = item.suffix.lower()
                            if ext in ('.pdf', '.docx', '.doc', '.xlsx', '.csv', '.mp4', '.mov', '.mp3', '.json', '.py', '.txt', '.ipynb'):
                                result['files'].append({
                                    'name': item.name,
                                    'ext': ext[1:],
                                    'location': base.name,
                                    'size_kb': round(stat.st_size / 1024, 1)
                                })
                except (OSError, PermissionError):
                    continue
        except (OSError, PermissionError):
            continue

    # Deduplicate
    result['new_folders'] = sorted(list(set(result['new_folders'])))
    seen_files = set()
    deduped_files = []
    for f in result['files']:
        if f['name'] not in seen_files:
            seen_files.add(f['name'])
            deduped_files.append(f)
    result['files'] = deduped_files

    if result['new_folders']:
        _notify(on_progress, f"Found {len(result['new_folders'])} newly created folder(s)/project(s)", f"Folders: {', '.join(result['new_folders'][:3])}", "folder")
    if result['files']:
        _notify(on_progress, f"Reading {len(result['files'])} touched document(s) & media files", f"Found: {', '.join([f['name'] for f in result['files'][:4]])}", "doc")
    elif not result['new_folders']:
        _notify(on_progress, "No documents, reports or media touched on this date", None, "doc")

    return result


def gather_day_activity(target_date: str, on_progress=None) -> dict:
    """Gathers all git commits, new folders, and file activity for target_date."""
    commits = scan_git_activity(target_date, on_progress=on_progress)
    file_info = scan_file_activity(target_date, on_progress=on_progress)
    return {
        'date': target_date,
        'commits': commits,
        'new_folders': file_info['new_folders'],
        'files': file_info['files'],
        'has_activity': bool(commits or file_info['new_folders'] or file_info['files'])
    }


def format_activity_digest(activity: dict) -> str:
    """Formats the gathered activity into a concise, factual context block for the planner."""
    if not activity or not activity.get('has_activity'):
        return ''

    lines = [f"=== DETECTED SYSTEM ACTIVITY FOR {activity['date']} ==="]

    if activity['commits']:
        lines.append("GIT COMMITS:")
        for c in activity['commits']:
            user_tag = " (By You)" if c['is_user'] else f" (Author: {c['author']})"
            files_str = f" [Modified: {', '.join(c['changed_files'])}]" if c['changed_files'] else ""
            ticket_str = f" [Ticket: {c['ticket']}]" if c['ticket'] else ""
            lines.append(f"- [{c['repo']}] {c['hash']}{user_tag}: {c['message']}{ticket_str}{files_str}")

    if activity['new_folders']:
        lines.append("\nNEW FOLDERS / PROJECTS CREATED:")
        for f in activity['new_folders']:
            lines.append(f"- Created folder: {f}")

    if activity['files']:
        lines.append("\nDOCUMENTS, MEDIA & ASSETS TOUCHED:")
        for f in activity['files']:
            ext_str = f" ({f.get('ext', '').upper()} file in {f.get('location', '')}, {f.get('size_kb', 0)} KB)" if f.get('ext') else ""
            lines.append(f"- {f['name']}{ext_str}")

    lines.append("====================================================")
    return '\n'.join(lines)
