from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .models import CommitRecord, DailyReport, MemberReport, MessageRecord, TaskRecord


def write_report(db_path: Path, report: DailyReport) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS daily_reports (
                report_date TEXT PRIMARY KEY,
                team_name TEXT NOT NULL,
                markdown TEXT NOT NULL,
                html TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                generated_at TEXT NOT NULL
            )
        """)
        payload = json.dumps({
            "source_status": report.source_status,
            "members": [{
                "member_id": member.member_id,
                "display_name": member.display_name,
                "commits": [record.__dict__ for record in member.commits],
                "tasks": [record.__dict__ for record in member.tasks],
                "messages": [record.__dict__ for record in member.messages],
                "source_status": member.source_status,
                "github_username": member.github_username,
            } for member in report.members],
        }, ensure_ascii=False, default=str)
        connection.execute("""
            INSERT INTO daily_reports(report_date, team_name, markdown, html, payload_json, generated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_date) DO UPDATE SET team_name=excluded.team_name,
              markdown=excluded.markdown, html=excluded.html,
              payload_json=excluded.payload_json, generated_at=excluded.generated_at
        """, (report.report_date.isoformat(), report.team_name, report.markdown, report.html,
              payload, report.generated_at.isoformat()))


def get_report(db_path: Path, report_date: date) -> DailyReport | None:
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM daily_reports WHERE report_date = ?", (report_date.isoformat(),)).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload_json"])
    members = []
    for item in payload["members"]:
        commits = [CommitRecord(**{**record, "committed_at": datetime.fromisoformat(record["committed_at"])}) for record in item["commits"]]
        tasks = [TaskRecord(**{**record, "changed_at": datetime.fromisoformat(record["changed_at"])}) for record in item["tasks"]]
        messages = [MessageRecord(**{**record, "sent_at": datetime.fromisoformat(record["sent_at"])}) for record in item["messages"]]
        members.append(MemberReport(item["member_id"], item["display_name"], commits, tasks, messages,
                                    item.get("source_status", {}),
                                    github_username=item.get("github_username", "")))
    return DailyReport(report_date, row["team_name"], members, payload["source_status"], row["markdown"],
                       row["html"], datetime.fromisoformat(row["generated_at"]))
