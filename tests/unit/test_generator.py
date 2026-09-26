from datetime import date, datetime, timezone

import pytest

from smart_daily_report.generator.formatter import generate_daily_report
from smart_daily_report.shared.models import MemberReport


def test_three_sections_show_records_empty_and_source_failure(records):
    member = MemberReport("u1", "张三", [records["commit"]], [], [records["message"]], {})
    statuses = {"github_commits": "success", "lark_tasks": "success", "lark_messages": "failure"}
    report = generate_daily_report(date(2026, 9, 25), "team", [member], statuses, datetime.now(timezone.utc))
    assert report.markdown.index("### 代码提交") < report.markdown.index("### 任务进展") < report.markdown.index("### 协作沟通")
    assert "fix bug" in report.markdown and "今日无记录" in report.markdown and "数据获取失败" in report.markdown


def test_html_escapes_untrusted_content(records):
    from dataclasses import replace
    member = MemberReport("u1", "<img>", [replace(records["commit"], message="<script>x</script>", url='javascript:alert(1)')])
    report = generate_daily_report(date(2026, 9, 25), "<team>", [member], {}, datetime.now(timezone.utc))
    assert "&lt;script&gt;" in report.html and "&lt;team&gt;" in report.html
    assert 'href="javascript:alert(1)"' not in report.html


def test_all_failed_sources_cannot_create_report():
    with pytest.raises(ValueError):
        generate_daily_report(date.today(), "team", [], {"github_commits": "failure"}, datetime.now(timezone.utc))
