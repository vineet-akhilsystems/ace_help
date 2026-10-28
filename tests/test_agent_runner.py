import asyncio
import socket
import sys
import threading
import time
from datetime import date
from pathlib import Path
import pytest
import uvicorn
from backend.services import agent_runner as ar
from backend.services.providers import ProviderError

FAKE = str(Path(__file__).with_name('fake_agent.py'))
DAY = date(2026, 10, 27)


def test_recipes_are_read_only(tmp_path):
    commands = {k: ' '.join(r.build('PROMPT', tmp_path, tmp_path / 'cfg.json')) for k, r in ar.RECIPES.items()}
    assert '--permission-mode dontAsk' in commands['claude'] and '--allowedTools mcp__ace-timesheet' in commands['claude']
    assert commands['antigravity'] == '-p PROMPT --output-format text'  # headless agy auto-denies unallowed tools
    assert '-s read-only' in commands['codex'] and '--disable shell_tool' in commands['codex']
    assert 'mcp_servers.ace-timesheet.default_tools_approval_mode="approve"' in commands['codex']
    assert '--approval-mode plan' in commands['gemini']
    assert not any(bad in c for c in commands.values() for bad in ('dangerously', 'yolo', 'bypass'))


def test_prompt_is_single_line_without_notes():
    prompt = ar.agent_prompt(DAY)
    assert '\n' not in prompt and '"' not in prompt and '2026-10-27' in prompt and 'get_day_context' in prompt


