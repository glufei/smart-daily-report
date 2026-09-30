"""A read action must preserve history and distinguish missing data from failures."""
from dataclasses import replace
from datetime import date, datetime, timezone
import sqlite3
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from smart_daily_report.shared.models import DailyReport, MemberReport
from smart_daily_report.shared.storage import get_report, write_report
from smart_daily_report.web import app as web_app
from smart_daily_report.web.app import create_app
from smart_daily_report.web.main import main


@pytest.fixture
def history(tmp_path, records, statuses):
    # Internal duplicate member status deliberately disagrees: templates use the top-level status.
    member = MemberReport("u1", "示例甲", [records["commit"]], [records["task"]], [records["message"]],
                          {"github_commits": "failure"}, "private-login-marker")
    report = DailyReport(date(2026, 9, 25), "示例团队", [member, MemberReport("u2", "示例乙")],
                         statuses, "private-markdown-marker", "private-html-marker",
                         datetime(2026, 9, 25, 10, tzinfo=timezone.utc))
    database = tmp_path / "日报 # history.sqlite3"
    write_report(database, report)
    return database, report


def client(database):
    return TestClient(create_app(database), base_url="http://127.0.0.1")


def test_query_preserves_content_order_and_only_exposes_contract_fields(history):
    database, report = history
    response = client(database).get("/api/v1/reports/2026-09-25")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"report_date", "team_name", "generated_at", "source_status", "members"}
    assert body["report_date"] == "2026-09-25"
    assert body["team_name"] == report.team_name
    assert datetime.fromisoformat(body["generated_at"]) == report.generated_at
    assert [member["member_id"] for member in body["members"]] == ["u1", "u2"]
    assert set(body["members"][0]) == {"member_id", "display_name", "commits", "tasks", "messages"}
    assert body["source_status"] == report.source_status
    assert body["members"][1]["commits"] == []
    assert set(body["members"][0]["commits"][0]) == {
        "record_id", "repository", "message", "committed_at", "url", "additions", "deletions", "files_changed"}
    for marker in ("private-login-marker", "private-markdown-marker", "private-html-marker", "ou_1", "author_login"):
        assert marker not in response.text


def test_empty_report_and_partial_source_failure_are_both_valid_history(history):
    database, report = history
    empty = replace(report, members=[MemberReport("u1", "示例甲")])
    write_report(database, empty)
    body = client(database).get("/api/v1/reports/2026-09-25").json()
    assert body["source_status"]["lark_tasks"] == "success"
    assert body["members"][0]["tasks"] == []
    partial = replace(empty, source_status={**report.source_status, "lark_tasks": "failure"})
    write_report(database, partial)
    response = client(database).get("/api/v1/reports/2026-09-25")
    assert response.status_code == 200
    assert response.json()["source_status"]["lark_tasks"] == "failure"


@pytest.mark.parametrize("day", ["20260925", "2026-02-30", "2026-09-25T00:00:00", "2026-9-25", "0000-01-01"])
def test_invalid_date_is_400_before_any_database_read(tmp_path, monkeypatch, day):
    def forbidden(*args):
        pytest.fail("Invalid input must not read history")
    monkeypatch.setattr(web_app, "get_report", forbidden)
    response = client(tmp_path / "absent.sqlite3").get(f"/api/v1/reports/{day}")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_report_date"


def test_missing_database_is_404_and_is_never_created(tmp_path):
    database = tmp_path / "missing" / "history.sqlite3"
    response = client(database).get("/api/v1/reports/2026-09-25")
    assert response.status_code == 404
    assert response.json()["error"] == {"code": "report_not_found", "message": "该日期尚无日报"}
    assert not database.parent.exists()


def test_absent_date_and_correct_empty_table_are_404(history):
    database, _ = history
    assert client(database).get("/api/v1/reports/2026-09-26").status_code == 404
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM daily_reports")
    assert client(database).get("/api/v1/reports/2026-09-25").status_code == 404


@pytest.mark.parametrize("content", [b"", b"not-a-database-secret-marker"])
def test_existing_broken_database_is_error_not_missing_history(tmp_path, content, caplog):
    database = tmp_path / "private-path-marker.sqlite3"
    database.write_bytes(content)
    response = client(database).get("/api/v1/reports/2026-09-25")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "storage_read_failed"
    assert "private-path-marker" not in response.text + caplog.text
    assert "secret-marker" not in response.text + caplog.text


@pytest.mark.parametrize("error,code", [(PermissionError("secret-path"), "storage_read_failed"),
                                        (RuntimeError("secret-token"), "internal_error")])
def test_unexpected_read_failures_have_safe_errors(history, monkeypatch, caplog, error, code):
    def fail(*args):
        raise error
    monkeypatch.setattr(web_app, "get_report", fail)
    response = client(history[0]).get("/api/v1/reports/2026-09-25")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == code
    assert str(error) not in response.text + caplog.text
    assert all(record.run_id for record in caplog.records)


def test_malformed_saved_payload_is_not_silently_repaired(history, caplog):
    database, _ = history
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE daily_reports SET payload_json = ?", ('{"private-message-marker":',))
    response = client(database).get("/api/v1/reports/2026-09-25")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "invalid_report_data"
    assert "private-message-marker" not in response.text + caplog.text


@pytest.mark.parametrize("change", ["missing_status", "unknown_status", "extra_status", "all_failed",
                                    "failed_with_records", "duplicate_member", "naive_time", "wrong_field_type"])
