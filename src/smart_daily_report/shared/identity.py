from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from .models import CommitRecord, MemberConfig, MemberReport, MessageRecord, RunConfig, TaskRecord


def filter_sensitive_messages(records: Sequence[MessageRecord], sensitive_keywords: Sequence[str]) -> list[MessageRecord]:
    blocked = [word.casefold() for word in sensitive_keywords if word]
    return [record for record in records if not any(word in record.content.casefold() for word in blocked)]


def resolve_github_member(config: RunConfig, record: CommitRecord) -> MemberConfig | None:
    if record.author_login:
        return next((member for member in config.members
                     if any(record.author_login.casefold() == login.casefold() for login in member.github_logins)), None)
    if record.author_name:
        return next((member for member in config.members
                     if any(record.author_name.casefold() == name.casefold() for name in member.github_author_names)), None)
    return None


def map_records_to_members(
    config: RunConfig,
    commits: Sequence[CommitRecord],
    tasks: Sequence[TaskRecord],
    messages: Sequence[MessageRecord],
    source_status: dict[str, str] | None = None,
) -> list[MemberReport]:
    lark_map = {user_id.casefold(): member for member in config.members for user_id in member.lark_user_ids}
    grouped: dict[str, dict[str, list]] = defaultdict(lambda: {"commits": [], "tasks": [], "messages": []})
    for record in commits:
        member = resolve_github_member(config, record)
        if member:
            grouped[member.member_id]["commits"].append(record.__class__(**{**record.__dict__, "member_id": member.member_id}))
    for record in tasks:
        member = lark_map.get((record.assignee_user_id or "").casefold())
        if member:
            grouped[member.member_id]["tasks"].append(record.__class__(**{**record.__dict__, "member_id": member.member_id}))
    safe_messages = filter_sensitive_messages(messages, config.sensitive_keywords)
    for record in safe_messages:
        member = lark_map.get((record.sender_user_id or "").casefold())
        if member:
            grouped[member.member_id]["messages"].append(record.__class__(**{**record.__dict__, "member_id": member.member_id}))
    statuses = source_status or {"github_commits": "success", "lark_tasks": "success", "lark_messages": "success"}
    return [MemberReport(member.member_id, member.display_name, **grouped[member.member_id],
                         source_status=dict(statuses), github_username=member.github_logins[0] if member.github_logins else "")
            for member in config.members]
