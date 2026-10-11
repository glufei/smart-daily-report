import json
from datetime import datetime, timezone

import httpx
import pytest

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
        return httpx.Response(200, json={"code": 0, "data": {"items": [{"guid": "t", "summary": "Ship", "completed_at": 1790301600000, "members": [{"id": "ou", "type": "user", "role": "assignee"}]}], "has_more": False}})
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


@pytest.mark.parametrize("field,value", [("login", 123), ("name", ["unexpected"])])
def test_github_non_string_author_identity_fails_source_instead_of_emitting_invalid_record(field, value):
    item = {"sha": "sha", "commit": {"message": "change", "author": {"name": "A", "date": "2026-09-25T01:00:00Z"}},
            "author": {"login": "octo"}, "html_url": "https://git/sha", "stats": {"additions": 1, "deletions": 0}, "files": []}
    (item["author"] if field == "login" else item["commit"]["author"])[field] = value
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[item])))
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    result = collect_commits(client, ["acme/repo"], window)
    assert result.status == "failure" and result.error_code == "invalid_payload" and result.records == []


def test_github_repeated_commit_page_url_fails_with_bounded_requests():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if len(calls) > 2:
            return httpx.Response(400)
        if len(calls) == 1:
            return httpx.Response(200, json=[], headers={"Link": '<https://api.test/repos/acme/repo/commits?page=2>; rel="next"'})
        return httpx.Response(200, json=[], headers={"Link": '<https://api.test/repos/acme/repo/commits?page=2>; rel="next"'})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    result = collect_commits(client, ["acme/repo"], window, "https://api.test")
    assert result.status == "failure" and result.error_code == "invalid_pagination" and result.records == []
    assert len(calls) == 2


def test_lark_non_string_sender_identity_fails_source_instead_of_emitting_invalid_record():
    payload = {"code": 0, "data": {"items": [{"message_id": "m", "content": "日报完成", "sender": {"id": 123},
              "create_time": "2026-09-25T02:00:00Z"}], "has_more": False}}
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    result = collect_messages(client, ["chat"], window, [], [], FakeToken(), "https://lark.test", "/messages")
    assert result.status == "failure" and result.error_code == "invalid_payload" and result.records == []


@pytest.mark.parametrize("sender", [[], "", 0])
def test_lark_falsy_non_object_sender_fails_source_instead_of_becoming_unassigned(sender):
    payload = {"code": 0, "data": {"items": [{"message_id": "m", "content": "日报完成", "sender": sender,
              "create_time": "2026-09-25T02:00:00Z"}], "has_more": False}}
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    result = collect_messages(client, ["chat"], window, [], [], FakeToken(), "https://lark.test", "/messages")
    assert result.status == "failure" and result.error_code == "invalid_payload" and result.records == []


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
        return httpx.Response(200, json={"stats": {"additions": 7, "deletions": 2, "total": 4}, "files": [{"filename": f"file-{i}.py"} for i in range(4)]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    result = collect_commits(client, ["acme/repo"], window, "https://api.test")
    assert result.status == "success" and result.records[0].additions == 7
    assert result.records[0].deletions == 2 and result.records[0].files_changed == 4
    assert calls == ["/repos/acme/repo/commits", "/detail"]


def test_lark_task_empty_result_is_success():
    token = FakeToken()
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 0, "data": {"items": [], "has_more": False}})))
    window = CollectionWindow(datetime.now(timezone.utc), datetime.now(timezone.utc))
    result = collect_tasks(client, ["p"], window, token, "https://lark", "/tasks", sleep=lambda _: None)
    assert result.status == "success" and result.records == []


def test_lark_message_http_failure_is_not_empty_success():
    token = FakeToken()
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    window = CollectionWindow(datetime.now(timezone.utc), datetime.now(timezone.utc))
    result = collect_messages(client, ["chat"], window, [], [], token, "https://lark", "/messages", sleep=lambda _: None)
    assert result.status == "failure" and result.attempts == 3


def test_lark_task_paginates_filters_completion_date_and_parses_assignee_members():
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == "GET" and request.content == b""
        assert request.url.params["page_size"] == "100"
        if request.url.params.get("page_token") is None:
            return httpx.Response(200, json={"code": 0, "data": {"items": [{"guid": "old", "summary": "Old", "completed_at": 1790215200000, "members": []}], "page_token": "next", "has_more": True}})
        assert request.url.params["page_token"] == "next"
        return httpx.Response(200, json={"code": 0, "data": {"items": [{"guid": "new", "summary": "New", "completed_at": 1790301600000, "members": [{"id": "ou", "type": "user", "role": "assignee"}]}], "page_token": "unused", "has_more": False}})
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
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"code": 0, "data": {"items": [], "has_more": False}})))
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
        return httpx.Response(200, json={"code": 0, "data": {"items": [], "has_more": False}})
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
        return httpx.Response(200, json={"code": 0, "data": {"items": [], "has_more": False}})
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


