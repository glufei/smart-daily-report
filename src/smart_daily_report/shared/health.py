from __future__ import annotations

import httpx
import smtplib
from datetime import datetime, timedelta, timezone

from .http import TokenProvider
from urllib.parse import quote
from .models import HealthCheckResult, RunConfig


def check_dependencies(config: RunConfig, client: httpx.Client) -> HealthCheckResult:
    checks: dict[str, bool] = {"configuration": True}
    if config.github_repositories:
        headers = {}
        if config.github_token:
            headers["Authorization"] = f"Bearer {config.github_token}"
            try:
                response = client.get(config.github_api_base_url + "/rate_limit", headers=headers, timeout=5)
                checks["github_api"] = response.is_success
            except httpx.HTTPError:
                checks["github_api"] = False
        for index, repository in enumerate(config.github_repositories):
            try:
                repo_response = client.get(config.github_api_base_url + f"/repos/{repository}",
                                           headers=headers, timeout=5)
                checks[f"github_repository_{index + 1}"] = repo_response.is_success
            except httpx.HTTPError:
                checks[f"github_repository_{index + 1}"] = False
    if config.lark_project_ids or config.lark_chat_ids:
        if not config.lark_app_id or not config.lark_app_secret:
            checks["lark_credentials"] = False
        else:
            try:
                provider = TokenProvider(client, config.lark_api_base_url, config.lark_token_path,
                                         config.lark_app_id, config.lark_app_secret)
                token = provider.get()
                checks["lark_token"] = True
                headers = {"Authorization": f"Bearer {token}"}
                for index, project_id in enumerate(config.lark_project_ids):
                    response = client.get(config.lark_api_base_url.rstrip("/") + "/" + config.lark_task_search_path.replace("{tasklist_guid}", quote(project_id, safe="")).lstrip("/"),
                                          params={"page_size": "1", "completed": "true", "user_id_type": "open_id"}, headers=headers, timeout=5)
                    payload = response.json() if response.is_success else {}
                    checks[f"lark_tasks_{index + 1}"] = response.is_success and payload.get("code", 0) == 0
                now = datetime.now(timezone.utc)
                for index, chat_id in enumerate(config.lark_chat_ids):
                    params = {"container_id_type": "chat", "container_id": chat_id, "page_size": "1",
                              "start_time": str(int((now - timedelta(minutes=1)).timestamp())),
                              "end_time": str(int(now.timestamp()))}
                    response = client.get(config.lark_api_base_url.rstrip("/") + "/" + config.lark_message_path.lstrip("/"),
                                          params=params, headers=headers, timeout=5)
                    payload = response.json() if response.is_success else {}
                    checks[f"lark_messages_{index + 1}"] = response.is_success and payload.get("code", 0) == 0
            except Exception:
                checks["lark_token"] = False
    if config.lark_webhook:
        checks["lark_webhook_configured"] = True
    if config.smtp.host:
        try:
            connection_factory = smtplib.SMTP_SSL if config.smtp.use_ssl else smtplib.SMTP
            with connection_factory(config.smtp.host, config.smtp.port, timeout=3) as smtp:
                smtp.noop()
            checks["smtp"] = True
        except (OSError, smtplib.SMTPException):
            checks["smtp"] = False
    return HealthCheckResult(all(checks.values()), checks, None if all(checks.values()) else "One or more dependency checks failed")
