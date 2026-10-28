import httpx
from backend import mcp_server as ms


def test_tools_report_backend_down(monkeypatch, tmp_path):
    monkeypatch.setattr(ms, 'PORT_FILE', tmp_path / 'port.json')
    assert ms.get_day_context('2026-10-26') == {'error': 'ACE assistant is not running. Start it with start.ps1.'}
    assert ms.submit_draft('2026-10-26', [])['error'].startswith('ACE assistant is not running')


def test_submit_returns_errors_not_exception(monkeypatch):
    def fake(method, path, **kwargs):
        return httpx.Response(422, json={'detail': ['Task 1: too short']}, request=httpx.Request(method, 'http://x' + path))
    monkeypatch.setattr(ms, '_request', fake)
    monkeypatch.setattr(ms, '_event', lambda message: None)
    assert ms.submit_draft('2026-10-26', [{'description': 'x', 'evidence': 'y'}]) == {
        'ok': False, 'errors': ['Task 1: too short']}


def test_read_file_refuses_outside_root(monkeypatch, tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    (tmp_path / 'secret.txt').write_text('outside', encoding='utf-8')
    monkeypatch.setattr(ms, 'scan_root', lambda: root.resolve())
    monkeypatch.setattr(ms, '_event', lambda message: None)
    result = ms.read_file(str(tmp_path / 'secret.txt'))
    assert 'outside the allowed folder' in result['error']


def test_prompt_contains_date():
    text = ms.fill_ace_day('2026-10-26')
    assert '2026-10-26' in text and 'submit_draft' in text and not text.startswith('---')


def test_identical_reads_do_not_repeat_io(monkeypatch):
    calls = []
    monkeypatch.setattr(ms, '_event', lambda message: None)
    monkeypatch.setattr(ms, '_reads', 0)
    monkeypatch.setattr(ms, '_read_results', {})

    def read(path):
        calls.append(path)
        return {'text': path}

    assert ms._read('Reading a', read, 'a') == {'text': 'a'}
    assert ms._read('Reading a', read, 'a') == {'text': 'a'}
    assert ms._read('Reading b', read, 'b') == {'text': 'b'}
    assert calls == ['a', 'b']
    assert ms._reads == 3  # Repetitions still consume the finite budget.


def test_ticket_cache_keeps_different_tickets_separate(monkeypatch):
    monkeypatch.setattr(ms, '_event', lambda message: None)
    monkeypatch.setattr(ms, '_reads', 0)
    monkeypatch.setattr(ms, '_read_results', {})
    calls = []

    def request(method, path, **kwargs):
        calls.append(path)
        return httpx.Response(200, json={'ticket': path.rsplit('/', 1)[-1]})

    monkeypatch.setattr(ms, '_request', request)
    assert ms.get_ticket('ASPL-172905')['ticket'] == 'ASPL-172905'
    assert ms.get_ticket('ASPL-172906')['ticket'] == 'ASPL-172906'
    ms.get_ticket('ASPL-172905')
    assert len(calls) == 2


def test_context_carries_skill_instructions(monkeypatch):
    def fake(method, path, **kwargs):
        return httpx.Response(200, json={'date': '2026-10-26'}, request=httpx.Request(method, 'http://x' + path))
    monkeypatch.setattr(ms, '_request', fake)
    monkeypatch.setattr(ms, '_event', lambda message: None)
    context = ms.get_day_context('2026-10-26')
    assert context['date'] == '2026-10-26' and 'submit_draft' in context['instructions']
    assert not context['instructions'].startswith('---')


def test_read_budget_forces_writing(monkeypatch, tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    (root / 'a.md').write_text('hello', encoding='utf-8')
    monkeypatch.setattr(ms, 'scan_root', lambda: root.resolve())
    monkeypatch.setattr(ms, '_event', lambda message: None)
    monkeypatch.setattr(ms, 'READ_BUDGET', 3)
    monkeypatch.setattr(ms, '_reads', 0)
    for _ in range(3):
        assert ms.read_file(str(root / 'a.md'))['text'] == 'hello'
    assert 'submit_draft now' in ms.list_dir(str(root))['error']
    def fake(method, path, **kwargs):
        return httpx.Response(200, json={'date': '2026-10-26'}, request=httpx.Request(method, 'http://x' + path))
    monkeypatch.setattr(ms, '_request', fake)
    ms.get_day_context('2026-10-26')
    assert 'submit_draft now' in ms.read_file(str(root / 'a.md'))['error']
