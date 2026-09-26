from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Sequence

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
    data = payload.get("data", payload)
    items = data.get("items", data.get("tasks", data.get("messages", [])))
    return items, data.get("page_token")


def _post_lark(client, provider, base_url, path, body, source, sleep=None, params=None):
    attempts = 0
    refreshed = False
    while True:
        try:
            token = provider.get()
        except Exception:
            return None, attempts + 1, "token_refresh_failed"
        request_args = {"json": body, "params": params, "headers": {"Authorization": f"Bearer {token}"}, "timeout": 10}
        response, used, error = request_with_retry(client, "POST", base_url.rstrip("/") + "/" + path.lstrip("/"), **request_args) if sleep is None else request_with_retry(client, "POST", base_url.rstrip("/") + "/" + path.lstrip("/"), sleep=sleep, **request_args)
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
            if payload.get("code", 0) != 0:
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
    for project_id in project_ids:
        token: str | None = None
        seen_tokens: set[str] = set()
        while True:
            body = {"page_size": 100, "tasklist_guid": project_id}
            params = {}
            if token:
                params["page_token"] = token
            payload, attempts, error = _post_lark(client, token_provider, api_base_url, path, body, "lark_tasks", sleep, params)
            attempts_total += attempts
            if error:
                return CollectResult("lark_tasks", "failure", error_code=error, message="Feishu task collection failed", attempts=max(1, attempts_total))
            try:
                items, next_token = _data_items(payload)
                for item in items:
                    changed = _dt(item.get("updated_time") or item.get("completed_at") or item.get("created_at"))
                    if window.start <= changed < window.end:
                        assignee = item.get("assignee") or item.get("assignee_id") or item.get("assignee_user_id")
                        if isinstance(assignee, dict):
                            assignee = assignee.get("id") or assignee.get("user_id")
                        records.append(TaskRecord(
                            record_id=str(item.get("guid") or item.get("task_id") or item.get("id")),
                            title=str(item.get("summary") or item.get("title") or ""),
                            status=str(item.get("status", "unknown")), assignee_user_id=assignee,
                            changed_at=changed, url=item.get("url") or item.get("link"),
                            status_from=item.get("status_from"), status_to=str(item.get("status_to") or item.get("status", "unknown")),
                        ))
                has_more = payload.get("data", payload).get("has_more")
                if has_more is False:
                    break
                if not next_token:
                    if has_more:
                        return CollectResult("lark_tasks", "failure", error_code="invalid_pagination", message="Feishu task pagination failed", attempts=max(1, attempts_total))
                    break
                if next_token in seen_tokens:
                    return CollectResult("lark_tasks", "failure", error_code="invalid_pagination", message="Feishu task pagination failed", attempts=max(1, attempts_total))
                seen_tokens.add(next_token)
                token = next_token
            except (ValueError, TypeError, AttributeError):
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
        while True:
            params = {"container_id_type": "chat", "container_id": chat_id,
                      "start_time": str(int(window.start.timestamp())), "end_time": str(int(window.end.timestamp())), "page_size": "50"}
            if page_token:
                params["page_token"] = page_token
            try:
                bearer = token_provider.get()
            except Exception:
                return CollectResult("lark_messages", "failure", error_code="token_refresh_failed", message="Feishu message collection failed", attempts=max(1, attempts_total + 1))
            headers = {"Authorization": f"Bearer {bearer}"}
            url = api_base_url.rstrip("/") + "/" + path.lstrip("/")
            response, used, error = request_with_retry(client, "GET", url, params=params, headers=headers, timeout=10) if sleep is None else request_with_retry(client, "GET", url, sleep=sleep, params=params, headers=headers, timeout=10)
            attempts_total += used
            if response is not None and response.status_code == 401:
                try:
                    bearer = token_provider.get(refresh=True)
                    response = client.get(url, params=params, headers={"Authorization": f"Bearer {bearer}"}, timeout=10)
                    attempts_total += 1
                    error = None if response.is_success else f"http_{response.status_code}"
                except Exception:
                    error = "token_refresh_failed"
            if error or response is None or response.is_error:
                return CollectResult("lark_messages", "failure", error_code=error or f"http_{response.status_code}", message="Feishu message collection failed", attempts=max(1, attempts_total))
            try:
                payload = response.json()
                if payload.get("code", 0) != 0:
                    if payload.get("code") in (99991663, 99991664):
                        try:
                            bearer = token_provider.get(refresh=True)
                            response = client.get(url, params=params, headers={"Authorization": f"Bearer {bearer}"}, timeout=10)
                            attempts_total += 1
                            if response.is_error:
                                return CollectResult("lark_messages", "failure", error_code=f"http_{response.status_code}", message="Feishu message collection failed", attempts=max(1, attempts_total))
                            payload = response.json()
                        except Exception:
                            return CollectResult("lark_messages", "failure", error_code="token_refresh_failed", message="Feishu message collection failed", attempts=max(1, attempts_total + 1))
                    if payload.get("code", 0) != 0:
                        return CollectResult("lark_messages", "failure", error_code=f"lark_{payload.get('code')}", message="Feishu message collection failed", attempts=max(1, attempts_total))
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
                if not page_token:
                    break
            except (ValueError, TypeError, AttributeError):
                return CollectResult("lark_messages", "failure", error_code="invalid_payload", message="Feishu message response could not be parsed", attempts=max(1, attempts_total))
    return CollectResult("lark_messages", "success", records, attempts=max(1, attempts_total))