def test_tasklist_get_uses_completion_time_not_update_time():
    completed=datetime.fromisoformat('2026-09-25T10:00:00+08:00')
    window=CollectionWindow(datetime.fromisoformat('2026-09-25T00:00:00+08:00'),datetime.fromisoformat('2026-09-26T00:00:00+08:00'))
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(200,json={'code':0,'data':{'items':[{'guid':'task-1','summary':'Ship','completed_at':str(int(completed.timestamp()*1000)),
             'updated_time':'2026-09-26T03:00:00Z','members':[{'id':'ou_1','type':'user','role':'assignee'}]}],'has_more':False}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=collect_tasks(client,['list-1'],window,FakeToken(),'https://lark.test/open-apis','/task/v2/tasklists/{tasklist_guid}/tasks',sleep=lambda _:None)
    assert requests[0].method=='GET'
    assert requests[0].url.path=='/open-apis/task/v2/tasklists/list-1/tasks'
    assert dict(requests[0].url.params)=={'page_size':'100','completed':'true','user_id_type':'open_id'}
    assert requests[0].content==b''
    assert result.status=='success' and len(result.records)==1
    record=result.records[0]
    assert (record.record_id,record.assignee_user_id,record.status)==('task-1','ou_1','completed')
    assert record.changed_at==completed and record.status_from is None


def completed_task(guid='task-1', **changes):
    item={'guid':guid,'summary':'Ship','completed_at':int(datetime(2026,9,25,2,tzinfo=timezone.utc).timestamp()*1000),
          'members':[{'id':'ou_1','type':'user','role':'assignee'}]}
    return {**item,**changes}


def task_result(items,handler=None,lists=None):
    window=CollectionWindow(datetime.fromisoformat('2026-09-25T00:00:00+08:00'),datetime.fromisoformat('2026-09-26T00:00:00+08:00'))
    with httpx.Client(transport=httpx.MockTransport(handler or (lambda r:httpx.Response(200,json={'code':0,'data':{'items':items,'has_more':False}})))) as client:
        return collect_tasks(client,lists or ['list-1'],window,FakeToken(),'https://lark.test','/task/v2/tasklists/{tasklist_guid}/tasks',sleep=lambda _:None)


def test_completion_window_is_left_closed_right_open():
    start=int(datetime.fromisoformat('2026-09-25T00:00:00+08:00').timestamp()*1000); end=start+86400000
    items=[completed_task('before-start',completed_at=start-1),completed_task('at-start',completed_at=str(start)),completed_task('before-end',completed_at=end-1),completed_task('at-end',completed_at=str(end))]
    result=task_result(items)
    assert result.status=='success' and [r.record_id for r in result.records]==['at-start','before-end']


def test_incomplete_or_title_only_update_is_not_completed_work():
    result=task_result([completed_task(completed_at=0,updated_time='2026-09-25T02:00:00Z')])
    assert result.status=='success' and result.records==[]


@pytest.mark.parametrize('change',[{'completed_at':'not-time'},{'completed_at':-1},{'completed_at':True},{'completed_at':None},{'completed_at':1.5},{'completed_at':'1.5'},{'guid':None},{'guid':''}])
def test_invalid_completion_or_missing_guid_fails_source(change):
    result=task_result([completed_task('good'),completed_task(**change)])
    assert result.status=='failure' and result.error_code=='invalid_payload' and result.records==[]


def test_missing_completion_fails_source_without_exception():
    item=completed_task(); del item['completed_at']
    result=task_result([item])
    assert result.status=='failure' and result.error_code=='invalid_payload'


def test_multiple_assignees_are_projected_once_per_person():
    item=completed_task(members=[{'id':'ou_1','type':'user','role':'assignee'},{'id':'ou_2','type':'user','role':'assignee'},
      {'id':'ou_3','type':'user','role':'follower'},{'id':'app','type':'app','role':'assignee'}])
    def handler(request):
        more='page_token' not in request.url.params
        return httpx.Response(200,json={'code':0,'data':{'items':[item],'has_more':more,**({'page_token':'next'} if more else {})}})
    result=task_result([],handler,['list-1','list-2'])
    assert result.status=='success'
    assert sorted((r.record_id,r.assignee_user_id) for r in result.records)==[('task-1','ou_1'),('task-1','ou_2')]


def test_task_without_assignee_keeps_unmapped_diagnostic():
    result=task_result([completed_task(members=[])])
    assert result.status=='success' and len(result.records)==1 and result.records[0].assignee_user_id is None


@pytest.mark.parametrize('payload',[{'code':0,'data':{}},{'code':0,'data':{'items':{},'has_more':False}},
 {'code':0,'data':{'items':[]}}, {'data':{'items':[],'has_more':False}}, {'code':False,'data':{'items':[],'has_more':False}},
 {'code':0,'data':{'items':[],'has_more':'false'}}])
def test_task_summary_payload_requires_actual_success_and_complete_page(payload):
    result=task_result([],lambda r:httpx.Response(200,json=payload))
    assert result.status=='failure' and result.error_code=='invalid_payload' and result.records==[]


@pytest.mark.parametrize('status',[401,403])
def test_tasklist_auth_denied_is_not_empty_success(status):
    calls=[]
    result=task_result([],lambda r:(calls.append(r),httpx.Response(status))[1])
    assert result.status=='failure' and result.records==[]
    assert len(calls)==(2 if status==401 else 1)


def test_tasklist_has_more_without_token_fails():
    result=task_result([],lambda r:httpx.Response(200,json={'code':0,'data':{'items':[],'has_more':True}}))
    assert result.status=='failure' and result.error_code=='invalid_pagination'


def test_repeated_message_page_token_fails_without_partial_success():
    calls=[]
    def handler(request):
        calls.append(request)
        if len(calls)>2: return httpx.Response(400)
        return httpx.Response(200,json={'code':0,'data':{'items':[{'message_id':'m','content':'日报','create_time':'2026-09-25T02:00:00Z'}],'has_more':True,'page_token':'same'}})
    window=CollectionWindow(datetime(2026,9,25,tzinfo=timezone.utc),datetime(2026,9,26,tzinfo=timezone.utc))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result=collect_messages(client,['chat'],window,[],[],FakeToken(),'https://lark','/messages',sleep=lambda _:None)
    assert result.status=='failure' and result.error_code=='invalid_pagination' and result.records==[]
    assert len(calls)==2


def test_message_has_more_without_token_is_failure():
    window=CollectionWindow(datetime(2026,9,25,tzinfo=timezone.utc),datetime(2026,9,26,tzinfo=timezone.utc))
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'code':0,'data':{'items':[],'has_more':True}}))) as client:
        result=collect_messages(client,['chat'],window,[],[],FakeToken(),'https://lark','/messages',sleep=lambda _:None)
    assert result.status=='failure' and result.error_code=='invalid_pagination'


