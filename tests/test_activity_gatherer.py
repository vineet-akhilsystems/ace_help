import pytest
from pathlib import Path
from backend.services.activity_gatherer import (
    gather_day_activity,
    format_activity_digest,
    scan_git_activity,
    scan_file_activity
)


def test_format_activity_digest_empty():
    assert format_activity_digest({}) == ''
    assert format_activity_digest({'has_activity': False}) == ''


def test_format_activity_digest_with_data():
    sample = {
        'date': '2026-09-16',
        'has_activity': True,
        'commits': [{
            'repo': 'patient_vist_summary',
            'hash': 'fc1aa27',
            'author': 'vineet',
            'message': 'feat: refactor super summary structure',
            'changed_files': ['schemas.py', 'super_summary.py'],
            'ticket': 'ASPL-169999',
            'is_user': True
        }],
        'new_folders': ['test_project'],
        'files': [{
            'name': 'Harsh Tyagi Report.docx',
            'ext': 'docx',
            'location': 'Downloads',
            'size_kb': 28.4
        }]
    }
    digest = format_activity_digest(sample)
    assert '2026-09-16' in digest
    assert 'fc1aa27' in digest
    assert 'patient_vist_summary' in digest
    assert 'test_project' in digest
    assert 'Harsh Tyagi Report.docx' in digest
    assert 'ASPL-169999' in digest


def test_scan_activity_runs_safely():
    # Verify scanning doesn't crash on invalid or non-existent directories
    commits = scan_git_activity('2099-01-01', [Path('/non/existent/path')])
    assert commits == []
    activity = gather_day_activity('2099-01-01')
    assert activity['date'] == '2099-01-01'
    assert isinstance(activity['commits'], list)
    assert isinstance(activity['new_folders'], list)
    assert isinstance(activity['files'], list)


def test_git_scan_never_reads_this_assistant(tmp_path):
    import os
    import subprocess
    from datetime import date
    from backend.services.activity_gatherer import scan_git_activity
    env = {**os.environ, 'GIT_AUTHOR_NAME': 'V', 'GIT_AUTHOR_EMAIL': 'v@x', 'GIT_COMMITTER_NAME': 'V',
           'GIT_COMMITTER_EMAIL': 'v@x'}
    for name in ('ace_portal_automation', 'billing'):
        repo = tmp_path / name
        repo.mkdir()
        subprocess.run(['git', 'init', str(repo)], check=True, capture_output=True)
        (repo / 'a.txt').write_text('x', encoding='utf-8')
        subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True, capture_output=True, env=env)
        subprocess.run(['git', '-C', str(repo), 'commit', '-m', 'work in ' + name], check=True, capture_output=True, env=env)
    messages = [c['message'] for c in scan_git_activity(date.today().isoformat(), [tmp_path])]
    assert 'work in billing' in messages and 'work in ace_portal_automation' not in messages