@pytest.fixture(scope='module')
def backend():
    from backend import main
    saved = main.agent_day_context, main.load_user_tickets, main.skip_reason
    main.skip_reason = lambda day: None
    main.agent_day_context = lambda day: {'isWorkingDay': True, 'alreadyFilled': False, 'onLeave': False}
    main.load_user_tickets = lambda fallback: ([], None)
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(main.app, host='127.0.0.1', port=port, log_level='warning'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    yield f'http://127.0.0.1:{port}'
    server.should_exit = True
    main.agent_day_context, main.load_user_tickets, main.skip_reason = saved


def fake(monkeypatch, tmp_path, mode):
    from backend.services import agent_drafts
    monkeypatch.setattr(agent_drafts, 'store', agent_drafts.DraftStore(tmp_path))
    monkeypatch.setitem(ar.RECIPES, 'fake', ar.Recipe('fake', 'Fake agent', sys.executable,
                                                      lambda prompt, root, cfg: [FAKE, mode, DAY.isoformat()]))


def run(backend, timeout=30):
    steps = []
    result = asyncio.run(ar.run_for_day('fake', DAY, 'my notes', lambda step, detail=None, icon=None: steps.append(step),
                                        base_url=backend, timeout=timeout))
    return result, steps


def test_run_returns_submitted_plan(monkeypatch, tmp_path, backend):
    fake(monkeypatch, tmp_path, 'submit')
    plan, steps = run(backend)
    assert plan.date == DAY and plan.tasks[0].evidence == 'Daily note item 1'
    assert 'Reading notes' in steps
    from backend.services import agent_drafts
    assert agent_drafts.current is None


def test_run_without_submit_reports_no_work(monkeypatch, tmp_path, backend):
    fake(monkeypatch, tmp_path, 'silent')
    assert run(backend)[0] is None


def test_never_reaching_tools_and_failures(monkeypatch, tmp_path, backend):
    fake(monkeypatch, tmp_path, 'none')
    with pytest.raises(ProviderError, match='did not reach the ACE tools'):
        run(backend)
    fake(monkeypatch, tmp_path, 'fail')
    with pytest.raises(ProviderError, match='stopped with an error'):
        run(backend)


def test_three_rejections_stop_the_run(monkeypatch, tmp_path, backend):
    fake(monkeypatch, tmp_path, 'reject')
    with pytest.raises(ProviderError, match="draft was rejected 3 times: Task 1: description"):
        run(backend)


def test_timeout_kills_agent(monkeypatch, tmp_path, backend):
    fake(monkeypatch, tmp_path, 'sleep')
    started = time.time()
    with pytest.raises(ProviderError, match='was stopped'):
        run(backend, timeout=2)
    assert time.time() - started < 15


def test_startup_watchdog(monkeypatch, tmp_path, backend):
    fake(monkeypatch, tmp_path, 'sleep')
    monkeypatch.setenv('AGENT_STARTUP_TIMEOUT_SECONDS', '1')
    with pytest.raises(ProviderError, match='did not load the day context within 1 seconds'):
        run(backend, timeout=10)


def test_idle_watchdog(monkeypatch, tmp_path, backend):
    fake(monkeypatch, tmp_path, 'idle')
    monkeypatch.setenv('AGENT_IDLE_TIMEOUT_SECONDS', '2')
    with pytest.raises(ProviderError, match='no new tool events'):
        run(backend, timeout=15)


def test_cli_progress_counts_tool_lifecycle_without_counting_waits():
    import json
    from backend.services.agent_drafts import ActiveRun

    async def check():
        from types import SimpleNamespace
        stdout, stderr = asyncio.StreamReader(), asyncio.StreamReader()
        run = ActiveRun(day=DAY, notes='')
        steps = []

        async def wait():
            return 0

        proc = SimpleNamespace(stdout=stdout, stderr=stderr, wait=wait)
        task = asyncio.create_task(ar._watch_cli(proc, run, lambda *args: steps.append(args[0]), 'Codex'))
        event = {'type': 'item.started', 'item': {'id': '1', 'type': 'mcp_tool_call',
                                               'tool': 'git_show', 'status': 'in_progress'}}
        stdout.feed_data(json.dumps(event).encode() + b'\n')
        await asyncio.sleep(0.01)
        assert run.cli_tool == 'git_show' and run.cli_progress_at > 0
        timestamp = run.cli_progress_at
        # Repeated lifecycle events and wait messages do not keep a loop alive.
        stdout.feed_data(json.dumps(event).encode() + b'\n')
        stdout.feed_data(b'{"type":"item.completed","item":{"type":"reasoning","text":"waiting"}}\n')
        await asyncio.sleep(0.01)
        assert run.cli_progress_at == timestamp
        event['type'] = 'item.completed'
        event['item']['status'] = 'completed'
        stdout.feed_data(json.dumps(event).encode() + b'\n')
        stdout.feed_eof()
        stderr.feed_eof()
        await task
        assert run.cli_tool_status == 'completed' and run.cli_progress_at >= timestamp
        assert steps == ['Codex: git_show in_progress', 'Codex: git_show completed']

    asyncio.run(check())


def test_repeated_tool_activity_stops_loop(monkeypatch, tmp_path, backend):
    fake(monkeypatch, tmp_path, 'loop')
    with pytest.raises(ProviderError, match='repeated the same tool activity'):
        run(backend, timeout=15)


@pytest.mark.parametrize('agent', ['claude', 'codex', 'antigravity'])
@pytest.mark.parametrize('mode, error', [('loop', 'repeated the same tool activity'),
                                       ('invalid-shape', 'draft was rejected 3 times')])
def test_shared_loop_guards_cover_every_agent(monkeypatch, tmp_path, backend, agent, mode, error):
    fake(monkeypatch, tmp_path, mode)
    recipe = ar.RECIPES[agent]
    # Exercise each agent route with a deterministic CLI substitute, without live provider calls.
    monkeypatch.setitem(ar.RECIPES, agent, ar.Recipe(agent, recipe.label, sys.executable,
                                                  ar.RECIPES['fake'].build))
    monkeypatch.setattr(ar, 'write_agy_hooks', lambda: None)
    monkeypatch.setattr(ar, 'antigravity_read_only', lambda: True)
    with pytest.raises(ProviderError, match=error):
        asyncio.run(ar.run_for_day(agent, DAY, '', lambda *args: None, base_url=backend, timeout=30))


def test_accepted_draft_does_not_wait_for_cli_exit(monkeypatch, tmp_path, backend):
    fake(monkeypatch, tmp_path, 'linger')
    started = time.monotonic()
    assert run(backend)[0].date == DAY
    assert time.monotonic() - started < 10


def test_closing_stream_cancels_agent_worker(monkeypatch):
    from types import SimpleNamespace
    from backend import main
    stopped = []

    async def draft(agent, day, notes, on_progress, **kwargs):
        on_progress('Started', None, 'ai')
        try:
            await asyncio.Event().wait()
        finally:
            stopped.append(True)

    monkeypatch.setattr(ar, 'available_agents', lambda: [{'id': 'fake', 'installed': True, 'verified': True}])
    monkeypatch.setattr(ar, 'run_for_day', draft)
    monkeypatch.setattr(main, 'skip_reason', lambda day: None)
    monkeypatch.setattr(main, 'planning_lock', asyncio.Lock())

    async def close():
        response = await main.agent_draft_stream(main.AgentDraftRequest(fromDate=DAY, agent='fake'),
                                                SimpleNamespace(url=SimpleNamespace(port=9999)))
        await asyncio.wait_for(anext(response.body_iterator), 2)
        await asyncio.wait_for(response.body_iterator.aclose(), 2)

    asyncio.run(close())
    assert stopped == [True]


def stream(backend, body):
    import httpx, json
    events = []
    with httpx.stream('POST', f'{backend}/agent/draft-stream', json=body, headers={'X-ACE-Client': '1'},
                      timeout=60) as response:
        if response.status_code != 200:
            response.read()
            return response.status_code, response.json()
        for line in response.iter_lines():
            if line.startswith('data: '):
                events.append(json.loads(line[6:]))
    return 200, events


def test_draft_stream_rejects_unverified_agent(backend):
    status, body = stream(backend, {'fromDate': '2026-10-27', 'toDate': None, 'agent': 'gemini', 'notes': ''})
    assert status == 422 and body['detail'] == 'Choose an available agent.'


def test_draft_stream_returns_plans_and_no_work(monkeypatch, tmp_path, backend):
    fake(monkeypatch, tmp_path, 'submit')
    monkeypatch.setattr(ar, 'VERIFIED', {'fake'})
    status, events = stream(backend, {'fromDate': '2026-10-27', 'toDate': None, 'agent': 'fake', 'notes': 'x'})
    result = events[-1]
    assert status == 200 and result['type'] == 'result' and result['plans'][0]['date'] == '2026-10-27'
    assert result['noWork'] == [] and any(e['type'] == 'step' for e in events)
    fake(monkeypatch, tmp_path, 'silent')
    status, events = stream(backend, {'fromDate': '2026-10-27', 'toDate': None, 'agent': 'fake', 'notes': ''})
    assert events[-1]['plans'] == [] and events[-1]['noWork'] == ['2026-10-27']
    assert any('No work found for 2026-10-27; dictate the day instead.' == e.get('step') for e in events)


def test_agents_list_has_default_first(backend):
    import httpx
    agents = httpx.get(f'{backend}/agent/agents', headers={'X-ACE-Client': '1'}).json()
    assert agents[0]['id'] == 'antigravity' and {a['id'] for a in agents} >= {'claude', 'codex', 'gemini'}


def test_only_agents_that_passed_real_checks_are_selectable():
    # Verified 2026-10-27: reaches the ace-timesheet tools unattended and cannot write files.
    # Gemini CLI fails before running (IneligibleTierError: individual Code Assist tier no longer supported).
    assert ar.VERIFIED == {'antigravity', 'claude', 'codex'}


def test_claude_has_no_builtin_tools(tmp_path):
    args = ar.RECIPES['claude'].build('PROMPT', tmp_path, tmp_path / 'cfg.json')
    assert args[args.index('--tools') + 1] == ''


def test_antigravity_refuses_extra_allow_rules(tmp_path):
    settings = tmp_path / 'settings.json'
    settings.write_text('{"permissions": {"allow": ["mcp(ace-timesheet/get_day_context)"]}}', encoding='utf-8')
    assert ar.antigravity_read_only(settings)
    settings.write_text('{"permissions": {"allow": ["mcp(ace-timesheet/read_file)", "write_file(C:/x)"]}}',
                        encoding='utf-8')
    assert not ar.antigravity_read_only(settings)
    assert not ar.antigravity_read_only(tmp_path / 'missing.json')


def test_antigravity_runs_from_hooked_workspace(tmp_path):
    import json
    assert ar.RECIPES['antigravity'].cwd == ar.AGY_WORKSPACE
    hooks = ar.write_agy_hooks(tmp_path)
    command = json.loads(hooks.read_text(encoding='utf-8'))['ace-only']['PreToolUse'][0]['hooks'][0]['command']
    assert command.endswith(' ace_only_hook.py') and '"' not in command and ' ' not in command.split(' ace_only')[0]
    assert (ar.AGY_WORKSPACE / '.agents' / 'ace_only_hook.py').exists()