def test_lark_message_refresh_replays_once_even_when_second_auth_failure_changes_shape():
    token_calls=[]; message_calls=[]
    def handler(request):
        if request.url.path=='/token':
            token_calls.append(request)
            return httpx.Response(200,json={'code':0,'tenant_access_token':'t'+str(len(token_calls))})
        message_calls.append(request)
        return httpx.Response(401) if len(message_calls)==1 else httpx.Response(200,json={'code':99991663})
    window=CollectionWindow(datetime(2026,9,25,tzinfo=timezone.utc),datetime(2026,9,26,tzinfo=timezone.utc))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider=TokenProvider(client,'https://lark','/token','app','secret')
        result=collect_messages(client,['chat'],window,[],[],provider,'https://lark','/messages',sleep=lambda _:None)
    assert result.status=='failure' and result.records==[]
    assert len(message_calls)==2 and len(token_calls)==2


@pytest.mark.parametrize("payload", [
    {"code": 0},
    {"code": 0, "data": {"has_more": False}},
    {"code": 0, "data": {"items": None}},
    {"code": 0, "data": {"items": {}}},
    {"code": 0, "data": {"items": ""}},
    {"code": 0, "data": {"items": [], "has_more": "false"}},
])
@pytest.mark.parametrize("after_first_page", [False, True])
def test_malformed_message_page_cannot_claim_empty_or_complete_success(payload, after_first_page):
    calls = []
    def handler(request):
        calls.append(request)
        if after_first_page and len(calls) == 1:
            return httpx.Response(200, json={"code": 0, "data": {"items": [
                {"message_id": "m", "content": "daily progress", "create_time": "2026-09-25T02:00:00Z"}
            ], "has_more": True, "page_token": "next"}})
        return httpx.Response(200, json=payload)
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = collect_messages(client, ["chat"], window, [], [], FakeToken(), "https://lark", "/messages")
    assert result.status == "failure" and result.error_code == "invalid_payload"
    assert result.records == []
    assert len(calls) == (2 if after_first_page else 1)


