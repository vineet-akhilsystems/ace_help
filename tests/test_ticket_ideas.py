import os
import subprocess
from datetime import date

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.ticket_ideas import find_ticket_ideas


def test_scan_finds_small_file_changes_and_commits(tmp_path):
    repo = tmp_path / "billing_project"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    code = repo / "billing.py"
    code.write_text("def price(): return 1\n", encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
           "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com"}
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "Set up billing"],
                   check=True, capture_output=True, env=env)
    result = find_ticket_ideas(date.today(), date.today(), roots=[tmp_path])
    kinds = {item["kind"] for item in result["ideas"]}
    assert "commit" in kinds
    assert "file changed" in kinds
    assert any("Set up billing" in item["title"] for item in result["ideas"])


def test_ticket_ideas_date_range_validation():
    with TestClient(app) as client:
        headers = {"X-ACE-Client": "1"}
        assert client.post("/ticket-ideas", json={"fromDate": "2026-09-01", "toDate": "2026-08-01"}, headers=headers).status_code == 422
        assert client.post("/ticket-ideas", json={"fromDate": "2026-01-01", "toDate": "2026-03-01"}, headers=headers).status_code == 422