def test_invalid_history_states_are_errors_rather_than_plausible_reports(history, change):
    database, report = history
    if change == "missing_status":
        report = replace(report, source_status={"github_commits": "success"})
    elif change == "unknown_status":
        report = replace(report, source_status={**report.source_status, "lark_tasks": "unknown"})
    elif change == "extra_status":
        report = replace(report, source_status={**report.source_status, "another": "success"})
    elif change == "all_failed":
        report = replace(report, source_status={key: "failure" for key in report.source_status})
    elif change == "failed_with_records":
        report = replace(report, source_status={**report.source_status, "lark_tasks": "failure"})
    elif change == "duplicate_member":
        report = replace(report, members=[report.members[0], report.members[0]])
    elif change == "naive_time":
        report = replace(report, generated_at=report.generated_at.replace(tzinfo=None))
    else:
        member = replace(report.members[0], commits=[replace(report.members[0].commits[0], additions="12")])
        report = replace(report, members=[member])
    write_report(database, report)
    response = client(database).get("/api/v1/reports/2026-09-25")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "invalid_report_data"


def test_query_never_invokes_generation_or_notifications_or_changes_database(history, monkeypatch):
    from smart_daily_report import main as pipeline
    from smart_daily_report.shared import storage
    from smart_daily_report.collector import github, lark
    from smart_daily_report.generator import formatter
    from smart_daily_report.notifier import email, lark_bot
    database, _ = history
    before = database.read_bytes()
    def forbidden(*args, **kwargs):
        pytest.fail("Viewing history must not generate, write or notify")
    for module, name in ((pipeline, "run_report"), (storage, "write_report"), (github, "collect_commits"),
                         (lark, "collect_tasks"), (lark, "collect_messages"), (formatter, "generate_daily_report"),
                         (email, "send_email"), (lark_bot, "send_lark_message")):
        monkeypatch.setattr(module, name, forbidden)
    for day in ("2026-09-25", "2026-09-26", "2026-09-25"):
        client(database).get(f"/api/v1/reports/{day}?database=other.sqlite3")
    assert database.read_bytes() == before


def test_shared_reader_uses_sqlite_read_only_mode(history, monkeypatch):
    database, report = history
    original = sqlite3.connect
    connections = []
    def connect(path, **kwargs):
        connections.append((path, kwargs))
        return original(path, **kwargs)
    monkeypatch.setattr(sqlite3, "connect", connect)
    assert get_report(database, report.report_date).team_name == report.team_name
    assert connections == [(database.resolve().as_uri() + "?mode=ro", {"uri": True})]


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_write_methods_are_rejected_without_side_effects(history, method):
    database, _ = history
    before = database.read_bytes()
    response = getattr(client(database), method)("/api/v1/reports/2026-09-25")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert database.read_bytes() == before


def test_origin_and_host_limit_local_history_access(history):
    browser = client(history[0])
    blocked = browser.get("/api/v1/reports/2026-09-25", headers={"Origin": "https://untrusted.example"})
    assert blocked.status_code == 403
    assert blocked.headers["cache-control"] == "no-store"
    allowed = browser.get("/api/v1/reports/2026-09-25", headers={"Origin": "http://127.0.0.1:5173"})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert browser.get("/api/v1/reports/2026-09-25", headers={"Host": "untrusted.example"}).status_code == 400
    preflight = browser.options("/api/v1/reports/2026-09-25", headers={
        "Origin": "http://127.0.0.1:4173", "Access-Control-Request-Method": "GET"})
    assert preflight.status_code == 200


def test_untrusted_text_remains_text_and_bad_links_are_not_exposed(history):
    database, report = history
    member = report.members[0]
    attack = '<img src=x onerror="alert(1)">'
    member = replace(member, commits=[replace(member.commits[0], message=attack, url="javascript:alert(1)")],
                     tasks=[replace(member.tasks[0], url="data:text/html,attack")])
    write_report(database, replace(report, members=[member]))
    body = client(database).get("/api/v1/reports/2026-09-25").json()
    assert body["members"][0]["commits"][0]["message"] == attack
    assert body["members"][0]["commits"][0]["url"] is None
    assert body["members"][0]["tasks"][0]["url"] is None


def test_filtered_message_does_not_leak_through_new_query_surface(history, records, monkeypatch, caplog):
    from smart_daily_report.shared.identity import filter_sensitive_messages
    database, report = history
    marker = "sensitive-message-marker"
    safe_messages = filter_sensitive_messages([replace(records["message"], content=marker)], [marker])
    write_report(database, replace(report, members=[replace(report.members[0], messages=safe_messages)]))
    monkeypatch.setenv("SMTP_PASSWORD", "secret-credential-marker")
    response = client(database).get("/api/v1/reports/2026-09-25")
    assert response.status_code == 200
    assert response.json()["members"][0]["messages"] == []
    assert marker not in response.text + caplog.text
    assert "secret-credential-marker" not in response.text + caplog.text


def test_web_entry_only_binds_loopback_without_loading_push_configuration(tmp_path, monkeypatch):
    from smart_daily_report.web import main as entry
    calls = []
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    assert main(["--database", str(tmp_path / "reports.sqlite3")]) == 0
    assert calls == [{"host": "127.0.0.1", "port": 8000, "access_log": False}]
    with pytest.raises(SystemExit):
        main(["--database", "reports.sqlite3", "--port", "0"])


def test_existing_cli_does_not_import_optional_web_framework():
    code = "import sys; import smart_daily_report.main; assert 'fastapi' not in sys.modules; assert 'uvicorn' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_openapi_describes_the_business_query_and_unknown_route_is_safe(history):
    browser = client(history[0])
    schema = browser.get("/openapi.json").json()
    assert set(schema["paths"]) == {"/api/v1/reports/{report_date}"}
    assert browser.get("/api/v1/unknown").json()["error"]["code"] == "endpoint_not_found"
