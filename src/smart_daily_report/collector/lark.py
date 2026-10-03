from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Sequence
from urllib.parse import quote

import httpx

from ..shared.http import TokenProvider, request_with_retry
from ..shared.models import CollectResult, CollectionWindow, MessageRecord, TaskRecord


def _dt(value) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 10**12 else value, timezone.utc)
    text = str(value)
    if text.isdigit():
        number = int(text)
        return datetime.fromtimestamp(number / 1000 if number > 10**12 else number, timezone.utc)
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _data_items(payload: dict) -> tuple[list[dict], str | None]:
    data = payload["data"]
    items = data["items"]
    if not isinstance(items, list) or "has_more" in data and type(data["has_more"]) is not bool:
        raise ValueError("Invalid message page")
    return items, data.get("page_token")


def _get_lark(client, provider, base_url, path, sleep=None, params=None):
    attempts = 0
    refreshed = False
    while True:
        try:
            token = provider.get()
        except Exception:
            return None, attempts + 1, "token_refresh_failed"
        request_args = {"params": params, "headers": {"Authorization": f"Bearer {token}"}, "timeout": 10}
        response, used, error = request_with_retry(client, "GET", base_url.rstrip("/") + "/" + path.lstrip("/"), **request_args) if sleep is None else request_with_retry(client, "GET", base_url.rstrip("/") + "/" + path.lstrip("/"), sleep=sleep, **request_args)
        attempts += used
        if response is not None and response.status_code in (401, 99991663) and not refreshed:
            refreshed = True
            try:
                provider.get(refresh=True)
            except Exception:
                return None, attempts + 1, "token_refresh_failed"
            continue
        if error or response is None or response.is_error:
            return None, attempts, error or f"http_{response.status_code if response else 'unknown'}"
        try:
            payload = response.json()
            if not isinstance(payload, dict) or type(payload.get("code")) is not int:
                return None, attempts, "invalid_payload"
            if payload["code"] != 0:
                if payload.get("code") in (99991663, 99991664) and not refreshed:
                    refreshed = True
                    try:
                        provider.get(refresh=True)
                    except Exception:
                        return None, attempts + 1, "token_refresh_failed"
                    continue
                return None, attempts, f"lark_{payload.get('code')}"
            return payload, attempts, None
        except (ValueError, AttributeError):
            return None, attempts, "invalid_payload"


def collect_tasks(client: httpx.Client, project_ids: Sequence[str], window: CollectionWindow,
                  token_provider: TokenProvider, api_base_url: str, path: str, sleep=None) -> CollectResult[TaskRecord]:
    records: list[TaskRecord] = []
    attempts_total = 0
    seen_records: set[tuple[str, str | None]] = set()
    for project_id in project_ids:
        token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            params = {"page_size": "100", "completed": "true", "user_id_type": "open_id"}
            if token:
                params["page_token"] = token
            payload, attempts, error = _get_lark(client, token_provider, api_base_url, path.replace("{tasklist_guid}", quote(project_id, safe="")), sleep, params)
            attempts_total += attempts
            if error:
                return CollectResult("lark_tasks", "failure", error_code=error, message="Feishu task collection failed", attempts=max(1, attempts_total))
            try:
                data = payload["data"]
                items = data["items"]
                has_more = data["has_more"]
                next_token = data.get("page_token")
                if not isinstance(items, list) or type(has_more) is not bool:
                    raise ValueError("Invalid task page")
                for item in items:
                    guid, title, completed = item["guid"], item["summary"], item["completed_at"]
                    if not isinstance(guid, str) or not guid.strip() or not isinstance(title, str):
                        raise ValueError("Invalid task identity")
                    if not (type(completed) is int or isinstance(completed, str) and completed.isascii() and completed.isdigit()):
                        raise ValueError("Invalid completion time")
                    if int(completed) < 0:
                        raise ValueError("Invalid completion time")
                    if int(completed) == 0:
                        continue
                    changed = datetime.fromtimestamp(int(completed) / 1000, timezone.utc)
                    members = item["members"]
                    if not isinstance(members, list):
                        raise ValueError("Invalid task members")
                    assignees = []
                    for member in members:
                        if member.get("type") == "user" and member.get("role") == "assignee":
                            if not isinstance(member.get("id"), str) or not member["id"]:
                                raise ValueError("Invalid task assignee")
                            assignees.append(member["id"])
                    if window.start <= changed < window.end:
                        for assignee in assignees or [None]:
                            key = (guid, assignee)
                            if key not in seen_records:
                                seen_records.add(key)
                                records.append(TaskRecord(record_id=guid, title=title, status="completed", assignee_user_id=assignee,
                                                          changed_at=changed, url=None, status_from=None, status_to="completed"))
                if has_more is False:
                    break
                if not isinstance(next_token, str) or not next_token:
                    if has_more:
                        return CollectResult("lark_tasks", "failure", error_code="invalid_pagination", message="Feishu task pagination failed", attempts=max(1, attempts_total))
                    break
                if next_token in seen_tokens:
                    return CollectResult("lark_tasks", "failure", error_code="invalid_pagination", message="Feishu task pagination failed", attempts=max(1, attempts_total))
                seen_tokens.add(next_token)
                token = next_token
            except (ValueError, TypeError, AttributeError, KeyError, OverflowError, OSError):
                return CollectResult("lark_tasks", "failure", error_code="invalid_payload", message="Feishu task response could not be parsed", attempts=max(1, attempts_total))
    return CollectResult("lark_tasks", "success", records, attempts=max(1, attempts_total))


