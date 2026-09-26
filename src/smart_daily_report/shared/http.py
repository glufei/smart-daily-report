from __future__ import annotations

import time
from collections.abc import Callable

import httpx


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs,
) -> tuple[httpx.Response | None, int, str | None]:
    attempts = 0
    for attempts in range(1, max_attempts + 1):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TimeoutException:
            if attempts == max_attempts:
                return None, attempts, "timeout"
            sleep(min(2 ** (attempts - 1), 5))
            continue
        except httpx.TransportError:
            if attempts == max_attempts:
                return None, attempts, "network_error"
            sleep(min(2 ** (attempts - 1), 5))
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempts == max_attempts:
                return response, attempts, f"http_{response.status_code}"
            retry_after = response.headers.get("Retry-After")
            try:
                delay = min(max(float(retry_after), 0), 30) if retry_after else min(2 ** (attempts - 1), 5)
            except ValueError:
                delay = min(2 ** (attempts - 1), 5)
            sleep(delay)
            continue
        if response.is_error:
            return response, attempts, f"http_{response.status_code}"
        return response, attempts, None
    return None, attempts, "network_error"


class TokenProvider:
    def __init__(self, client: httpx.Client, base_url: str, token_path: str, app_id: str, app_secret: str):
        self.client = client
        self.url = base_url.rstrip("/") + "/" + token_path.lstrip("/")
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: str | None = None

    def get(self, refresh: bool = False) -> str:
        if self._token and not refresh:
            return self._token
        response = self.client.post(self.url, json={"app_id": self.app_id, "app_secret": self.app_secret}, timeout=10)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", payload)
        token = data.get("tenant_access_token")
        if not token:
            raise ValueError("Token response did not contain tenant_access_token")
        self._token = token
        return token
