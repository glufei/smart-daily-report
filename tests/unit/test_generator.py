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


def test_member_summary_counts_records_before_preserving_source_details(records):
    from html.parser import HTMLParser

    class TextContent(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    member = MemberReport("u1", "张三", [records["commit"]], [records["task"]], [records["message"]])
    report = generate_daily_report(date(2026, 9, 25), "team", [member], {
        "github_commits": "success", "lark_tasks": "success", "lark_messages": "success",
    }, datetime.now(timezone.utc))
    expected = ("代码提交：1 条", "已完成任务：1 条", "协作沟通：1 条")

    assert report.markdown.index("### 今日总结") < report.markdown.index("### 代码提交")
    assert all(line in report.markdown for line in expected)
    assert "fix bug" in report.markdown
    assert "Ship（done）" in report.markdown
    assert "日报完成" in report.markdown

    parsed = TextContent()
    parsed.feed(report.html)
    html_text = "".join(parsed.parts)
    assert html_text.index("今日总结") < html_text.index("代码提交")
    assert all(line in html_text for line in expected)
    assert "acme/repo: fix bug" in html_text and "Ship（done）" in html_text and "日报完成" in html_text


def test_member_summary_distinguishes_zero_records_from_failed_source():
    from html.parser import HTMLParser

    class TextContent(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

    member = MemberReport("u1", "张三")
    report = generate_daily_report(date(2026, 9, 25), "team", [member], {
        "github_commits": "failure", "lark_tasks": "success", "lark_messages": "success",
    }, datetime.now(timezone.utc))
    failure_count = "代码提交：获取失败，数量未知"
    zero_counts = ("已完成任务：0 条", "协作沟通：0 条")

    assert failure_count in report.markdown
    assert all(line in report.markdown for line in zero_counts)
    assert "代码提交：0 条" not in report.markdown

    parsed = TextContent()
    parsed.feed(report.html)
    html_text = "".join(parsed.parts)
    assert failure_count in html_text
    assert all(line in html_text for line in zero_counts)
    assert "代码提交：0 条" not in html_text


def test_html_escapes_untrusted_content(records):
    from dataclasses import replace
    member = MemberReport("u1", "<img>", [replace(records["commit"], message="<script>x</script>", url='javascript:alert(1)')])
    report = generate_daily_report(date(2026, 9, 25), "<team>", [member], {}, datetime.now(timezone.utc))
    assert "&lt;script&gt;" in report.html and "&lt;team&gt;" in report.html
    assert 'href="javascript:alert(1)"' not in report.html


def test_all_failed_sources_cannot_create_report():
    with pytest.raises(ValueError):
        generate_daily_report(date.today(), "team", [], {"github_commits": "failure"}, datetime.now(timezone.utc))


def test_markdown_external_text_is_literal_without_extra_links_or_structure(records):
    from dataclasses import replace
    from html.parser import HTMLParser
    import markdown
    class Parsed(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags, self.hrefs, self.text = [], [], []
        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)
            self.hrefs.extend(value for name, value in attrs if name == 'href')
        def handle_data(self, data):
            self.text.append(data)
    text = '[核对](https://injected.invalid) **bold** <at id=all></at> &amp;\n# injected heading'
    member = MemberReport('u1', text, [replace(records['commit'], message=text)],
        [replace(records['task'], title=text, url='https://example.test/task')],
        [replace(records['message'], content=text)])
    report = generate_daily_report(date(2026, 9, 25), text, [member], {}, datetime.now(timezone.utc))
    rendered = Parsed()
    rendered.feed(markdown.markdown(report.markdown))
    assert rendered.tags.count('h1') == 1 and rendered.tags.count('h2') == 1 and rendered.tags.count('h3') == 4
    assert rendered.hrefs == ['https://example.test/commit', 'https://example.test/task']
    assert not any(tag in rendered.tags for tag in ['strong', 'em', 'at', 'img'])
    assert ''.join(rendered.text).count(text) == 5
    assert report.members[0].messages[0].content == text


def test_markdown_link_destination_cannot_break_out_into_an_extra_link(records):
    from dataclasses import replace
    from html.parser import HTMLParser
    import markdown
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.hrefs = []
        def handle_starttag(self, tag, attrs):
            self.hrefs.extend(value for name, value in attrs if tag == 'a' and name == 'href')
    member = MemberReport('u1', 'A', [replace(records['commit'], url='https://example.test/path)[injected](https://injected.invalid)')])
    report = generate_daily_report(date(2026, 9, 25), 'team', [member], {}, datetime.now(timezone.utc))
    rendered = Links()
    rendered.feed(markdown.markdown(report.markdown))
    assert rendered.hrefs == ['https://example.test/path%29%5Binjected%5D%28https://injected.invalid%29']
