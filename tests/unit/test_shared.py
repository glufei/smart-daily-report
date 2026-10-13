import json
import logging
from datetime import date
from pathlib import Path

import pytest

from smart_daily_report.shared.config import load_config, validate_identity_mappings
from smart_daily_report.shared.errors import ConfigError
from smart_daily_report.shared.identity import filter_sensitive_messages, map_records_to_members
from smart_daily_report.shared.logging import JsonFormatter
from smart_daily_report.shared.logging import configure_logging, new_run_id
from smart_daily_report.shared.models import MemberConfig, MessageRecord
from smart_daily_report.shared.storage import get_report, write_report
from smart_daily_report.generator.formatter import generate_daily_report


def test_config_loads_mapping_and_secrets_from_env(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("""team:\n  name: team\n  timezone: Asia/Shanghai\n  holidays: []\n  smtp:\n    host: smtp.test\n    sender: reports@test\n    recipients: [lead@test]\n  github_token_env: GH_TOKEN\nmembers:\n  - member_id: m1\n    display_name: Member\n    github_logins: [octo]\n    lark_user_ids: [ou1]\n""", encoding="utf-8")
    config = load_config(path, {"GH_TOKEN": "secret"})
    assert config.github_token == "secret"
    assert config.members[0].lark_user_ids == ["ou1"]


@pytest.mark.parametrize("section,key", [
    ("team", "github_repositories"), ("team", "lark_project_ids"), ("team", "lark_chat_ids"),
    ("team", "report_keywords"), ("team", "sensitive_keywords"),
    ("member", "github_logins"), ("member", "lark_user_ids"), ("member", "github_author_names"),
])
@pytest.mark.parametrize("value", ["whole-value", [123], [" "]])
def test_config_rejects_malformed_lists_before_collection_or_privacy_filtering(tmp_path, section, key, value):
    raw = {"team": {"name": "team", "timezone": "UTC"}, "members": [{"member_id": "m", "display_name": "Member"}]}
    target = raw["team"] if section == "team" else raw["members"][0]
    target[key] = value
    path = tmp_path / "bad-list.yaml"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ConfigError, match=key):
        load_config(path, {})


