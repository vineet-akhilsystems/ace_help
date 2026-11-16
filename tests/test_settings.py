from dotenv import dotenv_values
from fastapi.testclient import TestClient
from backend import main
from backend.app_settings import Credentials, save_credentials


def test_credentials_round_trip_preserves_literal_password(tmp_path):
    path = tmp_path / '.env'
    path.write_text('OTHER=value\n')
    password = " spaces ' \\n \\ ${OTHER} # "
    save_credentials(Credentials(username=' person ', password=password), path)
    values = dotenv_values(path, interpolate=False)
    assert values == {'OTHER': 'value', 'ACE_USERNAME': 'person', 'ACE_PASSWORD': password}
    assert not list(tmp_path.glob('.ace-login-*'))


def test_settings_never_return_password_and_require_local_header(monkeypatch):
    monkeypatch.setattr(main, 'login_restart_required', False)
    monkeypatch.setattr(main, 'login_status', lambda: {'username': 'person', 'configured': True})
    with TestClient(main.app) as client:
        assert client.get('/settings/credentials').status_code == 403
        result = client.get('/settings/credentials', headers={'X-ACE-Client': '1'})
        assert result.json() == {'username': 'person', 'configured': True, 'restartRequired': False}


def test_save_requires_restart_without_echoing_secret(monkeypatch, tmp_path):
    monkeypatch.setattr(main, 'login_restart_required', False)
    monkeypatch.setattr(main.session, 'state_file', tmp_path / 'state.json')
    saved = []
    monkeypatch.setattr(main, 'save_credentials', lambda credentials: saved.append(credentials))
    headers = {'X-ACE-Client': '1'}
    with TestClient(main.app) as client:
        invalid = client.post('/settings/credentials', headers=headers,
                              json={'username': 'person', 'password': 'private\nvalue'})
        assert invalid.status_code == 422
        assert 'private' not in invalid.text
        result = client.post('/settings/credentials', headers=headers,
                             json={'username': 'person', 'password': 'private-value'})
        assert result.json() == {'saved': True, 'restartRequired': True}
        assert len(saved) == 1
        assert client.get('/tickets', headers=headers).status_code == 409
