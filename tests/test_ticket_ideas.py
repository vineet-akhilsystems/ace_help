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


def test_items_that_name_a_ticket_are_marked():
    from backend.services.ticket_ideas import _event
    assert _event(date(2026, 10, 28), "commit", "Fix vitals for aspl172905", "emr", ["Commit abc"])["ticket"] == "ASPL-172905"
    assert _event(date(2026, 10, 28), "file changed", "File changed: notes.md", "emr", ["C:/x/notes.md"])["ticket"] is None


def test_this_assistant_is_never_a_ticket_idea(tmp_path):
    tool = tmp_path / "ace_portal_automation"
    (tool / "backend").mkdir(parents=True)
    (tool / "backend" / "main.py").write_text("x", encoding="utf-8")
    (tmp_path / "billing").mkdir()
    (tmp_path / "billing" / "invoice.py").write_text("x", encoding="utf-8")
    result = find_ticket_ideas(date.today(), date.today(), roots=[tmp_path])
    text = " ".join(item["title"] + " " + " ".join(item["evidence"]) for item in result["ideas"])
    assert "invoice.py" in text and "ace_portal_automation" not in text
    assert find_ticket_ideas(date.today(), date.today(), roots=[tool])["ideas"] == []
