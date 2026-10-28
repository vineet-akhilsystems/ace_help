import os
import subprocess
from datetime import date, datetime
from pathlib import Path
from backend.services import agent_context as ac
from backend.services.activity_gatherer import scan_git_activity


def test_find_daily_note_formats(tmp_path):
    (tmp_path / '17-9-2026.txt').write_text('first day', encoding='utf-8')
    (tmp_path / '18-9-26.txt').write_text('second day', encoding='utf-8')
    (tmp_path / 'notes.txt').write_text('ignored', encoding='utf-8')
    assert ac.find_daily_note(date(2026, 9, 18), tmp_path) == 'second day'
    assert ac.find_daily_note(date(2026, 9, 17), tmp_path) == 'first day'
    assert ac.find_daily_note(date(2026, 9, 19), tmp_path) is None


def test_scan_project_files_skips_secrets_and_vendor(tmp_path):
    for rel in ('proj/app.py', 'proj/.env', 'proj/.env.local', 'proj/node_modules/x.js', 'proj/runtime/a.json',
                'proj/storage_state.json', 'proj/key.pem'):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('x', encoding='utf-8')
    found = ac.scan_project_files(date.today(), tmp_path)
    files = [f['path'] for f in found if f['kind'] == 'file']
    assert files == [str(tmp_path / 'proj' / 'app.py')]
    assert all(set(f) == {'path', 'kind', 'created', 'time'} for f in found)


def test_day_context_flags_filled_and_sunday(monkeypatch, tmp_path):
    monkeypatch.setattr(ac, 'read_json', lambda path, default: {'2026-10-26': {'rows': 3, 'minutes': 560}})
    monkeypatch.setattr(ac, 'leave_days', lambda: set())
    monkeypatch.setattr(ac, 'scan_root', lambda: tmp_path)
    monkeypatch.setattr(ac, 'load_user_tickets', lambda fallback: ([], None))
    filled = ac.day_context(date(2026, 10, 26), 'my notes', [])
    assert filled['alreadyFilled'] and filled['isWorkingDay'] and filled['userNotes'] == 'my notes'
    sunday = ac.day_context(date(2026, 10, 25), None, [])
    assert not sunday['isWorkingDay'] and not sunday['alreadyFilled']
    assert set(filled) == {'date', 'isWorkingDay', 'workplace', 'alreadyFilled', 'onLeave', 'userNotes', 'dailyNote',
                           'commits', 'files', 'candidateTickets', 'ticketWarning', 'rules'}
    assert filled['rules']['descriptionMaxChars'] == 480 and filled['rules']['descriptionMinChars'] == 40


def test_git_items_have_repo_path_and_time(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    env = {**os.environ, 'GIT_AUTHOR_NAME': 'Vineet', 'GIT_AUTHOR_EMAIL': 'v@x', 'GIT_COMMITTER_NAME': 'Vineet',
           'GIT_COMMITTER_EMAIL': 'v@x'}
    subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
    (repo / 'a.txt').write_text('a', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True, env=env)
    subprocess.run(['git', 'commit', '-q', '-m', 'feat: thing'], cwd=repo, check=True, env=env)
    commits = scan_git_activity(datetime.now().strftime('%Y-%m-%d'), [tmp_path])
    assert commits[0]['repoPath'] == str(repo) and commits[0]['message'] == 'feat: thing'
    assert len(commits[0]['time']) == 5 and commits[0]['time'][2] == ':'


def _git(repo, *args, author='vineet'):
    env = {**os.environ, 'GIT_AUTHOR_NAME': author, 'GIT_AUTHOR_EMAIL': 'a@x', 'GIT_COMMITTER_NAME': author,
           'GIT_COMMITTER_EMAIL': 'a@x'}
    subprocess.run(['git', *args], cwd=repo, check=True, env=env, capture_output=True)


def test_work_files_drop_pulled_files_and_group_by_project(tmp_path):
    repo = tmp_path / 'proj'
    repo.mkdir()
    _git(repo, 'init', '-q')
    for name, author in (('mine.py', 'vineet'), ('theirs.py', 'amit')):
        (repo / name).write_text(name, encoding='utf-8')
        _git(repo, 'add', name, author=author)
        _git(repo, 'commit', '-q', '-m', name, author=author)
    (repo / 'dirty.py').write_text('wip', encoding='utf-8')
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'report.md').write_text('r', encoding='utf-8')
    today = date.today()
    files = ac.scan_project_files(today, tmp_path)
    groups = ac.work_files(files, today, tmp_path)
    by_folder = {g['folder']: g for g in groups}
    kept = by_folder[str(repo)]['files']
    assert sorted(Path(p).name for p in kept) == ['dirty.py', 'mine.py']
    assert [Path(p).name for p in by_folder[str(tmp_path / 'docs')]['files']] == ['report.md']
    assert set(by_folder[str(repo)]) == {'folder', 'files', 'more', 'firstTime', 'lastTime'}


