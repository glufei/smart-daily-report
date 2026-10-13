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


def _string_list(mapping: Mapping, key: str, context: str) -> list[str]:
    value = mapping.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ConfigError(f"{context}.{key} must be a list of non-empty strings")
    return list(value)


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
            github_logins=_string_list(item, "github_logins", f"members[{index}]"),
            lark_user_ids=_string_list(item, "lark_user_ids", f"members[{index}]"),
            github_author_names=_string_list(item, "github_author_names", f"members[{index}]"),
        ))
    smtp_raw = team.get("smtp", {})
    if not isinstance(smtp_raw, dict):
        raise ConfigError("team.smtp must be a mapping")
    holidays = set()
    try:
        holidays = {date.fromisoformat(value) for value in team.get("holidays", [])}
        if smtp_raw:
            recipients = smtp_raw.get("recipients")
            if not isinstance(recipients, list) or not recipients or not all(isinstance(value, str) and value.strip() for value in recipients):
                raise ConfigError("SMTP requires non-empty recipients")
            if any(key in smtp_raw for key in ('username_env', 'password_env')):
                if any(not isinstance(smtp_raw.get(key), str) or not smtp_raw[key].strip()
                       or not _env(smtp_raw, key, env) or not _env(smtp_raw, key, env).strip()
                       for key in ('username_env', 'password_env')):
                    raise ConfigError("SMTP login requires both configured credential variables")
            port = int(smtp_raw.get("port", 587))
            if not 1 <= port <= 65535:
                raise ConfigError("SMTP port must be between 1 and 65535")
            if any(type(smtp_raw.get(key, default)) is not bool
                   for key, default in (("starttls", True), ("use_ssl", False))):
                raise ConfigError("SMTP TLS options must be booleans")
            smtp = SmtpConfig(
                host=_required(smtp_raw, "host", "team.smtp"),
                port=port,
                username=_env(smtp_raw, "username_env", env),
                password=_env(smtp_raw, "password_env", env),
                sender=_required(smtp_raw, "sender", "team.smtp"),
                recipients=list(smtp_raw.get("recipients", [])),
                starttls=bool(smtp_raw.get("starttls", True)),
                use_ssl=bool(smtp_raw.get("use_ssl", False)),
            )
            if smtp.starttls and smtp.use_ssl:
                raise ConfigError("SMTP starttls and use_ssl cannot both be enabled")
        else:
            smtp = SmtpConfig("", 587, None, None, "", [])
        config = RunConfig(
            team_name=_required(team, "name", "team"), timezone=timezone,
            members=members,
            github_repositories=_string_list(team, "github_repositories", "team"),
            lark_project_ids=_string_list(team, "lark_project_ids", "team"),
            lark_chat_ids=_string_list(team, "lark_chat_ids", "team"),
            report_keywords=_string_list(team, "report_keywords", "team"),
            sensitive_keywords=_string_list(team, "sensitive_keywords", "team"),
            holidays=holidays,
            database_path=str(team.get("database_path", "data/reports.sqlite3")),
            github_api_base_url=str(team.get("github_api_base_url", "https://api.github.com")).rstrip("/"),
            lark_api_base_url=str(team.get("lark_api_base_url", "https://open.feishu.cn/open-apis")).rstrip("/"),
            github_token=_env(team, "github_token_env", env),
            lark_app_id=_env(team, "lark_app_id_env", env),
            lark_app_secret=_env(team, "lark_app_secret_env", env),
            lark_webhook=_env(team, "lark_webhook_env", env),
            lark_task_search_path=str(team.get("lark_task_search_path", "/task/v2/tasklists/{tasklist_guid}/tasks")),
            lark_message_path=str(team.get("lark_message_path", "/im/v1/messages")),
            lark_token_path=str(team.get("lark_token_path", "/auth/v3/tenant_access_token/internal")),
            smtp=smtp,
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError("Configuration contains invalid field values") from exc
    if config.lark_project_ids and config.lark_task_search_path != "/task/v2/tasklists/{tasklist_guid}/tasks":
        raise ConfigError("Enabled tasks require the authorized tasklist GET path; migrate the old search configuration")
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
