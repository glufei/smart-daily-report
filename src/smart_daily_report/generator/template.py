from __future__ import annotations

import html
from datetime import date
from typing import Mapping, Sequence
from urllib.parse import urlparse

from ..shared.models import CollectResultStatus, MemberReport

SECTIONS = (("代码提交", "commits", "github_commits"), ("任务进展", "tasks", "lark_tasks"), ("协作沟通", "messages", "lark_messages"))


def safe_url(url: str | None) -> str | None:
    if not url:
        return None
    return url if urlparse(url).scheme.casefold() in {"http", "https"} else None


def render_markdown(report_date: date, team_name: str, members: Sequence[MemberReport],
                    source_status: Mapping[str, CollectResultStatus]) -> str:
    lines = [f"# {team_name} 日报（{report_date.isoformat()}）", ""]
    for member in members:
        lines.extend((f"## {member.display_name}", ""))
        for title, attr, source in SECTIONS:
            lines.extend((f"### {title}", ""))
            if source_status.get(source, "success") == "failure":
                lines.extend(("数据获取失败", ""))
                continue
            records = getattr(member, attr)
            if not records:
                lines.extend(("今日无记录", ""))
                continue
            for record in records:
                if attr == "commits":
                    label = f"{record.repository}: {record.message}（+{record.additions}/-{record.deletions}，{record.files_changed} 个文件）"
                    url = safe_url(record.url)
                    lines.append(f"- [{label}]({url})" if url else f"- {label}")
                elif attr == "tasks":
                    label = f"{record.title}（{record.status}）"
                    url = safe_url(record.url)
                    lines.append(f"- [{label}]({url})" if url else f"- {label}")
                else:
                    lines.append(f"- {record.content}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(report_date: date, team_name: str, members: Sequence[MemberReport],
                source_status: Mapping[str, CollectResultStatus]) -> str:
    output = [f"<h1>{html.escape(team_name)} 日报（{report_date.isoformat()}）</h1>"]
    for member in members:
        output.append(f"<h2>{html.escape(member.display_name)}</h2>")
        for title, attr, source in SECTIONS:
            output.append(f"<h3>{title}</h3>")
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
