from __future__ import annotations

from datetime import date
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_validator, model_validator

from ..generator.template import safe_url


class ViewModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, strict=True)


class SourceStatus(ViewModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    github_commits: Literal["success", "failure"]
    lark_tasks: Literal["success", "failure"]
    lark_messages: Literal["success", "failure"]


class LinkedRecordView(ViewModel):
    record_id: str
    url: str | None

    @field_validator("url")
    @classmethod
    def allow_web_links(cls, value: str | None) -> str | None:
        return safe_url(value)


class CommitView(LinkedRecordView):
    repository: str
    message: str
    committed_at: AwareDatetime
    additions: int
    deletions: int
    files_changed: int


class TaskView(LinkedRecordView):
    title: str
    status: str
    status_from: str | None
    status_to: str | None
    changed_at: AwareDatetime


class MessageView(LinkedRecordView):
    content: str
    sent_at: AwareDatetime
    chat_name: str


class MemberView(ViewModel):
    member_id: str
    display_name: str
    commits: list[CommitView]
    tasks: list[TaskView]
    messages: list[MessageView]


class ReportView(ViewModel):
    report_date: date
    team_name: str
    generated_at: AwareDatetime
    source_status: SourceStatus
    members: list[MemberView]

    @model_validator(mode="after")
    def validate_report_states(self) -> Self:
        sources = self.source_status.model_dump()
        if all(status == "failure" for status in sources.values()):
            raise ValueError("A report requires a successful source")
        if len({member.member_id for member in self.members}) != len(self.members):
            raise ValueError("Member IDs must be unique")
        for member in self.members:
            for source, field in (("github_commits", "commits"), ("lark_tasks", "tasks"),
                                  ("lark_messages", "messages")):
                if sources[source] == "failure" and getattr(member, field):
                    raise ValueError("Failed sources cannot contain records")
        return self


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