def test_config_rejects_invalid_timezone_and_mapping(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("team: {name: team, timezone: Mars/Olympus}\nmembers: [{member_id: m, display_name: M}]", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path, {})


def test_duplicate_external_identity_fails(config):
    config.members.append(MemberConfig("u2", "李四", ["OCTO"], []))
    with pytest.raises(ConfigError):
        validate_identity_mappings(config)


def test_unlinked_github_commit_uses_only_explicit_author_name(config, records):
    from dataclasses import replace

    config.members[0] = replace(config.members[0], github_author_names=["gaochang0339-web"])
    old_commit = replace(records["commit"], author_login=None, author_name="GAOCHANG0339-WEB")
    mapped = map_records_to_members(config, [old_commit], [], [])
    assert [item.record_id for item in mapped[0].commits] == [old_commit.record_id]
    assert mapped[0].commits[0].member_id == config.members[0].member_id

    linked_to_someone_else = replace(old_commit, author_login="different-user")
    assert map_records_to_members(config, [linked_to_someone_else], [], [])[0].commits == []


def test_duplicate_github_author_name_mapping_fails(config):
    from dataclasses import replace

    config.members[0] = replace(config.members[0], github_author_names=["gaochang0339-web"])
    config.members.append(MemberConfig("u2", "李四", [], [], ["GAOCHANG0339-WEB"]))
    with pytest.raises(ConfigError):
        validate_identity_mappings(config)


def test_sensitive_message_is_removed_before_member_grouping(config, records):
    private = MessageRecord("m2", "ou_1", "薪资 100000", records["message"].sent_at)
    assert filter_sensitive_messages([records["message"], private], config.sensitive_keywords) == [records["message"]]
    members = map_records_to_members(config, [], [], [private])
    assert members[0].messages == []


def test_book_model_names_remain_available_as_compatibility_aliases(records, statuses):
    from smart_daily_report.shared.models import MemberReport
    member = MemberReport("u1", "张三", [records["commit"]], [records["task"]], [records["message"]], statuses, "octo")
    report = generate_daily_report(date(2026, 9, 25), "team", [member], statuses, records["commit"].committed_at)
    assert records["commit"].author == "octo" and records["commit"].repo == "acme/repo"
    assert records["commit"].timestamp == records["commit"].committed_at
    assert records["task"].assignee == "ou_1" and records["task"].updated_at == records["task"].changed_at
    assert records["message"].sender == "ou_1" and records["message"].timestamp == records["message"].sent_at
    assert member.name == "张三" and member.github_username == "octo" and report.date == report.report_date


def test_unmapped_identity_is_not_assigned_to_member(config, records):
    from dataclasses import replace
    member = map_records_to_members(config, [replace(records["commit"], author_login="unknown")], [], [])
    assert member[0].commits == []


def test_json_formatter_has_machine_readable_event():
    record = logging.LogRecord("x", logging.INFO, "", 1, "event", (), None)
    record.run_id = "run-1"
    data = json.loads(JsonFormatter().format(record))
    assert data["event"] == "event" and data["run_id"] == "run-1"


def test_configure_logging_emits_json_to_stdout(capsys):
    logger = configure_logging()
    logger.info("hello", extra={"run_id": "r"})
    assert json.loads(capsys.readouterr().out)["event"] == "hello"
    assert len(new_run_id()) == 36


def test_config_rejects_missing_file_and_missing_member(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.yaml", {})
    path = tmp_path / "empty.yaml"
    path.write_text("team: {name: team, timezone: UTC, smtp: {host: smtp, sender: a, recipients: []}}\nmembers: []", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path, {})


def test_config_rejects_duplicate_member_id(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("""team: {name: team, timezone: UTC, smtp: {host: smtp, sender: a, recipients: [lead@test]}}
members:
  - {member_id: m, display_name: M}
  - {member_id: m, display_name: M2}
""", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path, {})


def test_config_rejects_invalid_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("team: [", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path, {})


def test_sqlite_round_trip_and_idempotent_replace(tmp_path, records, statuses):
    from smart_daily_report.shared.models import MemberReport
    report = generate_daily_report(date(2026, 9, 25), "team", [MemberReport("u1", "张三")], statuses,
                                   records["commit"].committed_at)
    path = tmp_path / "daily.sqlite"
    write_report(path, report)
    write_report(path, report)
    saved = get_report(path, report.report_date)
    assert saved.markdown == report.markdown
    assert get_report(path, date(2026, 9, 24)) is None


def test_report_storage_releases_connections_for_windows_file_operations(tmp_path, records, statuses, monkeypatch):
    import sqlite3
    from smart_daily_report.shared.models import MemberReport
    connections = []
    connect = sqlite3.connect
    def capture(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection
    monkeypatch.setattr("smart_daily_report.shared.storage.sqlite3.connect", capture)
    report = generate_daily_report(date(2026, 9, 25), "team", [MemberReport("u1", "Member")], statuses, records["commit"].committed_at)
    path = tmp_path / "reports.sqlite3"
    write_report(path, report)
    assert get_report(path, report.report_date) is not None
    assert len(connections) == 2
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_storage_does_not_store_secret_when_message_filtered(config, records, tmp_path):
    from smart_daily_report.shared.models import MemberReport
    private = MessageRecord("m2", "ou_1", "薪资 secret-marker", records["message"].sent_at)
    safe_members = map_records_to_members(config, [], [], [private])
    report = generate_daily_report(date(2026, 9, 25), "team", safe_members,
                                   {"github_commits": "success", "lark_tasks": "success", "lark_messages": "success"},
                                   records["commit"].committed_at)
    path = tmp_path / "daily.sqlite"
    write_report(path, report)
    assert "secret-marker" not in get_report(path, report.report_date).markdown


def test_smtp_block_absent_disables_email_but_partial_block_is_error(tmp_path):
    path = tmp_path / "config.yaml"
    base = {"team": {"name": "team", "timezone": "UTC"}, "members": [{"member_id": "m", "display_name": "M"}]}
    path.write_text(json.dumps(base), encoding="utf-8")
    try:
        cfg = load_config(path, {})
    except ConfigError:
        cfg = None
    assert cfg is not None, "Generation without SMTP must remain available"
    assert cfg.smtp.host == "" and cfg.smtp.recipients == []
    for partial in ({"host":"smtp.test"}, {"host":"smtp.test","sender":"a@test","recipients":[]}):
        path.write_text(json.dumps({**base,"team":{**base["team"],"smtp":partial}}), encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(path, {})


def test_task_config_migrates_default_and_rejects_explicit_search(tmp_path):
    path=tmp_path/'config.yaml'
    base='team:\n  name: team\n  timezone: Asia/Shanghai\n  lark_project_ids: [list-1]\n{extra}members:\n  - member_id: m\n    display_name: M\n'
    path.write_text(base.format(extra=''),encoding='utf-8')
    assert load_config(path,{}).lark_task_search_path=='/task/v2/tasklists/{tasklist_guid}/tasks'
    path.write_text(base.format(extra='  lark_task_search_path: /task/v2/tasks/search\n'),encoding='utf-8')
    with pytest.raises(ConfigError): load_config(path,{})
    path.write_text(base.replace('[list-1]','[]').format(extra='  lark_task_search_path: /task/v2/tasks/search\n'),encoding='utf-8')
    assert load_config(path,{}).lark_project_ids==[]


@pytest.mark.parametrize('smtp,environ', [
    ({'username_env':'USER'}, {'USER':'someone'}),
    ({'password_env':'PASS'}, {'PASS':'private-marker'}),
    ({'username_env':'USER','password_env':'PASS'}, {}),
    ({'username_env':'USER','password_env':'PASS'}, {'USER':'someone','PASS':'  '}),
    ({'port':0}, {}), ({'port':65536}, {}),
    ({'starttls':'false'}, {}), ({'use_ssl':'true'}, {}),
])
def test_smtp_invalid_login_or_transport_cannot_silently_start(tmp_path,smtp,environ):
    raw={'team':{'name':'team','timezone':'UTC','smtp':{'host':'smtp.test','sender':'a@test','recipients':['b@test'],**smtp}},
         'members':[{'member_id':'m','display_name':'M'}]}
    path=tmp_path/'config.yaml';path.write_text(json.dumps(raw),encoding='utf-8')
    with pytest.raises(ConfigError) as caught:
        load_config(path,environ)
    assert 'private-marker' not in str(caught.value)


def test_smtp_credentials_are_required_only_if_login_is_configured(tmp_path):
    raw={'team':{'name':'team','timezone':'UTC','smtp':{'host':'smtp.test','sender':'a@test','recipients':['b@test'],
         'username_env':'USER','password_env':'PASS'}},'members':[{'member_id':'m','display_name':'M'}]}
    path=tmp_path/'config.yaml';path.write_text(json.dumps(raw),encoding='utf-8')
    config=load_config(path,{'USER':'user','PASS':'private-marker'})
    assert config.smtp.username=='user' and config.smtp.password=='private-marker'
