import json
from datetime import datetime, timezone

import httpx

from smart_daily_report.collector.github import collect_commits
from smart_daily_report.collector.lark import _dt, _message_text, collect_messages, collect_tasks
from smart_daily_report.shared.http import TokenProvider, request_with_retry
from smart_daily_report.shared.models import CollectionWindow


def test_github_collects_and_maps_commit():
    def handler(request):
        return httpx.Response(200, json=[{"sha": "abc", "commit": {"message": "fix\nmore", "author": {"name": "A", "date": "2026-09-25T01:00:00Z"}}, "author": {"login": "octo"}, "html_url": "https://git/abc", "stats": {"additions": 3, "deletions": 1}, "files": [{}, {}]}])
    client = httpx.Client(transport=httpx.MockTransport(handler))
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    result = collect_commits(client, ["acme/repo"], window)
    assert result.status == "success" and result.records[0].message == "fix"
    assert result.records[0].additions == 3 and result.records[0].files_changed == 2


def test_github_empty_is_success_and_http_failure_is_failure():
    window = CollectionWindow(datetime.now(timezone.utc), datetime.now(timezone.utc))
    empty = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])))
    assert collect_commits(empty, ["a/b"], window).status == "success"
    sleeps = []
    failed = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    result = collect_commits(failed, ["a/b"], window, sleep=sleeps.append)
    assert result.status == "failure" and result.attempts == 3 and len(sleeps) == 2


class FakeToken:
    def __init__(self): self.refreshes = 0
    def get(self, refresh=False):
        if refresh: self.refreshes += 1
        return "new" if self.refreshes else "old"


def test_lark_task_refreshes_token_once_and_collects():
    token = FakeToken()
    seen = []
    def handler(request):
        seen.append(request.headers.get("Authorization"))
        if len(seen) == 1: return httpx.Response(401)
        return httpx.Response(200, json={"code": 0, "data": {"items": [{"guid": "t", "summary": "Ship", "status": "done", "assignee": {"id": "ou"}, "updated_time": "2026-09-25T02:00:00Z"}]}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    result = collect_tasks(client, ["project"], window, token, "https://lark.test", "/tasks", sleep=lambda _: None)
    assert result.status == "success" and result.records[0].assignee_user_id == "ou"
    assert seen == ["Bearer old", "Bearer new"]


def test_lark_message_filters_sensitive_and_nonmatching():
    token = FakeToken()
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 0, "data": {"items": [
        {"message_id": "1", "body": {"content": "{\"text\":\"日报 done\"}"}, "sender": {"id": "u"}, "create_time": "2026-09-25T02:00:00Z"},
        {"message_id": "2", "body": {"content": "{\"text\":\"日报 薪资 secret\"}"}, "sender": {"id": "u"}, "create_time": "2026-09-25T02:00:00Z"},
        {"message_id": "3", "body": {"content": "{\"text\":\"闲聊\"}"}, "sender": {"id": "u"}, "create_time": "2026-09-25T02:00:00Z"},
    ]}})))
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    result = collect_messages(client, ["chat"], window, ["日报"], ["薪资"], token, "https://lark.test", "/messages")
    assert result.status == "success" and [item.content for item in result.records] == ["日报 done"]


def test_request_retry_does_not_retry_client_error():
    calls = []
    client = httpx.Client(transport=httpx.MockTransport(lambda request: (calls.append(request), httpx.Response(403))[1]))
    response, attempts, error = request_with_retry(client, "GET", "https://x", sleep=lambda _: None)
    assert response.status_code == 403 and attempts == 1 and error == "http_403" and len(calls) == 1


def test_github_invalid_response_returns_failure():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"wrong": True})))
    window = CollectionWindow(datetime.now(timezone.utc), datetime.now(timezone.utc))
    result = collect_commits(client, ["a/b"], window)
    assert result.status == "failure" and result.error_code == "invalid_payload"


