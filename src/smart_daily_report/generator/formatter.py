from __future__ import annotations

from datetime import date, datetime
from typing import Mapping, Sequence

from ..shared.models import CollectResultStatus, DailyReport, MemberReport
from .template import render_html, render_markdown


def generate_daily_report(report_date: date, team_name: str, members: Sequence[MemberReport],
                          source_status: Mapping[str, CollectResultStatus], generated_at: datetime) -> DailyReport:
    if source_status and all(value == "failure" for value in source_status.values()):
        raise ValueError("Cannot generate a report when all data sources failed")
    markdown_text = render_markdown(report_date, team_name, members, source_status)
    html_text = render_html(report_date, team_name, members, source_status, generated_at=generated_at)
    return DailyReport(report_date, team_name, list(members), dict(source_status), markdown_text, html_text, generated_at)
