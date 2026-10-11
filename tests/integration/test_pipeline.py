from datetime import date, datetime
from pathlib import Path
from time import perf_counter

import httpx

from smart_daily_report.main import run_report
from smart_daily_report.generator.formatter import generate_daily_report
from smart_daily_report.shared.models import MemberReport


def test_pipeline_dry_run_generates_and_stores_without_delivery(config, tmp_path):
    config = config.__class__(**{**config.__dict__, "github_repositories": ["acme/repo"], "database_path": str(tmp_path / "db.sqlite")})
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])))
    result = run_report(config, date(2026, 9, 25), dry_run=True, client=client)
    assert result.success and result.report is not None
    assert result.deliveries == {}
    assert Path(config.database_path).exists()


def test_unlinked_historical_commit_is_included_without_unmapped_warning(config, tmp_path):
    from dataclasses import replace
    import logging

    config.members[0] = replace(config.members[0], github_author_names=["gaochang0339-web"])
    config = replace(config, github_repositories=["acme/repo"], database_path=str(tmp_path / "db.sqlite"))
    def handler(request):
        if request.url.path.endswith("/commits"):
            return httpx.Response(200, json=[
                {"sha": "current", "commit": {"message": "current work", "author": {"name": "Chang GAO", "date": "2026-04-23T02:00:00Z"}},
                 "author": {"login": "octo"}, "html_url": "https://git/current", "stats": {"additions": 1, "deletions": 0}},
                {"sha": "historical", "commit": {"message": "historical work", "author": {"name": "gaochang0339-web", "date": "2026-04-23T03:00:00Z"}},
                 "author": None, "html_url": "https://git/historical", "stats": {"additions": 2, "deletions": 0}},
            ])
        return httpx.Response(404)
    events = []
    logger = logging.getLogger("smart_daily_report")
    capture = logging.Handler()
    capture.emit = lambda record: events.append(record.getMessage())
    logger.addHandler(capture)
    try:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        result = run_report(config, date(2026, 4, 23), dry_run=True, client=client, sleep=lambda _: None)
    finally:
        logger.removeHandler(capture)
    assert result.success and result.report is not None
    assert [item.record_id for item in result.report.members[0].commits] == ["current", "historical"]
    assert "records_unmapped" not in events


