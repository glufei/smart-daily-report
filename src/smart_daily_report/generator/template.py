from __future__ import annotations

import html
from datetime import date
from typing import Mapping, Sequence
from urllib.parse import quote, urlparse

from ..shared.models import CollectResultStatus, MemberReport

SUMMARY_LABELS = (("代码提交", "commits", "github_commits"), ("已完成任务", "tasks", "lark_tasks"), ("协作沟通", "messages", "lark_messages"))
SOURCE_GROUPS = (
    ("GitHub｜代码提交", (("提交明细", "commits", "github_commits"),)),
    ("飞书｜任务与工作消息", (("任务进展", "tasks", "lark_tasks"), ("工作消息", "messages", "lark_messages"))),
)


def _summary_value(member: MemberReport, attr: str, source: str,
                   source_status: Mapping[str, CollectResultStatus]) -> str:
    if source_status.get(source, "success") == "failure":
        return "获取失败，数量未知"
    return f"{len(getattr(member, attr))} 条"


def safe_url(url: str | None) -> str | None:
    if not url:
        return None
    return url if urlparse(url).scheme.casefold() in {"http", "https"} else None


def _markdown_text(text: str) -> str:
    # Entity references remain literal text rather than Markdown/card controls.
    controls = "\\`*_{}[]()<>#+-.!|~:&\n\r"
    return text.translate({ord(char): f"&#{ord(char)};" for char in controls})


def _markdown_url(url: str | None) -> str | None:
    allowed = safe_url(url)
    return quote(allowed, safe=":/?#@!$&'*+,;=%._~-") if allowed else None


def render_markdown(report_date: date, team_name: str, members: Sequence[MemberReport],
                    source_status: Mapping[str, CollectResultStatus]) -> str:
    lines = [f"# {_markdown_text(team_name)} 日报（{report_date.isoformat()}）", "",
             "本日报由系统自动生成，内容依据已配置并成功采集的数据。", ""]
    for member in members:
        lines.extend((f"## {_markdown_text(member.display_name)}", ""))
        lines.extend(("### 今日总结", ""))
        lines.extend(("系统自动统计：仅依据下方成功采集的记录，不作人工编辑或 AI 推断。", ""))
        for label, attr, source in SUMMARY_LABELS:
            lines.append(f"- {label}：{_summary_value(member, attr, source, source_status)}")
        lines.append("")
        for group, sections in SOURCE_GROUPS:
            lines.extend((f"### {_markdown_text(group)}", ""))
            for title, attr, source in sections:
                lines.extend((f"#### {title}", ""))
                if source_status.get(source, "success") == "failure":
                    lines.extend(("数据获取失败", ""))
                    continue
                records = getattr(member, attr)
                if not records:
                    lines.extend(("今日无记录", ""))
                    continue
                for record in records:
                    if attr == "commits":
                        label = _markdown_text(f"{record.repository}: {record.message}（+{record.additions}/-{record.deletions}，{record.files_changed} 个文件）")
                        url = _markdown_url(record.url)
                        lines.append(f"- [{label}]({url})" if url else f"- {label}")
                    elif attr == "tasks":
                        label = _markdown_text(f"{record.title}（{record.status}）")
                        url = _markdown_url(record.url)
                        lines.append(f"- [{label}]({url})" if url else f"- {label}")
                    else:
                        lines.append(f"- {_markdown_text(record.content)}")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(report_date: date, team_name: str, members: Sequence[MemberReport],
                source_status: Mapping[str, CollectResultStatus]) -> str:
    output = [f"<h1>{html.escape(team_name)} 日报（{report_date.isoformat()}）</h1>",
              "<p>本日报由系统自动生成，内容依据已配置并成功采集的数据。</p>"]
    for member in members:
        output.append(f"<h2>{html.escape(member.display_name)}</h2>")
        output.append("<h3>今日总结</h3><p>系统自动统计：仅依据下方成功采集的记录，不作人工编辑或 AI 推断。</p><ul>")
        for label, attr, source in SUMMARY_LABELS:
            value = f"{label}：{_summary_value(member, attr, source, source_status)}"
            output.append(f"<li>{html.escape(value)}</li>")
        output.append("</ul>")
        for group, sections in SOURCE_GROUPS:
            output.append(f"<h3>{html.escape(group)}</h3>")
            for title, attr, source in sections:
                output.append(f"<h4>{html.escape(title)}</h4>")
                if source_status.get(source, "success") == "failure":
                    output.append("<p>数据获取失败</p>")
                    continue
                records = getattr(member, attr)
                if not records:
                    output.append("<p>今日无记录</p>")
                    continue
                output.append("<ul>")
                for record in records:
                    if attr == "commits":
                        text = f"{record.repository}: {record.message}（+{record.additions}/-{record.deletions}，{record.files_changed} 个文件）"
                        url = safe_url(record.url)
                    elif attr == "tasks":
                        text, url = f"{record.title}（{record.status}）", safe_url(record.url)
                    else:
                        text, url = record.content, None
                    escaped = html.escape(text)
                    output.append(f'<li><a href="{html.escape(url, quote=True)}">{escaped}</a></li>' if url else f"<li>{escaped}</li>")
                output.append("</ul>")
    return "<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><body>" + "".join(output) + "</body></html>"
