from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import httpx

from ..main import run_report
from ..shared.models import DailyReport, RunConfig
from ..shared.errors import ConfigError
from ..shared.operation_storage import OperationStore
from ..shared.storage import get_report
from .schemas import ReportView
from .operation_schemas import GenerationRequest, OperationView, PreviewView


def validate_operation_config(config: RunConfig, token: str) -> None:
    if len(token) < 32 or not token.strip():
        raise ConfigError("Operation token must have at least 32 non-blank characters")
    if not (config.github_repositories or config.lark_project_ids or config.lark_chat_ids):
        raise ConfigError("Operation mode requires an enabled source")
    if (config.lark_project_ids or config.lark_chat_ids) and not (config.lark_app_id and config.lark_app_secret):
        raise ConfigError("Enabled Feishu sources require application credentials")


def report_revision(report: DailyReport) -> str:
    canonical = json.dumps(asdict(report), sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, default=lambda value: value.isoformat())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AcceptedOperation:
    view: OperationView
    is_new: bool
    snapshot: DailyReport | None = None


class OperationError(Exception):
    def __init__(self, status_code: int, code: str):
        self.status_code = status_code
        self.code = code
        super().__init__(code)


class OperationService:
    def __init__(self, config: RunConfig, store: OperationStore, *,
                 client_factory: Callable[[], httpx.Client] = httpx.Client, smtp_factory=None):
        self.config = config
        self.store = store
        self.client_factory = client_factory
        self.smtp_factory = smtp_factory
        store.initialize()
        store.recover_interrupted()

    def accept_generation(self, body: GenerationRequest, request_id: str) -> AcceptedOperation:
        enabled = {"github_commits": bool(self.config.github_repositories),
                   "lark_tasks": bool(self.config.lark_project_ids),
                   "lark_messages": bool(self.config.lark_chat_ids)}
        sources = {name: {"status": "pending" if active else "disabled", "error_code": None}
                   for name, active in enabled.items()}
        deliveries = {name: {"status": "not_requested", "attempts": 0, "error_code": None}
                      for name in ("email", "lark")}
        fingerprint = json.dumps({"kind": "generation", **body.model_dump(mode="json")},
                                 sort_keys=True, separators=(",", ":"))
        record, is_new = self.store.accept(request_id, "generation", body.report_date.isoformat(),
                                          fingerprint, None, sources, deliveries)
        return AcceptedOperation(OperationView.model_validate_json(json.dumps(record)), is_new)


    def execute(self, operation_id: str, snapshot: DailyReport | None = None) -> None:
        record = self.store.get(operation_id)
        if record is None:
            raise KeyError(operation_id)
        try:
            with self.client_factory() as client:
                result = run_report(self.config, date.fromisoformat(record["report_date"]), dry_run=True,
                                    client=client, smtp_factory=self.smtp_factory)
            sources = record["sources"]
            for name, outcome in result.sources.items():
                error = None
                if outcome.status == "failure":
                    error = "source_auth_failed" if outcome.error_code in ("http_401", "http_403", "missing_credentials") else "source_payload_invalid" if outcome.error_code == "invalid_payload" else "source_unavailable"
                sources[name] = {"status": outcome.status, "error_code": error}
            if result.skipped:
                status, error = "skipped", "non_workday"
            elif result.report is None:
                status, error = "failed", result.error_code if result.error_code in ("all_sources_failed", "report_write_failed") else "internal_error"
            else:
                status = "partial_failure" if any(item.status == "failure" for item in result.sources.values()) else "succeeded"
                error = None
            self.store.finish(operation_id, status=status,
                              report_revision=report_revision(result.report) if result.report is not None else None,
                              sources=sources, deliveries=record["deliveries"], error_code=error)
        except Exception:
            self.store.finish(operation_id, status="failed", report_revision=None,
                              sources=record["sources"], deliveries=record["deliveries"], error_code="internal_error")


    def preview(self, report_date: date) -> PreviewView:
        try:
            report = get_report(Path(self.config.database_path), report_date)
        except (sqlite3.Error, OSError):
            raise OperationError(500, "storage_read_failed") from None
        except (ValueError, TypeError, KeyError, AttributeError):
            raise OperationError(500, "invalid_report_data") from None
        if report is None:
            raise OperationError(404, "report_not_found")
        try:
            view = ReportView.model_validate(report)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise OperationError(500, "invalid_report_data") from None
        revision = report_revision(report)
        sources, previous = self.store.preview_metadata(report_date.isoformat(), revision)
        targets = {
            "email": {"enabled": bool(self.config.smtp.host),
                      "label": f"邮件（{len(self.config.smtp.recipients)} 位收件人）" if self.config.smtp.host else "邮件未启用",
                      "previous": previous["email"]},
            "lark": {"enabled": bool(self.config.lark_webhook),
                     "label": "配置的日报群" if self.config.lark_webhook else "飞书未启用",
                     "previous": previous["lark"]},
        }
        return PreviewView.model_validate_json(json.dumps({"report": view.model_dump(mode="json"),
                         "report_revision": revision, "sources": sources, "targets": targets}))