def test_malformed_github_identity_is_source_failure_without_blocking_healthy_feishu_source(config, tmp_path):
    from dataclasses import replace
    cfg = replace(config, github_repositories=["acme/repo"], lark_project_ids=["project"],
                  lark_app_id="app", lark_app_secret="secret", database_path=str(tmp_path / "db.sqlite"))
    def handler(request):
        if request.url.path.endswith("/repos/acme/repo/commits"):
            return httpx.Response(200, json=[{"sha": "sha", "commit": {"message": "change", "author": {"name": "A", "date": "2026-09-25T02:00:00Z"}},
                "author": {"login": 123}, "html_url": "https://git/sha", "stats": {"additions": 1, "deletions": 0}, "files": []}])
        if request.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            return httpx.Response(200, json={"tenant_access_token": "synthetic-token"})
        if request.url.path.endswith("/task/v2/tasklists/project/tasks"):
            return httpx.Response(200, json={"code": 0, "data": {"items": [], "has_more": False}})
        return httpx.Response(404)
    result = run_report(cfg, date(2026, 9, 25), dry_run=True, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert result.success and result.report is not None
    assert result.report.source_status == {"github_commits": "failure", "lark_tasks": "success", "lark_messages": "success"}


def test_weekend_skips_before_any_network_or_storage(config, tmp_path):
    config = config.__class__(**{**config.__dict__, "database_path": str(tmp_path / "db.sqlite")})
    result = run_report(config, date(2026, 9, 26), dry_run=True)
    assert result.success and result.skipped
    assert not Path(config.database_path).exists()


def test_pipeline_collects_generates_stores_and_delivers_both_channels(config, tmp_path):
    from datetime import datetime
    config = config.__class__(**{
        **config.__dict__, "database_path": str(tmp_path / "db.sqlite"),
        "github_repositories": ["acme/repo"], "github_token": "gh-token",
        "lark_project_ids": ["project"], "lark_chat_ids": ["chat"],
        "lark_app_id": "app", "lark_app_secret": "app-secret", "lark_webhook": "https://hook.test/key",
    })
    def handler(request):
        if request.url.path.endswith("/repos/acme/repo/commits"):
            return httpx.Response(200, json=[{"sha": "sha", "commit": {"message": "fix", "author": {"name": "A", "date": "2026-09-25T02:00:00Z"}}, "author": {"login": "octo"}, "html_url": "https://git/sha", "stats": {"additions": 4, "deletions": 2, "total": 3}}])
        if request.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            return httpx.Response(200, json={"tenant_access_token": "lark-token"})
        if request.url.path.endswith("/task/v2/tasklists/project/tasks"):
            return httpx.Response(200, json={"code": 0, "data": {"items": [{"guid": "task", "summary": "Ship", "completed_at": 1790301600000, "members": [{"id": "ou_1", "type": "user", "role": "assignee"}]}], "has_more": False}})
        if request.url.path.endswith("/im/v1/messages"):
            return httpx.Response(200, json={"code": 0, "data": {"items": [{"message_id": "msg", "body": {"content": "{\"text\":\"日报 done\"}"}, "sender": {"id": "ou_1"}, "create_time": "2026-09-25T02:00:00Z"}]}})
        if request.url.path.endswith("/key"):
            return httpx.Response(200, json={"StatusCode": 0})
        return httpx.Response(404)
    class SMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self): pass
        def login(self, *args): pass
        def send_message(self, message):
            assert "fix" in message.get_body(("html",)).get_content()
            return {}
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = run_report(config, date(2026, 9, 25), client=client, smtp_factory=SMTP, sleep=lambda _: None)
    assert result.success and result.report is not None
    assert result.deliveries["email"].success and result.deliveries["lark"].success
    assert "fix" in result.report.markdown and "Ship" in result.report.markdown and "日报 done" in result.report.markdown
    assert Path(config.database_path).exists()


def test_unexpected_email_error_does_not_block_lark_delivery(config, tmp_path, monkeypatch):
    from smart_daily_report.shared.models import DeliveryResult
    from smart_daily_report.main import run_report
    config = config.__class__(**{**config.__dict__, "database_path": str(tmp_path / "db.sqlite"), "lark_webhook": "https://hook.test", "github_repositories": ["acme/repo"]})
    called = []
    monkeypatch.setattr("smart_daily_report.main.send_email", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("mail")))
    monkeypatch.setattr("smart_daily_report.main.send_lark_message", lambda *args, **kwargs: (called.append(True), DeliveryResult(True, 1))[1])
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])))
    result = run_report(config, date(2026, 9, 25), dry_run=False, client=client, sleep=lambda _: None)
    assert not result.success and result.deliveries["email"].error_code == "email_unhandled"
    assert result.deliveries["lark"].success and called == [True]


def test_five_member_generation_meets_sixty_second_budget(records, statuses):
    members = [MemberReport(f"m{i}", f"Member {i}", [records["commit"]], [records["task"]], [records["message"]]) for i in range(5)]
    started = perf_counter()
    report = generate_daily_report(date(2026, 9, 25), "team", members, statuses, datetime.now().astimezone())
    elapsed = perf_counter() - started
    assert len(report.members) == 5 and elapsed < 60


def test_cli_pipeline_does_not_attempt_disabled_email(config,tmp_path,monkeypatch):
    from dataclasses import replace
    cfg=replace(config,github_repositories=['acme/repo'],database_path=str(tmp_path/'report.sqlite3'),smtp=replace(config.smtp,host=''))
    calls=[]
    monkeypatch.setattr('smart_daily_report.main.send_email',lambda *args,**kwargs:calls.append(args))
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=[]))) as client:
        result=run_report(cfg,date(2026,9,25),client=client)
    assert calls==[] and result.success and result.deliveries=={}