def test_github_follows_link_header_and_marks_rate_limit():
    calls, waits = [], []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1"})
        return httpx.Response(200, json=[], headers={"Link": '<https://api.test/page2>; rel="next"'}) if len(calls) == 2 else httpx.Response(200, json=[])
    client = httpx.Client(transport=httpx.MockTransport(handler))
    window = CollectionWindow(datetime.now(timezone.utc), datetime.now(timezone.utc))
    result = collect_commits(client, ["a/b"], window, "https://api.test", sleep=waits.append)
    assert result.status == "success" and len(calls) == 3 and waits == [0]


def test_github_fetches_change_statistics_when_list_omits_them():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/commits"):
            return httpx.Response(200, json=[{"sha": "sha", "url": "https://api.test/detail", "commit": {
                "message": "change", "author": {"name": "A", "date": "2026-09-25T01:00:00Z"}},
                "author": {"login": "octo"}, "html_url": "https://git/sha"}])
        return httpx.Response(200, json={"stats": {"additions": 7, "deletions": 2, "total": 4}, "files": [{}, {}, {}, {}]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    result = collect_commits(client, ["acme/repo"], window, "https://api.test")
    assert result.status == "success" and result.records[0].additions == 7
    assert result.records[0].deletions == 2 and result.records[0].files_changed == 4
    assert calls == ["/repos/acme/repo/commits", "/detail"]


def test_lark_task_empty_result_is_success():
    token = FakeToken()
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 0, "data": {"items": []}})))
    window = CollectionWindow(datetime.now(timezone.utc), datetime.now(timezone.utc))
    result = collect_tasks(client, ["p"], window, token, "https://lark", "/tasks", sleep=lambda _: None)
    assert result.status == "success" and result.records == []


def test_lark_message_http_failure_is_not_empty_success():
    token = FakeToken()
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    window = CollectionWindow(datetime.now(timezone.utc), datetime.now(timezone.utc))
    result = collect_messages(client, ["chat"], window, [], [], token, "https://lark", "/messages", sleep=lambda _: None)
    assert result.status == "failure" and result.attempts == 3


def test_lark_task_paginates_filters_date_and_parses_assignee_string():
    requests = []
    def handler(request):
        requests.append(request)
        assert json.loads(request.content)["page_size"] == 100
        assert "page_size" not in request.url.params
        assert "page_token" not in json.loads(request.content)
        if request.url.params.get("page_token") is None:
            return httpx.Response(200, json={"code": 0, "data": {"items": [{"guid": "old", "updated_time": "2026-09-24T02:00:00Z"}], "page_token": "next", "has_more": True}})
        assert request.url.params["page_token"] == "next"
        return httpx.Response(200, json={"code": 0, "data": {"items": [{"guid": "new", "assignee_id": "ou", "updated_time": "2026-09-25T02:00:00Z"}], "page_token": "unused", "has_more": False}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    result = collect_tasks(client, ["p"], window, FakeToken(), "https://lark", "/tasks", sleep=lambda _: None)
    assert len(requests) == 2 and result.status == "success" and [r.record_id for r in result.records] == ["new"]


def test_lark_task_repeated_page_token_fails_without_replaying_pages():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"code": 0, "data": {"items": [], "page_token": "same", "has_more": True}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    window = CollectionWindow(datetime.now(timezone.utc), datetime.now(timezone.utc))
    result = collect_tasks(client, ["p"], window, FakeToken(), "https://lark", "/tasks", sleep=lambda _: None)
    assert result.status == "failure" and result.error_code == "invalid_pagination"
    assert result.attempts == len(requests) == 2


def test_lark_message_parses_plain_text_and_rejects_api_error():
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    plain = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 0, "data": {"items": [
        {"message_id": "1", "content": "日报 plain", "sender": {"id": "ou"}, "create_time": "2026-09-25T02:00:00Z"}]}})))
    result = collect_messages(plain, ["chat"], window, ["日报"], [], FakeToken(), "https://lark", "/messages")
    assert result.status == "success" and result.records[0].content == "日报 plain"
    denied = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 999, "msg": "denied"})))
    result = collect_messages(denied, ["chat"], window, [], [], FakeToken(), "https://lark", "/messages")
    assert result.status == "failure" and result.error_code == "lark_999"


