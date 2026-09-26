import json
from datetime import date

import httpx

from smart_daily_report.main import main, run_health_check, run_report
from smart_daily_report.shared.health import check_dependencies
from smart_daily_report.shared.http import TokenProvider, request_with_retry


def test_retry_handles_timeout_then_success():
    calls, waits = [], []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(200)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    response, attempts, error = request_with_retry(client, "GET", "https://example.test", sleep=waits.append)
    assert response.status_code == 200 and attempts == 2 and error is None and waits == [1]


def test_retry_uses_retry_after_and_gives_up_after_limit():
    waits = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(429, headers={"Retry-After": "2"})))
    response, attempts, error = request_with_retry(client, "GET", "https://example.test", sleep=waits.append)
    assert response.status_code == 429 and attempts == 3 and error == "http_429" and waits == [2.0, 2.0]


def test_token_provider_fetches_and_refreshes():
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: (calls.append(request), httpx.Response(200, json={"tenant_access_token": f"t{len(calls)}"}))[1]))
    provider = TokenProvider(client, "https://lark", "/token", "id", "secret")
    assert provider.get() == "t1" and provider.get() == "t1" and provider.get(refresh=True) == "t2"
    assert len(calls) == 2


def test_health_check_passes_without_optional_api_sources(config, monkeypatch):
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def noop(self): return 250, b"OK"
    monkeypatch.setattr("smart_daily_report.shared.health.smtplib.SMTP", SMTP)
    result = run_health_check(config, httpx.Client())
    assert result.success and result.checks["smtp"]


def test_health_check_uses_implicit_ssl_when_configured(config, monkeypatch):
    from dataclasses import replace
    calls = []
    class SMTPSSL:
        def __init__(self, *args, **kwargs): calls.append((args, kwargs))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def noop(self): return 250, b"OK"
    config = replace(config, smtp=config.smtp.__class__("smtp.163.com", 465, None, None, "from@test", [], False, True))
    monkeypatch.setattr("smart_daily_report.shared.health.smtplib.SMTP_SSL", SMTPSSL)
    result = check_dependencies(config, httpx.Client())
    assert result.success and calls[0][0][:2] == ("smtp.163.com", 465)


def test_health_check_accepts_public_github_repository_without_token(config, monkeypatch):
    config.github_repositories.append("a/b")
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def noop(self): return 250, b"OK"
    monkeypatch.setattr("smart_daily_report.shared.health.smtplib.SMTP", SMTP)
    def handler(request):
        assert request.url.path == "/repos/a/b"
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"full_name": "a/b"})
    result = check_dependencies(config, httpx.Client(transport=httpx.MockTransport(handler)))
    assert result.success and result.checks["github_repository_1"]


def test_health_check_reports_private_github_repository_without_token(config, monkeypatch):
    config.github_repositories.append("a/b")
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def noop(self): return 250, b"OK"
    monkeypatch.setattr("smart_daily_report.shared.health.smtplib.SMTP", SMTP)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404)))
    result = check_dependencies(config, client)
    assert not result.success and result.checks["github_repository_1"] is False


def test_health_check_exercises_connected_github_lark_and_webhook(config, monkeypatch):
    config = config.__class__(**{**config.__dict__, "github_repositories": ["a/b"], "github_token": "gh",
        "lark_project_ids": ["p"], "lark_app_id": "app", "lark_app_secret": "secret", "lark_webhook": "https://hook"})
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def noop(self): return 250, b"OK"
    monkeypatch.setattr("smart_daily_report.shared.health.smtplib.SMTP", SMTP)
    def handler(request):
        if request.url.path.endswith("/tasks/search"):
            assert json.loads(request.content)["page_size"] == 1
            assert "page_size" not in request.url.params
        return httpx.Response(200, json={"tenant_access_token": "ok"} if "tenant_access_token" in request.url.path else {"resources": []})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = check_dependencies(config, client)
    assert result.success and result.checks["github_api"] and result.checks["lark_token"] and result.checks["lark_webhook_configured"]


def test_health_check_handles_unreachable_services(config, monkeypatch):
    config = config.__class__(**{**config.__dict__, "github_repositories": ["a/b"], "github_token": "gh",
        "lark_project_ids": ["p"], "lark_app_id": "app", "lark_app_secret": "secret"})
    class SMTP:
        def __init__(self, *args, **kwargs): raise OSError("offline")
    monkeypatch.setattr("smart_daily_report.shared.health.smtplib.SMTP", SMTP)
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    result = check_dependencies(config, client)
    assert not result.success and result.checks["github_api"] is False and result.checks["lark_token"] is False and result.checks["smtp"] is False


def test_run_report_dry_run_and_all_sources_failure(config, tmp_path):
    config = config.__class__(**{**config.__dict__, "database_path": str(tmp_path / "db.sqlite")})
    result = run_report(config, date(2026, 9, 25), dry_run=True)
    assert result.success and result.report is not None
    config = config.__class__(**{**config.__dict__, "github_repositories": ["a/b"], "github_token": "token",
                                 "lark_project_ids": ["project"], "lark_chat_ids": ["chat"]})
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403)))
    failed = run_report(config, date(2026, 9, 25), dry_run=True, client=client, sleep=lambda _: None)
    assert not failed.success and failed.error_code == "all_sources_failed"


def test_main_returns_error_for_missing_config(tmp_path):
    assert main(["--config", str(tmp_path / "missing.yaml")]) == 2


def test_main_check_and_run_exit_codes(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("""team: {name: team, timezone: UTC, smtp: {host: smtp, sender: a, recipients: []}}
members:
  - {member_id: m, display_name: M}
""", encoding="utf-8")
    from smart_daily_report.shared.models import HealthCheckResult, RunResult
    monkeypatch.setattr("smart_daily_report.main.run_health_check", lambda config: HealthCheckResult(True, {"configuration": True}))
    monkeypatch.setattr("smart_daily_report.main.run_report", lambda *args: RunResult(True))
    assert main(["--config", str(config_path), "--check"]) == 0
    assert main(["--config", str(config_path), "--dry-run"]) == 0
    monkeypatch.setattr("smart_daily_report.main.run_report", lambda *args: RunResult(False))
    assert main(["--config", str(config_path)]) == 1
