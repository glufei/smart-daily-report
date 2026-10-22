from __future__ import annotations

import html
from datetime import date, datetime
from typing import Mapping, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from ..shared.models import CollectResultStatus, MemberReport

SUMMARY_LABELS = (("代码提交", "commits", "github_commits"), ("已完成任务", "tasks", "lark_tasks"), ("协作沟通", "messages", "lark_messages"))
CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _format_commit_timestamp(timestamp: datetime) -> str:
    local = timestamp.astimezone(CHINA_TIMEZONE)
    offset = local.strftime("%z")
    return f"{local:%Y-%m-%d %H:%M:%S}（中国标准时间，UTC{offset[:3]}:{offset[3:]}）"


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


def render_markdown(report_date: date, team_name: str, members: Sequence[MemberReport],
                    source_status: Mapping[str, CollectResultStatus]) -> str:
    lines = [f"# 高畅智能日报（{report_date.isoformat()}）", "",
             "本日报由系统自动生成，只展示已采集记录的汇总统计，不包含工作细节。", ""]
    multiple_members = len(members) > 1
    summary_level = "###" if multiple_members else "##"
    for member in members:
        if multiple_members:
            lines.extend((f"## {_markdown_text(member.display_name)}", ""))
        lines.extend((f"{summary_level} 今日概览", ""))
        lines.extend(("仅依据成功采集的记录统计；获取失败的来源数量未知。", ""))
        for label, attr, source in SUMMARY_LABELS:
            lines.append(f"- {label}：{_summary_value(member, attr, source, source_status)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(report_date: date, team_name: str, members: Sequence[MemberReport],
                source_status: Mapping[str, CollectResultStatus], *,
                generated_at: datetime | None = None) -> str:
    multiple_members = len(members) > 1
    body_style = "font-family:Arial,'Microsoft YaHei',sans-serif;font-size:16px;line-height:1.6;color:#243247"
    title_style = "margin:0;font-size:28px;line-height:1.35;color:#17365d"
    section_style = "margin:0;font-size:20px;line-height:1.4;color:#17365d"
    muted_style = "margin:0;color:#667085;font-size:13px;line-height:1.5"
    output = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"></head>',
        f'<body style="{body_style};margin:0;background:#f2f5f9;padding:0">',
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;border-collapse:collapse;background:#f2f5f9">',
        '<tr><td align="center" style="padding:24px 12px">',
        '<table role="presentation" width="860" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:860px;border-collapse:separate;border-spacing:0">',
        '<tr><td style="padding:24px 26px;background:#fff;border:1px solid #dce3ec;border-radius:12px">',
        f'<p style="{muted_style};margin-bottom:6px">高畅智能日报</p>',
        f'<h1 style="{title_style}">报告日期：{report_date.isoformat()}</h1>',
        f'<p style="{muted_style};margin-top:10px">汇总 GitHub 代码活动与飞书协作记录，不展示原始工作细节。</p>',
    ]
    if generated_at:
        output.append(f'<p style="{muted_style};margin-top:6px">生成时间：{_format_commit_timestamp(generated_at)}</p>')
    output.append('</td></tr><tr><td height="14" style="height:14px;font-size:0;line-height:0">&nbsp;</td></tr>')
    for member in members:
        if multiple_members:
            output.extend((
                '<tr><td style="padding:4px 2px 10px">',
                f'<h2 style="margin:0;font-size:21px;line-height:1.4;color:#243247">{html.escape(member.display_name)}</h2>',
                '</td></tr>',
            ))
        output.extend((
            '<tr><td style="padding:20px 22px;background:#fff;border:1px solid #dce3ec;border-radius:12px">',
            f'<h2 style="{section_style};margin-bottom:4px">今日概览</h2>',
            f'<p style="{muted_style};margin-bottom:14px">仅统计成功采集的记录；来源获取失败时数量标记为未知。代码提交来自 GitHub，任务与协作沟通来自飞书。</p>',
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;border-collapse:separate;border-spacing:6px 0"><tr>',
        ))
        for label, attr, source in SUMMARY_LABELS:
            value = _summary_value(member, attr, source, source_status)
            output.append(
                f'<td width="33%" valign="top" style="width:33%;padding:12px 10px;background:#f3f6fa;border:1px solid #e1e7ef;border-radius:8px">'
                f'<p style="{muted_style};margin-bottom:5px">{html.escape(label)}</p>'
                f'<p style="margin:0;font-size:18px;line-height:1.4;font-weight:bold;color:#17365d">{html.escape(value)}</p></td>'
            )
        output.append('</tr></table></td></tr><tr><td height="14" style="height:14px;font-size:0;line-height:0">&nbsp;</td></tr>')

    output.append('</table></td></tr></table></body></html>')
    return "".join(output)
