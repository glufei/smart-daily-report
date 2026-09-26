from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .errors import ConfigError
from .models import MemberConfig, RunConfig, SmtpConfig


def _required(mapping: Mapping, key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Missing required configuration: {context}.{key}")
    return value.strip()


def _env(mapping: Mapping, key: str, environ: Mapping[str, str]) -> str | None:
    name = mapping.get(key)
    return environ.get(name) if isinstance(name, str) and name else None


def load_config(path: Path, environ: Mapping[str, str] | None = None) -> RunConfig:
    env = os.environ if environ is None else environ
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Unable to read configuration: {path}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("team"), dict):
        raise ConfigError("Configuration must contain a team mapping")
    team = raw["team"]
    members_raw = raw.get("members")
    if not isinstance(members_raw, list) or not members_raw:
        raise ConfigError("Configuration must contain at least one member")
    try:
        timezone = _required(team, "timezone", "team")
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ConfigError(f"Unknown timezone: {timezone}") from exc
    members = []
    for index, item in enumerate(members_raw):
        if not isinstance(item, dict):
            raise ConfigError(f"members[{index}] must be a mapping")
        members.append(MemberConfig(
            member_id=_required(item, "member_id", f"members[{index}]"),
            display_name=_required(item, "display_name", f"members[{index}]"),
            github_logins=list(item.get("github_logins", [])),
            lark_user_ids=list(item.get("lark_user_ids", [])),
            github_author_names=list(item.get("github_author_names", [])),
        ))
    smtp_raw = team.get("smtp", {})
    if not isinstance(smtp_raw, dict):
        raise ConfigError("team.smtp must be a mapping")
    holidays = set()
    try:
        holidays = {date.fromisoformat(value) for value in team.get("holidays", [])}
        smtp = SmtpConfig(
            host=_required(smtp_raw, "host", "team.smtp"),
            port=int(smtp_raw.get("port", 587)),
            username=_env(smtp_raw, "username_env", env),
            password=_env(smtp_raw, "password_env", env),
            sender=_required(smtp_raw, "sender", "team.smtp"),
            recipients=list(smtp_raw.get("recipients", [])),
            starttls=bool(smtp_raw.get("starttls", True)),
            use_ssl=bool(smtp_raw.get("use_ssl", False)),
        )
        if smtp.starttls and smtp.use_ssl:
            raise ConfigError("SMTP starttls and use_ssl cannot both be enabled")
        config = RunConfig(
            team_name=_required(team, "name", "team"), timezone=timezone,
            members=members,
            github_repositories=list(team.get("github_repositories", [])),
            lark_project_ids=list(team.get("lark_project_ids", [])),
            lark_chat_ids=list(team.get("lark_chat_ids", [])),
            report_keywords=list(team.get("report_keywords", [])),
            sensitive_keywords=list(team.get("sensitive_keywords", [])),
            holidays=holidays,
            database_path=str(team.get("database_path", "data/reports.sqlite3")),
            github_api_base_url=str(team.get("github_api_base_url", "https://api.github.com")).rstrip("/"),
            lark_api_base_url=str(team.get("lark_api_base_url", "https://open.feishu.cn/open-apis")).rstrip("/"),
            github_token=_env(team, "github_token_env", env),
            lark_app_id=_env(team, "lark_app_id_env", env),
            lark_app_secret=_env(team, "lark_app_secret_env", env),
            lark_webhook=_env(team, "lark_webhook_env", env),
            lark_task_search_path=str(team.get("lark_task_search_path", "/task/v2/tasks/search")),
            lark_message_path=str(team.get("lark_message_path", "/im/v1/messages")),
            lark_token_path=str(team.get("lark_token_path", "/auth/v3/tenant_access_token/internal")),
            smtp=smtp,
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError("Configuration contains invalid field values") from exc
    validate_identity_mappings(config)
    return config


def validate_identity_mappings(config: RunConfig) -> None:
    member_ids: set[str] = set()
    accounts: set[tuple[str, str]] = set()
    for member in config.members:
        if member.member_id in member_ids:
            raise ConfigError(f"Duplicate member_id: {member.member_id}")
        member_ids.add(member.member_id)
        for kind, values in (("github", member.github_logins), ("lark", member.lark_user_ids),
                             ("github_author_name", member.github_author_names)):
            for value in values:
                key = (kind, value.casefold())
                if key in accounts:
                    raise ConfigError(f"Duplicate {kind} identity mapping")
                accounts.add(key)
