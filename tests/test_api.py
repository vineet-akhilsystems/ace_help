from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from backend.main import app
from tests.test_rules import plan

HEADERS = {'X-ACE-Client':'1'}


def test_no_save_or_ticket_update_capability():
    paths = app.openapi()['paths']
    assert '/save' not in paths and '/ticket/update' not in paths


def test_local_only_requests():
    with TestClient(app) as client:
        assert client.post('/validate', json=[]).status_code == 403
        assert client.post('/validate', json=[], headers={**HEADERS,'Origin':'https://attacker.test'}).status_code == 403
        assert client.post('/validate', json=[], headers={**HEADERS,'Origin':'http://127.0.0.1:8766'}).status_code == 422
        assert client.post('/validate', json=[], headers={**HEADERS,'Origin':'http://localhost:5175'}).status_code == 422
        assert client.get('/health', headers={'Host':'attacker.test'}).status_code == 400
        assert client.get('/health').json()['saveEnabled'] is False


def test_dynamic_port_selection():
    import socket
    from backend.run import find_available_port, is_port_available
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        busy_port = s.getsockname()[1]
        assert not is_port_available('127.0.0.1', busy_port)
        next_port = find_available_port('127.0.0.1', busy_port)
        assert next_port != busy_port
        assert next_port > busy_port


def test_all_plans_validated_before_browser(monkeypatch):
    from backend.main import portal
    fill = AsyncMock()
    monkeypatch.setattr(portal, 'fill', fill)
    invalid = plan().model_dump(mode='json')
    invalid['tasks'][0]['end'] = '20:00'
    with TestClient(app) as client:
        assert client.post('/fill', json=[plan().model_dump(mode='json'),invalid], headers=HEADERS).status_code == 422
        assert client.post('/fill', json=[], headers=HEADERS).status_code == 422
        assert client.post('/fill', json=[plan().model_dump(mode='json')]*2, headers=HEADERS).status_code == 422
    fill.assert_not_awaited()


def test_audio_validation():
    with TestClient(app) as client:
        response = client.post('/transcribe', files={'audio':('recording.txt',b'test','text/plain')}, headers=HEADERS)
        assert response.status_code == 415


def test_status_endpoints(monkeypatch, tmp_path):
    import backend.app_status as status
    monkeypatch.setattr(status, 'CACHE', tmp_path / 'cache.json')
    monkeypatch.setattr(status, 'LEAVE', tmp_path / 'leave.json')
    monkeypatch.setattr(status, 'read_audit', lambda: {})
    with TestClient(app) as client:
        assert client.get('/status?month=2026-09').status_code == 403
        assert client.get('/status?month=2026-9', headers=HEADERS).status_code == 422
        assert client.get('/status?month=2999-01', headers=HEADERS).status_code == 422
        body = client.get('/status?month=2026-09', headers=HEADERS).json()
        assert len(body['days']) == 30 and body['counts']['unchecked'] == body['workingDays']
        marked = client.post('/status/leave', json={'day': '2026-09-01', 'leave': True}, headers=HEADERS).json()
        assert marked['days'][0]['status'] == 'leave' and marked['counts']['leave'] == 1
        assert client.post('/status/leave', json={'day': '2026-09-06', 'leave': True}, headers=HEADERS).status_code == 422
