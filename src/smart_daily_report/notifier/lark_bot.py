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
                if response.status_code >= 500:
                    return DeliveryResult(False, attempt, "lark_unknown", "unknown")
                if response.is_error:
                    return DeliveryResult(False, attempt, f"http_{response.status_code}", "rejected")
                payload = response.json()
                if not isinstance(payload, dict):
                    return DeliveryResult(False, attempt, "lark_unknown", "unknown")
                codes = [payload[key] for key in ("code", "StatusCode") if key in payload]
                if not codes or any(type(code) is not int for code in codes) or len(set(codes)) != 1:
                    return DeliveryResult(False, attempt, "lark_unknown", "unknown")
                if codes[0] != 0:
                    return DeliveryResult(False, attempt, "lark_rejected", "rejected")
                return DeliveryResult(True, attempt, outcome="accepted")
            except (httpx.ConnectError, httpx.ConnectTimeout):
                if attempt == 3:
                    return DeliveryResult(False, attempt, "lark_unavailable", "rejected")
                sleep(min(2 ** (attempt - 1), 5))
            except (httpx.TransportError, ValueError):
                return DeliveryResult(False, attempt, "lark_unknown", "unknown")
        return DeliveryResult(False, 3, "lark_unavailable", "rejected")
    finally:
        if own_client:
            client.close()
