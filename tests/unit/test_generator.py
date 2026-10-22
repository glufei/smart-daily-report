from dataclasses import replace
from datetime import date, datetime, timezone
from html.parser import HTMLParser

import markdown
import pytest

from smart_daily_report.generator.formatter import generate_daily_report
from smart_daily_report.shared.models import MemberReport


STATUSES = {"github_commits": "success", "lark_tasks": "success", "lark_messages": "success"}
DAY = date(2026, 9, 25)
GENERATED = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)


def make_report(members, statuses=STATUSES):
    return generate_daily_report(DAY, "team", members, statuses, GENERATED)


def test_shared_report_outputs_do_not_disclose_source_details(records):
    secret = "classified-project-marker"
    member = MemberReport("u1", "张三", [replace(records["commit"], message=secret, repository=secret,
                                               url="https://example.test/private-commit")],
                          [replace(records["task"], title=secret, url="https://example.test/private-task")],
                          [replace(records["message"], content=secret, chat_name=secret)])
    report = make_report([member])

    for output in (report.markdown, report.html):
        assert all(label in output for label in ("代码提交", "已完成任务", "协作沟通", "1 条"))
        assert all(marker not in output for marker in (secret, "private-commit", "private-task"))
    assert report.members[0].commits[0].message == secret


def test_summary_preserves_zero_vs_unknown_and_date(records):
    member = MemberReport("u1", "张三", [records["commit"]])
    report = make_report([member], {"github_commits": "success", "lark_tasks": "failure", "lark_messages": "success"})
    assert report.markdown.startswith("# 高畅智能日报（2026-09-25）")
    assert "代码提交：1 条" in report.markdown
    assert "已完成任务：获取失败，数量未知" in report.markdown
    assert "协作沟通：0 条" in report.markdown
    assert "已完成任务：0 条" not in report.markdown
    assert "获取失败，数量未知" in report.html


def test_email_has_clear_overview_and_china_generation_time_without_record_metadata(records):
    report = make_report([MemberReport("u1", "张三", [records["commit"]], [records["task"]], [records["message"]])])
    assert '<table role="presentation"' in report.html
    assert 'width="860"' in report.html and 'max-width:860px' in report.html
    assert "今日概览" in report.html
    assert "生成时间：2026-09-25 18:00:00（中国标准时间，UTC+08:00）" in report.html
    assert report.html.count("1 条") == 3
    assert all(value not in report.html for value in ("fix bug", "Ship", "日报完成", "acme/repo",
                                                      "href=", "个文件"))


def test_multi_member_identity_is_safe_but_single_member_is_not_repeated(records):
    name = "<img> [链接](https://injected.invalid)"
    member = MemberReport("u1", name, [replace(records["commit"], message="<script>x</script>")])
    single = make_report([member])
    assert f"## {name}" not in single.markdown
    assert name not in single.html
    assert "<script>" not in single.html
    multi = make_report([member, MemberReport("u2", "李四")])
    assert "&lt;img&gt;" in multi.html and "&lt;script&gt;" not in multi.html
    parsed = HTMLParser()
    parsed.feed(markdown.markdown(multi.markdown))
    assert "https://injected.invalid" not in multi.markdown
    assert "href=" not in markdown.markdown(multi.markdown)


def test_generated_markdown_contains_only_one_summary_section_per_member(records):
    report = make_report([MemberReport("u1", "张三", [records["commit"]]),
                          MemberReport("u2", "李四", messages=[records["message"]])])
    rendered = markdown.markdown(report.markdown)
    assert rendered.count("<h2>") == 2
    assert rendered.count("<h3>今日概览</h3>") == 2
    assert "提交明细" not in rendered and "工作消息" not in rendered
    assert "代码提交：1 条" in report.markdown
    assert "协作沟通：1 条" in report.markdown


def test_all_failed_sources_cannot_create_report():
    with pytest.raises(ValueError):
        make_report([], {"github_commits": "failure"})
