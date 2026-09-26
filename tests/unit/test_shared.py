import json
import logging
from datetime import date
from pathlib import Path

import pytest

from smart_daily_report.shared.calendar import is_workday
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


def test_workday_skips_weekends_and_holidays():
    assert not is_workday(date(2026, 9, 26), set())
    assert not is_workday(date(2026, 9, 25), {date(2026, 9, 25)})
    assert is_workday(date(2026, 9, 25), set())


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
    path.write_text("""team: {name: team, timezone: UTC, smtp: {host: smtp, sender: a, recipients: []}}
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