def test_day_context_keeps_only_own_commits(monkeypatch, tmp_path):
    monkeypatch.setattr(ac, 'read_json', lambda path, default: {})
    monkeypatch.setattr(ac, 'leave_days', lambda: set())
    monkeypatch.setattr(ac, 'scan_root', lambda: tmp_path)
    monkeypatch.setattr(ac, 'load_user_tickets', lambda fallback: ([], None))
    monkeypatch.setattr(ac, 'scan_git_activity', lambda day, roots: [
        {'repo': 'a', 'repoPath': str(tmp_path / 'a'), 'is_user': True, 'message': 'mine'},
        {'repo': 'a', 'repoPath': str(tmp_path / 'a'), 'is_user': False, 'message': 'theirs'}])
    context = ac.day_context(date(2026, 10, 26), None, [])
    assert [c['message'] for c in context['commits']] == ['mine']


def test_loose_files_group_by_project_folder(tmp_path):
    for rel in ('AI POC projects/video/a/b/x.md', 'AI POC projects/video/c/y.md', 'my task updates/27-10-2026.txt'):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text('x', encoding='utf-8')
    groups = ac.work_files(ac.scan_project_files(date.today(), tmp_path), date.today(), tmp_path)
    by_folder = {g['folder']: g for g in groups}
    assert len([f for f in by_folder[str(tmp_path / 'AI POC projects' / 'video')]['files'] if f.endswith('.md')]) == 2
    assert by_folder[str(tmp_path / 'my task updates')]['files'][-1].endswith('27-10-2026.txt')


def test_assistant_project_is_never_reported(monkeypatch, tmp_path):
    tool = tmp_path / 'AI POC projects' / 'ace_portal_automation'
    (tool / 'backend').mkdir(parents=True)
    (tool / 'backend' / 'main.py').write_text('x', encoding='utf-8')
    (tmp_path / 'proj').mkdir()
    (tmp_path / 'proj' / 'work.md').write_text('x', encoding='utf-8')
    monkeypatch.setattr(ac, 'excluded_folders', lambda: [tool])
    paths = [f['path'] for f in ac.scan_project_files(date.today(), tmp_path)]
    assert all('ace_portal_automation' not in p for p in paths) and any(p.endswith('work.md') for p in paths)
    monkeypatch.setattr(ac, 'read_json', lambda path, default: {})
    monkeypatch.setattr(ac, 'leave_days', lambda: set())
    monkeypatch.setattr(ac, 'scan_root', lambda: tmp_path)
    monkeypatch.setattr(ac, 'load_user_tickets', lambda fallback: ([], None))
    monkeypatch.setattr(ac, 'scan_git_activity', lambda day, roots: [
        {'repo': 'ace_portal_automation', 'repoPath': str(tool), 'is_user': True, 'message': 'tool work'},
        {'repo': 'proj', 'repoPath': str(tmp_path / 'proj'), 'is_user': True, 'message': 'real work'}])
    assert [c['message'] for c in ac.day_context(date.today(), None, [])['commits']] == ['real work']


def test_default_exclusion_is_this_assistant():
    from backend.config import ROOT
    assert ROOT.resolve() in ac.excluded_folders()


def test_skip_reason_before_spawning_agent(monkeypatch):
    monkeypatch.setattr(ac, 'read_json', lambda path, default: {'2026-10-26': {'rows': 2}})
    monkeypatch.setattr(ac, 'leave_days', lambda: {'2026-10-24'})
    assert ac.skip_reason(date(2026, 10, 26)) == '2026-10-26 already has entries in ACE; skipped.'
    assert ac.skip_reason(date(2026, 10, 24)) == '2026-10-24 is marked as leave; skipped.'
    assert ac.skip_reason(date(2026, 10, 23)) is None