def github_detail_result(handler, waits):
    def route(request):
        if request.url.path.endswith('/commits'):
            return httpx.Response(200, json=[{'sha': 'sha', 'url': 'https://api.test/detail', 'commit': {
                'message': 'change', 'author': {'name': 'A', 'date': '2026-09-25T01:00:00Z'}},
                'author': {'login': 'octo'}, 'html_url': 'https://git/sha'}])
        return handler(request)
    window = CollectionWindow(datetime(2026, 9, 25, tzinfo=timezone.utc), datetime(2026, 9, 26, tzinfo=timezone.utc))
    with httpx.Client(transport=httpx.MockTransport(route)) as client:
        return collect_commits(client, ['acme/repo'], window, 'https://api.test', sleep=waits.append)


@pytest.mark.parametrize('recovered', [True, False])
def test_github_detail_rate_limit_uses_reset_retry_without_partial_success(recovered):
    calls, waits = [], []
    def handler(request):
        calls.append(request)
        if recovered and len(calls) == 2:
            return httpx.Response(200, json={'stats': {'additions': 7, 'deletions': 2}, 'files': [{'filename': 'a.py'}]})
        return httpx.Response(403, headers={'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '1'})
    result = github_detail_result(handler, waits)
    assert len(calls) == 2 and waits == [0]
    assert result.attempts == 3
    if recovered:
        assert result.status == 'success' and result.records[0].additions == 7
    else:
        assert result.status == 'failure' and result.error_code == 'http_403' and result.records == []


@pytest.mark.parametrize('headers', [{}, {'X-RateLimit-Remaining': '1', 'X-RateLimit-Reset': '1'},
    {'X-RateLimit-Remaining': '0'}, {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': 'invalid'}])
def test_github_detail_permission_or_unusable_reset_is_not_retried(headers):
    calls, waits = [], []
    result = github_detail_result(lambda request: (calls.append(request), httpx.Response(403, headers=headers))[1], waits)
    assert result.status == 'failure' and result.error_code == 'http_403' and result.records == []
    assert len(calls) == 1 and waits == []


def test_github_detail_pages_count_unique_files_and_keep_commit_statistics():
    calls, waits = [], []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={'stats': {'additions': 9, 'deletions': 4},
                'files': [{'filename': f'file-{i}.py'} for i in range(300)]},
                headers={'Link': '<https://api.test/detail?page=2>; rel="next"'})
        return httpx.Response(200, json={'stats': {'additions': 9, 'deletions': 4},
            'files': [{'filename': 'file-299.py'}, {'filename': 'file-300.py'}]})
    result = github_detail_result(handler, waits)
    assert result.status == 'success' and result.records[0].files_changed == 301
    assert result.records[0].additions == 9 and result.records[0].deletions == 4
    assert len(calls) == 2 and calls[1].url.params['page'] == '2'


@pytest.mark.parametrize('failure', ['http', 'missing_files', 'repeated_link'])
def test_github_incomplete_detail_pages_fail_entire_source(failure):
    calls, waits = [], []
    link = {'Link': '<https://api.test/detail?page=2>; rel="next"'}
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={'stats': {'additions': 1, 'deletions': 0},
                'files': [{'filename': 'a.py'}]}, headers=link)
        if failure == 'http':
            return httpx.Response(503)
        if failure == 'missing_files':
            return httpx.Response(200, json={'stats': {'additions': 1}})
        return httpx.Response(200, json={'stats': {'additions': 1}, 'files': [{'filename': 'b.py'}]}, headers=link)
    result = github_detail_result(handler, waits)
    assert result.status == 'failure' and result.records == []
    assert result.error_code == {'http': 'http_503', 'missing_files': 'invalid_payload', 'repeated_link': 'invalid_pagination'}[failure]
    assert len(calls) == (4 if failure == 'http' else 2)


def test_github_detail_at_upstream_file_cap_does_not_claim_complete_count():
    result = github_detail_result(lambda request: httpx.Response(200, json={
        'stats': {'additions': 3000, 'deletions': 0},
        'files': [{'filename': f'file-{i}.py'} for i in range(3000)]}), [])
    assert result.status == 'failure' and result.error_code == 'details_file_limit'
    assert result.records == []
