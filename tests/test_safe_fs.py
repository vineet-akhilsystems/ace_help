import os
import subprocess
import sys
import time
from datetime import date
import pytest
from backend.services import safe_fs as fs


@pytest.fixture
def root(tmp_path):
    r = tmp_path / 'root'
    (r / 'proj' / 'runtime').mkdir(parents=True)
    (r / 'proj' / 'app.py').write_text('print("hi")\n' * 10, encoding='utf-8')
    (r / 'proj' / '.env').write_text('SECRET=1', encoding='utf-8')
    (r / 'proj' / 'runtime' / 'state.json').write_text('{}', encoding='utf-8')
    (tmp_path / 'secret.txt').write_text('outside', encoding='utf-8')
    return r.resolve()


def test_rejects_escape_via_dotdot_and_symlink(root):
    with pytest.raises(fs.AccessError):
        fs.read_file(str(root / '..' / 'secret.txt'), root)
    link = root / 'proj' / 'link.txt'
    try:
        os.symlink(root.parent / 'secret.txt', link)
    except OSError:
        pytest.skip('symlinks need developer mode on Windows')
    with pytest.raises(fs.AccessError):
        fs.read_file(str(link), root)


def test_refuses_env_and_runtime(root):
    for blocked in (root / 'proj' / '.env', root / 'proj' / 'runtime' / 'state.json'):
        with pytest.raises(fs.AccessError):
            fs.read_file(str(blocked), root)
    names = [e['name'] for e in fs.list_dir(str(root / 'proj'), root)]
    assert names == ['app.py']


def test_read_file_truncates_and_refuses_binary(root):
    result = fs.read_file(str(root / 'proj' / 'app.py'), root, max_chars=20)
    assert result['text'] == 'print("hi")\nprint("h' and result['truncated']
    (root / 'proj' / 'img.png').write_bytes(b'\x89PNG\x00\x00data')
    with pytest.raises(fs.AccessError, match='Binary file'):
        fs.read_file(str(root / 'proj' / 'img.png'), root)


def test_git_show_rejects_non_hash(root):
    with pytest.raises(fs.AccessError):
        fs.git_show(str(root / 'proj'), 'HEAD; rm -rf /', root)


def test_git_log_and_show_on_tmp_repo(root):
    repo = root / 'proj'
    env = {**os.environ, 'GIT_AUTHOR_NAME': 'V', 'GIT_AUTHOR_EMAIL': 'v@x', 'GIT_COMMITTER_NAME': 'V',
           'GIT_COMMITTER_EMAIL': 'v@x'}
    subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
    subprocess.run(['git', 'add', 'app.py', '.env'], cwd=repo, check=True, env=env)
    subprocess.run(['git', 'commit', '-q', '-m', 'feat: greet'], cwd=repo, check=True, env=env)
    log = fs.git_log(str(repo), date.today(), root)
    assert log[0]['subject'] == 'feat: greet' and 'app.py' in log[0]['files']
    shown = fs.git_show(str(repo), log[0]['hash'], root)
    assert 'print("hi")' in shown['text'] and 'SECRET=1' not in shown['text']
    with pytest.raises(fs.AccessError):
        fs.git_log(str(root.parent), date.today(), root)


def test_refuses_dot_folders_and_credential_files(root):
    for rel in ('.claude/settings.local.json', '.npmrc', '.git-credentials', 'prod.env', 'Prod.ENV', 'id_rsa',
                'cert.p12', 'store.jks', 'aws_credentials.txt', 'Storage_State.json', 'k.KEY'):
        target = root / 'proj' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('secret', encoding='utf-8')
        with pytest.raises(fs.AccessError):
            fs.read_file(str(target), root)


def test_git_show_hides_secrets_case_insensitively(root):
    repo = root / 'proj'
    env = {**os.environ, 'GIT_AUTHOR_NAME': 'V', 'GIT_AUTHOR_EMAIL': 'v@x', 'GIT_COMMITTER_NAME': 'V',
           'GIT_COMMITTER_EMAIL': 'v@x'}
    for name in ('Prod.env', 'Storage_State.json', 'k.KEY', '.git-credentials', 'app.py'):
        (repo / name).write_text(f'SECRET-{name}' if name != 'app.py' else 'print(1)', encoding='utf-8')
    subprocess.run(['git', 'init', '-q'], cwd=repo, check=True)
    subprocess.run(['git', 'add', '-A'], cwd=repo, check=True, env=env)
    subprocess.run(['git', 'commit', '-q', '-m', 'all'], cwd=repo, check=True, env=env)
    commit = fs.git_log(str(repo), date.today(), root)[0]
    assert 'Prod.env' not in commit['files'] and '.git-credentials' not in commit['files']
    text = fs.git_show(str(repo), commit['hash'], root)['text']
    assert 'print(1)' in text and 'SECRET-' not in text


def test_excluded_folder_cannot_be_opened(root, monkeypatch):
    monkeypatch.setattr(fs, 'excluded_folders', lambda: [root / 'proj'])
    with pytest.raises(fs.AccessError, match='excluded'):
        fs.read_file(str(root / 'proj' / 'app.py'), root)


def test_git_timeout_cannot_hang_on_inherited_output_pipes(monkeypatch, tmp_path):
    real_popen = subprocess.Popen
    processes = []

    def hung_git(*args, **kwargs):
        assert kwargs['stdin'] == subprocess.DEVNULL
        assert kwargs['stdout'] != subprocess.PIPE and kwargs['stderr'] != subprocess.PIPE
        script = ('import subprocess,sys,time; '
                  'subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]); '
                  'time.sleep(60)')
        proc = real_popen([sys.executable, '-c', script], **kwargs)
        processes.append(proc)
        return proc

    monkeypatch.setattr(fs.subprocess, 'Popen', hung_git)
    monkeypatch.setattr(fs, 'GIT_READ_TIMEOUT_SECONDS', 0.3)
    started = time.monotonic()
    # taskkill uses subprocess.run too, so retain the real Popen for that helper.
    real_run = subprocess.run

    def run_helper(*args, **kwargs):
        with monkeypatch.context() as patch:
            patch.setattr(fs.subprocess, 'Popen', real_popen)
            return real_run(*args, **kwargs)

    monkeypatch.setattr(fs.subprocess, 'run', run_helper)
    with pytest.raises(fs.AccessError, match='do not repeat this read'):
        fs._git(tmp_path, ['show', 'abc1234'])
    assert time.monotonic() - started < 5
    assert processes[0].wait(timeout=2) is not None


def test_this_assistant_is_invisible_to_agents(root):
    tool = root / 'ace_portal_automation'
    (tool / 'backend').mkdir(parents=True)
    (tool / 'backend' / 'main.py').write_text('x', encoding='utf-8')
    assert 'ace_portal_automation' not in [e['name'] for e in fs.list_dir(str(root), root)]
    for call in (lambda: fs.list_dir(str(tool), root), lambda: fs.read_file(str(tool / 'backend' / 'main.py'), root),
                 lambda: fs.git_log(str(tool), date.today(), root)):
        with pytest.raises(fs.AccessError):
            call()
