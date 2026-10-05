from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Generic, Literal, TypeVar

T = TypeVar("T")
CollectResultStatus = Literal["success", "failure"]


@dataclass(frozen=True)
class CommitRecord:
    record_id: str
    repository: str
    author_login: str | None
    author_name: str | None
    message: str
    committed_at: datetime
    url: str
    member_id: str | None = None
    additions: int = 0
    deletions: int = 0
    files_changed: int = 0

    @property
    def author(self) -> str:
        return self.author_login or self.author_name or ""

    @property
    def timestamp(self) -> datetime:
        return self.committed_at

    @property
    def repo(self) -> str:
        return self.repository


@dataclass(frozen=True)
class TaskRecord:
    record_id: str
    title: str
    status: str
    assignee_user_id: str | None
    changed_at: datetime
    url: str | None = None
    member_id: str | None = None
    status_from: str | None = None
    status_to: str | None = None

    @property
    def assignee(self) -> str:
        return self.assignee_user_id or ""

    @property
    def updated_at(self) -> datetime:
        return self.changed_at


@dataclass(frozen=True)
class MessageRecord:
    record_id: str
    sender_user_id: str | None
    content: str
    sent_at: datetime
    url: str | None = None
    member_id: str | None = None
    chat_name: str = ""

    @property
    def sender(self) -> str:
        return self.sender_user_id or ""

    @property
    def timestamp(self) -> datetime:
        return self.sent_at


@dataclass(frozen=True)
class CollectResult(Generic[T]):
    source: str
    status: CollectResultStatus
    records: list[T] = field(default_factory=list)
    error_code: str | None = None
    message: str | None = None
    attempts: int = 1

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts must be at least 1")
        if self.status == "success" and self.error_code:
            raise ValueError("successful result cannot have an error_code")
        if self.status == "failure" and self.records:
            raise ValueError("failed result cannot contain records")


@dataclass(frozen=True)
class MemberReport:
    member_id: str
    display_name: str
    commits: list[CommitRecord] = field(default_factory=list)
    tasks: list[TaskRecord] = field(default_factory=list)
    messages: list[MessageRecord] = field(default_factory=list)
    source_status: dict[str, CollectResultStatus] = field(default_factory=dict)
    github_username: str = ""

    @property
    def name(self) -> str:
        return self.display_name


@dataclass(frozen=True)
class DailyReport:
    report_date: date
    team_name: str
    members: list[MemberReport]
    source_status: dict[str, CollectResultStatus]
    markdown: str
    html: str
    generated_at: datetime

    @property
    def date(self) -> date:
        return self.report_date


@dataclass(frozen=True)
class MemberConfig:
    member_id: str
    display_name: str
    github_logins: list[str]
    lark_user_ids: list[str]
    github_author_names: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    username: str | None
    password: str | None
    sender: str
    recipients: list[str]
    starttls: bool = True
    use_ssl: bool = False


@dataclass(frozen=True)
class RunConfig:
    team_name: str
    timezone: str
    members: list[MemberConfig]
    github_repositories: list[str]
    lark_project_ids: list[str]
    lark_chat_ids: list[str]
    report_keywords: list[str]
    sensitive_keywords: list[str]
    holidays: set[date]
    database_path: str
    github_api_base_url: str
    lark_api_base_url: str
    github_token: str | None
    lark_app_id: str | None
    lark_app_secret: str | None
    lark_webhook: str | None
    lark_task_search_path: str
    lark_message_path: str
    lark_token_path: str
    smtp: SmtpConfig


@dataclass(frozen=True)
class CollectionWindow:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class DeliveryResult:
    success: bool
    attempts: int
    error_code: str | None = None
    outcome: Literal["accepted", "rejected", "partial_failure", "unknown"] | None = None


@dataclass(frozen=True)
class HealthCheckResult:
    success: bool
    checks: dict[str, bool]
    message: str | None = None


@dataclass(frozen=True)
class RunResult:
    success: bool
    skipped: bool = False
    report: DailyReport | None = None
    deliveries: dict[str, DeliveryResult] = field(default_factory=dict)
    error_code: str | None = None
    sources: dict[str, CollectResult] = field(default_factory=dict)
