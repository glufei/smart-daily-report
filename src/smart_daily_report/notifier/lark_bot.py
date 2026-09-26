from __future__ import annotations

import time
from typing import Callable

import httpx

from ..shared.models import DailyReport, DeliveryResult


def send_lark_message(report: DailyReport, webhook_url: str, client: httpx.Client | None = None,
                      sleep: Callable[[float], None] = time.sleep) -> DeliveryResult:
    own_client = client is None
    client = client or httpx.Client(timeout=10)
    try:
        for attempt in range(1, 4):
            try:
                response = client.post(webhook_url, json={"msg_type": "interactive", "card": {
                    "config": {"wide_screen_mode": True},
                    "elements": [{"tag": "markdown", "content": report.markdown}],
                }}, timeout=10)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 3:
                        sleep(min(2 ** (attempt - 1), 5))
                        continue
                if response.is_error:
                    return DeliveryResult(False, attempt, f"http_{response.status_code}")
                payload = response.json()
                if payload.get("StatusCode", 0) != 0:
                    return DeliveryResult(False, attempt, "lark_rejected")
                return DeliveryResult(True, attempt)
            except (httpx.TransportError, ValueError):
                if attempt == 3:
                    return DeliveryResult(False, attempt, "lark_unavailable")
                sleep(min(2 ** (attempt - 1), 5))
        return DeliveryResult(False, 3, "lark_unavailable")
    finally:
        if own_client:
            client.close()