def _message_text(item: dict) -> str:
    content = item.get("body", {}).get("content", item.get("content", ""))
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return content
    if isinstance(content, dict):
        return str(content.get("text", ""))
    return ""


def collect_messages(client: httpx.Client, chat_ids: Sequence[str], window: CollectionWindow,
                     keywords: Sequence[str], sensitive_keywords: Sequence[str], token_provider: TokenProvider,
                     api_base_url: str, path: str, sleep=None) -> CollectResult[MessageRecord]:
    records: list[MessageRecord] = []
    attempts_total = 0
    for chat_id in chat_ids:
        page_token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            params = {"container_id_type": "chat", "container_id": chat_id,
                      "start_time": str(int(window.start.timestamp())), "end_time": str(int(window.end.timestamp())), "page_size": "50"}
            if page_token:
                params["page_token"] = page_token
            payload, used, error = _get_lark(client, token_provider, api_base_url, path, sleep, params)
            attempts_total += used
            if error:
                return CollectResult("lark_messages", "failure", error_code=error, message="Feishu message collection failed", attempts=max(1, attempts_total))
            try:
                items, page_token = _data_items(payload)
                for item in items:
                    content = _message_text(item)
                    if any(word.casefold() in content.casefold() for word in sensitive_keywords if word):
                        continue
                    if keywords and not any(word.casefold() in content.casefold() for word in keywords if word):
                        continue
                    sender = item.get("sender") or {}
                    records.append(MessageRecord(
                        record_id=str(item.get("message_id") or item.get("id")),
                        sender_user_id=sender.get("id") or sender.get("sender_id"),
                        content=content, sent_at=_dt(item.get("create_time")),
                        url=item.get("url"), chat_name=str(item.get("chat_name") or chat_id),
                    ))
                has_more = payload.get("data", payload).get("has_more")
                if has_more is False:
                    break
                if not page_token and not has_more:
                    break
                if not isinstance(page_token, str) or not page_token or page_token in seen_tokens:
                    return CollectResult("lark_messages", "failure", error_code="invalid_pagination", message="Feishu message pagination failed", attempts=max(1, attempts_total))
                seen_tokens.add(page_token)
            except (ValueError, TypeError, AttributeError, KeyError):
                return CollectResult("lark_messages", "failure", error_code="invalid_payload", message="Feishu message response could not be parsed", attempts=max(1, attempts_total))
    return CollectResult("lark_messages", "success", records, attempts=max(1, attempts_total))
