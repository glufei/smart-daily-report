"""Serve only synthetic history; fail loudly if viewing triggers production work."""
import argparse
from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sqlite3

import uvicorn

from smart_daily_report.shared.identity import filter_sensitive_messages
from smart_daily_report.shared.logging import JsonFormatter, configure_logging
from smart_daily_report.shared.models import CommitRecord, DailyReport, MemberReport, MessageRecord, TaskRecord
from smart_daily_report.shared.storage import write_report
from smart_daily_report.web.app import create_app

parser = argparse.ArgumentParser()
parser.add_argument("--port", type=int, required=True)
parser.add_argument("--broken", action="store_true")
args = parser.parse_args()
directory = Path(__file__).resolve().parents[2] / ".runtime" / "e2e"
directory.mkdir(parents=True, exist_ok=True)
database = directory / ("broken.sqlite3" if args.broken else "history.sqlite3")
if database.exists():
    database.unlink()  # Fixed path in isolated fixture directory; never a user-supplied DB.

if args.broken:
    database.write_bytes(b"not-a-database-private-path-marker")
else:
    at = datetime(2026, 9, 25, 10, tzinfo=timezone.utc)
    sensitive = MessageRecord("filtered", "external-private-id", "sensitive-message-marker", at)
    messages = filter_sensitive_messages([sensitive, MessageRecord("m1", "external-private-id", "日报：已完成只读页面原型", at, None, chat_name="示例研发群")], ["sensitive-message-marker"])
    member = MemberReport("member-a", "示例成员甲",
        [CommitRecord("c1", "example/report", "external-private-id", None, "修正日期选择交互", at, "https://example.com/commit", additions=10, deletions=2, files_changed=1)],
        [TaskRecord("t1", "完成页面契约评审", "已完成", "external-private-id", at, status_from="进行中", status_to="已完成")], messages)
    report = DailyReport(date(2026, 9, 25), "示例研发团队", [member, MemberReport("member-b", "示例成员乙")],
        {"github_commits": "success", "lark_tasks": "success", "lark_messages": "success"},
        "private-markdown-marker", "private-html-marker", at)
    write_report(database, report)
    write_report(database, replace(report, report_date=date(2026, 9, 26),
        source_status={**report.source_status, "lark_tasks": "failure"}, members=[replace(member, tasks=[]), report.members[1]]))
    write_report(database, replace(report, report_date=date(2026, 9, 28)))
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE daily_reports SET payload_json = ? WHERE report_date = ?", ('{"private-payload-marker":', "2026-09-28"))
    attack = '<img src=x onerror="window.attack=1">'
    write_report(database, replace(report, report_date=date(2026, 9, 29), team_name="长团队" + "X" * 120,
        members=[replace(member, commits=[replace(member.commits[0], repository="long/" + "X" * 200, message=attack, url="javascript:alert(1)")],
            tasks=[replace(member.tasks[0], url="data:text/html,attack")], messages=[replace(messages[0], content="长消息" + "X" * 300)])]))
    write_report(database, replace(report, report_date=date(2026, 9, 30), members=[MemberReport("member-a", "示例成员甲"), report.members[1]]))

baseline = {"database": database.name, "sha256": hashlib.sha256(database.read_bytes()).hexdigest()}
(directory / f"baseline-{args.port}.json").write_text(json.dumps(baseline), encoding="utf-8")

logger = configure_logging()
handler = logging.FileHandler(directory / f"api-{args.port}.log", mode="w", encoding="utf-8")
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)

def forbidden(*_args, **_kwargs):
    (directory / "forbidden-call.txt").write_text("Viewing invoked generation/collection/write/notification", encoding="utf-8")
    raise AssertionError("Read-only workflow invoked a forbidden action")

from smart_daily_report import main as pipeline
from smart_daily_report.collector import github, lark
from smart_daily_report.generator import formatter
from smart_daily_report.notifier import email, lark_bot
from smart_daily_report.shared import storage
for module, name in ((pipeline, "run_report"), (storage, "write_report"), (github, "collect_commits"),
    (lark, "collect_tasks"), (lark, "collect_messages"), (formatter, "generate_daily_report"),
    (email, "send_email"), (lark_bot, "send_lark_message")):
    setattr(module, name, forbidden)

uvicorn.run(create_app(database), host="127.0.0.1", port=args.port, access_log=False, log_level="warning")
