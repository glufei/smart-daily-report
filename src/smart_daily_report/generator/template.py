from __future__ import annotations

import html
from datetime import date, datetime, timezone
from typing import Mapping, Sequence
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

from ..shared.models import CollectResultStatus, MemberReport

SUMMARY_LABELS = (("代码提交", "commits", "github_commits"), ("已完成任务", "tasks", "lark_tasks"), ("协作沟通", "messages", "lark_messages"))
SOURCE_GROUPS = (
    ("GitHub｜代码提交", (("提交明细", "commits", "github_commits"),)),
    ("飞书｜任务与工作消息", (("任务进展", "tasks", "lark_tasks"), ("工作消息", "messages", "lark_messages"))),
)
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


def _markdown_url(url: str | None) -> str | None:
    allowed = safe_url(url)
    return quote(allowed, safe=":/?#@!$&'*+,;=%._~-") if allowed else None


def render_markdown(report_date: date, team_name: str, members: Sequence[MemberReport],
                    source_status: Mapping[str, CollectResultStatus]) -> str:
    lines = [f"# 高畅智能日报（{report_date.isoformat()}）", "",
             "本日报由系统自动生成，内容依据已配置并成功采集的数据。", ""]
    multiple_members = len(members) > 1
    summary_level = "###" if multiple_members else "##"
    group_level = summary_level
    detail_level = "####" if multiple_members else "###"
    for member in members:
        if multiple_members:
            lines.extend((f"## {_markdown_text(member.display_name)}", ""))
        lines.extend((f"{summary_level} 今日总结", ""))
        lines.extend(("系统自动统计：仅依据下方成功采集的记录，不作人工编辑或 AI 推断。", ""))
        for label, attr, source in SUMMARY_LABELS:
            lines.append(f"- {label}：{_summary_value(member, attr, source, source_status)}")
        lines.append("")
        for group, sections in SOURCE_GROUPS:
            lines.extend(("---", "", f"{group_level} {_markdown_text(group)}", ""))
            for title, attr, source in sections:
                lines.extend((f"{detail_level} {title}", ""))
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
                source_status: Mapping[str, CollectResultStatus], *,
                generated_at: datetime | None = None) -> str:
    multiple_members = len(members) > 1
    body_style = "font-family:Arial,'Microsoft YaHei',sans-serif;font-size:16px;line-height:1.6;color:#243247"
    title_style = "margin:0;font-size:28px;line-height:1.35;color:#17365d"
    section_style = "margin:0;font-size:20px;line-height:1.4;color:#17365d"
    subheading_style = "margin:0;font-size:16px;line-height:1.4;color:#34445a"
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
        f'<p style="{muted_style};margin-top:10px">按成功采集的记录汇总，GitHub 与飞书分区展示。</p>',
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
            f'<p style="{muted_style};margin-bottom:14px">仅统计成功采集的记录；来源获取失败时数量标记为未知。</p>',
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

        for group, sections in SOURCE_GROUPS:
            github_group = group.startswith("GitHub")
            group_bg, group_border = ("#eaf1fb", "#4d77ad") if github_group else ("#eaf5f1", "#4d8b72")
            if github_group:
                attr, source = sections[0][1], sections[0][2]
                group_count = _summary_value(member, attr, source, source_status)
                heading = f'{group}（{group_count}）'
                output.extend((
                    '<tr><td style="padding:20px 22px;background:#fff;border:1px solid #dce3ec;border-left:4px solid #4d77ad;border-radius:12px">',
                    f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;border-collapse:collapse"><tr><td style="padding:12px 14px;background:{group_bg};border-left:4px solid {group_border};border-radius:6px">',
                    f'<h2 style="{section_style}">{html.escape(heading)}</h2></td></tr></table>',
                ))
                if source_status.get(source, "success") == "failure":
                    output.append('<p style="margin:14px 0 0;padding:12px 14px;background:#fdf0ed;border:1px solid #e6aaa7;border-radius:6px;color:#9a3431">数据获取失败，数量未知</p>')
                elif not member.commits:
                    output.append(f'<p style="{muted_style};margin-top:14px;padding:12px 14px;background:#f7f8fa;border-radius:6px">今日无记录</p>')
                else:
                    for record in member.commits:
                        timestamp = _format_commit_timestamp(record.committed_at)
                        title = html.escape(record.message)
                        url = safe_url(record.url)
                        title_html = f'<a href="{html.escape(url, quote=True)}" style="color:#145dbf;text-decoration:none"><strong>{title}</strong></a>' if url else f'<strong>{title}</strong>'
                        metadata = f'{html.escape(record.repository)} · {timestamp} · +{record.additions} / −{record.deletions} · {record.files_changed} 个文件'
                        output.append(
                            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;margin-top:10px;border-collapse:collapse;background:#fbfcfe;border:1px solid #e1e7ef;border-radius:7px">'
                            f'<tr><td style="padding:12px 14px 4px;font-size:17px;line-height:1.5;color:#243247">{title_html}</td></tr>'
                            f'<tr><td style="padding:0 14px 12px;font-size:13px;line-height:1.5;color:#667085">{metadata}</td></tr></table>'
                        )
                output.extend(('</td></tr><tr><td height="14" style="height:14px;font-size:0;line-height:0">&nbsp;</td></tr>'))
                continue

            output.extend((
                '<tr><td style="padding:20px 22px;background:#fff;border:1px solid #dce3ec;border-left:4px solid #4d8b72;border-radius:12px">',
                f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;border-collapse:collapse"><tr><td style="padding:12px 14px;background:{group_bg};border-left:4px solid {group_border};border-radius:6px">',
                f'<h2 style="{section_style}">{html.escape(group)}</h2></td></tr></table>',
            ))
            for title, attr, source in sections:
                records = getattr(member, attr)
                value = _summary_value(member, attr, source, source_status)
                output.append(
                    f'<h3 style="{subheading_style};margin:16px 0 8px">{html.escape(title)} · {html.escape(value)}</h3>'
                )
                if source_status.get(source, "success") == "failure":
                    output.append('<p style="margin:0;padding:12px 14px;background:#fdf0ed;border:1px solid #e6aaa7;border-radius:6px;color:#9a3431">数据获取失败，数量未知</p>')
                    continue
                if not records:
                    output.append(f'<p style="{muted_style};margin:0;padding:10px 14px;background:#f7f8fa;border-radius:6px">今日无记录</p>')
                    continue
                for record in records:
                    if attr == "tasks":
                        timestamp = record.changed_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                        text, url = record.title, safe_url(record.url)
                        metadata = f'状态：{record.status} · {timestamp}'
                    else:
                        timestamp = record.sent_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                        text, url = record.content, None
                        metadata = f'时间：{timestamp}'
                        if record.chat_name:
                            metadata = f'{html.escape(record.chat_name)} · {metadata}'
                    escaped = html.escape(text)
                    title_html = f'<a href="{html.escape(url, quote=True)}" style="color:#145dbf;text-decoration:none"><strong>{escaped}</strong></a>' if url else f'<strong>{escaped}</strong>'
                    output.append(
                        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;margin-top:8px;border-collapse:collapse;background:#fbfcfe;border:1px solid #e1e7ef;border-radius:7px">'
                        f'<tr><td style="padding:11px 14px 3px;font-size:16px;line-height:1.5;color:#243247">{title_html}</td></tr>'
                        f'<tr><td style="padding:0 14px 10px;font-size:13px;line-height:1.5;color:#667085">{html.escape(metadata)}</td></tr></table>'
                    )
            output.extend(('</td></tr><tr><td height="14" style="height:14px;font-size:0;line-height:0">&nbsp;</td></tr>'))

    output.append('</table></td></tr></table></body></html>')
    return "".join(output)
