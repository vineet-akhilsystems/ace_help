"""Collect local work evidence for a date range without reading file contents."""
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from backend.services.activity_gatherer import get_scan_roots
from backend.services.safe_fs import is_excluded

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
             ".next", ".pytest_cache", ".idea", ".vscode", "coverage", ".cache"}
SKIP_FILES = {".env", ".env.local", ".env.production", "credentials.json", "secrets.json"}
EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".txt", ".yml", ".yaml",
              ".toml", ".ini", ".sql", ".ipynb", ".ps1", ".sh", ".bat", ".html", ".css",
              ".scss", ".java", ".cs", ".go", ".rb", ".php", ".xml", ".pdf", ".doc",
              ".docx", ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".png", ".jpg", ".jpeg",
              ".svg", ".mp4", ".webm", ".lock"}
MAX_EVENTS = 3000
TICKET = re.compile(r"\bASPL-?\d{5,8}\b", re.I)


def _roots():
    roots = []
    for path in get_scan_roots():
        path = Path(path).resolve()
        if path.exists() and not is_excluded(path) and not any(path == old or old in path.parents for old in roots):
            roots = [old for old in roots if path not in old.parents]
            roots.append(path)
    return roots


def _date(timestamp):
    return datetime.fromtimestamp(timestamp).date()


def _event(day, kind, title, project, evidence):
    # Work that already names an ACE ticket (e.g. in its commit message) needs no new one.
    found = TICKET.search(" ".join([title, *evidence]))
    ticket = re.sub(r"(?i)^aspl-?", "ASPL-", found[0]) if found else None
    return {"date": day.isoformat(), "kind": kind, "title": title[:240],
            "repo": project, "evidence": evidence[:8], "ticket": ticket}


def find_ticket_ideas(start, end, roots=None):
    """Show all observed changes without consulting ACE tickets."""
    roots = [Path(root).resolve() for root in roots] if roots is not None else _roots()
    events = []
    seen = set()
    repos = []
    scanned = 0
    for base in roots:
        if is_excluded(base):
            continue
        for root, dirs, files in os.walk(base, topdown=True, followlinks=False):
            # This assistant (and AGENT_EXCLUDE folders) is never the user's work.
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")
                       and not is_excluded(Path(root, d))]
            here = Path(root)
            project = here.relative_to(base).parts[0] if here != base else base.name
            git_dir = here / ".git"
            if git_dir.exists():
                repos.append(here)
                try:
                    created = _date(git_dir.stat().st_ctime)
                    if start <= created <= end:
                        events.append(_event(created, "repository", "Git repository created: " + here.name,
                                             project, [str(here)]))
                except OSError:
                    pass
            for name in dirs:
                folder = here / name
                try:
                    created = _date(folder.stat().st_ctime)
                    if start <= created <= end:
                        events.append(_event(created, "folder", "Folder created: " + name,
                                             project, [str(folder)]))
                except OSError:
                    pass
            for name in files:
                if name in SKIP_FILES or name.startswith("."):
                    continue
                path = here / name
                if path.suffix.lower() not in EXTENSIONS:
                    continue
                try:
                    stat = path.stat()
                    modified = _date(stat.st_mtime)
                    created = _date(stat.st_ctime)
                except OSError:
                    continue
                for day, kind in ((created, "file created"), (modified, "file changed")):
                    if start <= day <= end:
                        key = (str(path), day, kind)
                        if key not in seen:
                            seen.add(key)
                            events.append(_event(day, kind, kind.capitalize() + ": " + name,
                                                 project, [str(path)]))
            scanned += 1
            if scanned >= 100000:
                break
        if scanned >= 100000:
            break

    for repo in repos:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), "log", "--all",
                 "--since=" + start.isoformat() + " 00:00:00",
                 "--until=" + end.isoformat() + " 23:59:59",
                 "--date=short", "--pretty=format:%ad%x09%h%x09%s", "--name-only"],
                capture_output=True, text=True, timeout=15, check=False)
            for block in result.stdout.split("\n\n"):
                lines = [line for line in block.splitlines() if line.strip()]
                if not lines or "\t" not in lines[0]:
                    continue
                date_text, commit_hash, message = lines[0].split("\t", 2)
                day = datetime.strptime(date_text, "%Y-%m-%d").date()
                events.append(_event(day, "commit", message, repo.name,
                                     ["Commit " + commit_hash + " in " + repo.name, *lines[1:7]]))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            continue

    events.sort(key=lambda item: (item["date"], item["repo"], item["kind"], item["title"]), reverse=True)
    return {"ideas": events[:MAX_EVENTS], "total": len(events),
            "truncated": len(events) > MAX_EVENTS or scanned >= 100000,
            "note": "Review each activity item and choose what deserves a new ticket."}
