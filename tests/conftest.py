from datetime import date, datetime, timezone

import pytest

from smart_daily_report.shared.models import (
    CollectResult, CommitRecord, DailyReport, MemberConfig, MemberReport,
    MessageRecord, RunConfig, SmtpConfig, TaskRecord,
)


@pytest.fixture
def config():
    return RunConfig(
        team_name="team", timezone="Asia/Shanghai",
        members=[MemberConfig("u1", "张三", ["octo"], ["ou_1"])],
        github_repositories=[], lark_project_ids=[], lark_chat_ids=[],
        report_keywords=["日报"], sensitive_keywords=["薪资"], holidays=set(),
        database_path="reports.sqlite3", github_api_base_url="https://api.github.com",
        lark_api_base_url="https://open.feishu.cn/open-apis", github_token=None,
        lark_app_id=None, lark_app_secret=None, lark_webhook=None,
        lark_task_search_path="/task/v2/tasklists/{tasklist_guid}/tasks", lark_message_path="/im/v1/messages",
        lark_token_path="/auth/v3/tenant_access_token/internal",
        smtp=SmtpConfig("smtp.test", 587, None, None, "reports@test", ["lead@test"]),
    )


@pytest.fixture
def records():
    at = datetime(2026, 9, 25, 10, tzinfo=timezone.utc)
    return {
        "commit": CommitRecord("sha", "acme/repo", "octo", "Octo", "fix bug", at, "https://example.test/commit"),
        "task": TaskRecord("t1", "Ship", "done", "ou_1", at, None),
        "message": MessageRecord("m1", "ou_1", "日报完成", at),
    }


@pytest.fixture
def statuses():
    return {"github_commits": "success", "lark_tasks": "success", "lark_messages": "success"}