def test_lark_token_provider_failure_is_reported():
    class Broken:
        def get(self, refresh=False): raise RuntimeError("no token")
    window = CollectionWindow(datetime.now(timezone.utc), datetime.now(timezone.utc))
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 0, "data": {"items": []}})))
    tasks = collect_tasks(client, ["p"], window, Broken(), "https://lark", "/tasks")
    messages = collect_messages(client, ["c"], window, [], [], Broken(), "https://lark", "/messages")
    assert tasks.error_code == "token_refresh_failed" and messages.error_code == "token_refresh_failed"


def test_lark_task_rejects_malformed_payload_and_refreshes_expired_code():
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    malformed = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 0, "data": {"items": [{"updated_time": "not-a-date"}]}})))
    bad = collect_tasks(malformed, ["p"], window, FakeToken(), "https://lark", "/tasks")
    assert bad.status == "failure" and bad.error_code == "invalid_payload"
    calls = []
    def handler(request):
        if request.url.path == "/token":
            calls.append("token")
            return httpx.Response(200, json={"tenant_access_token": f"t{len(calls)}"})
        if not any(item.startswith("api") for item in calls):
            calls.append("api1")
            return httpx.Response(200, json={"code": 99991663})
        calls.append("api2")
        return httpx.Response(200, json={"code": 0, "data": {"items": []}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TokenProvider(client, "https://lark", "/token", "a", "b")
    result = collect_tasks(client, ["p"], window, provider, "https://lark", "/tasks")
    assert result.status == "success" and calls.count("token") == 2


def test_lark_messages_refresh_after_unauthorized_and_follow_pages():
    calls = []
    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"tenant_access_token": f"t{sum(c == 'token' for c in calls) + 1}"})
        calls.append("api")
        if len(calls) == 1: return httpx.Response(401)
        if len(calls) == 2:
            return httpx.Response(200, json={"code": 0, "data": {"items": [{"message_id": "1", "content": "plain", "create_time": 1780000000}], "page_token": "next"}})
        return httpx.Response(200, json={"code": 0, "data": {"items": [{"message_id": "2", "content": {"text": "dict"}, "create_time": 1780000000}]}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TokenProvider(client, "https://lark", "/token", "a", "b")
    window = CollectionWindow(datetime(2020, 1, 1, tzinfo=timezone.utc), datetime(2030, 1, 1, tzinfo=timezone.utc))
    result = collect_messages(client, ["chat"], window, [], [], provider, "https://lark", "/messages")
    assert result.status == "success" and len(result.records) == 2


def test_lark_message_api_token_error_refreshes_and_retries():
    calls = []
    def handler(request):
        if request.url.path == "/token":
            return httpx.Response(200, json={"tenant_access_token": f"t{len([c for c in calls if c == 'token']) + 1}"})
        calls.append("api")
        if len(calls) == 1:
            return httpx.Response(200, json={"code": 99991663})
        return httpx.Response(200, json={"code": 0, "data": {"items": []}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TokenProvider(client, "https://lark", "/token", "a", "b")
    window = CollectionWindow(datetime(2020, 1, 1, tzinfo=timezone.utc), datetime(2030, 1, 1, tzinfo=timezone.utc))
    result = collect_messages(client, ["chat"], window, [], [], provider, "https://lark", "/messages")
    assert result.status == "success" and calls == ["api", "api"]


def test_lark_timestamp_and_message_content_variants_are_normalized():
    from datetime import timedelta
    assert _dt("1780000000").utcoffset() == timedelta(0)
    assert _dt(1780000000000).utcoffset() == timedelta(0)
    assert _message_text({"content": {"text": "structured"}}) == "structured"
    assert _message_text({"content": "plain text"}) == "plain text"
