from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

import httpx

from ..main import run_report
from ..shared.models import DailyReport, RunConfig
from ..notifier.email import send_email
from ..notifier.lark_bot import send_lark_message
from ..shared.errors import ConfigError
from ..shared.operation_storage import OperationStore
from ..shared.storage import get_report
from .schemas import ReportView
from .operation_schemas import DeliveryRequest, GenerationRequest, OperationView, PreviewView


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


class _DeliveryPersistenceError(Exception):
    pass


class OperationService:
    def __init__(self, config: RunConfig, store: OperationStore, *,
                 client_factory: Callable[[], httpx.Client] = httpx.Client, smtp_factory=None):
        self.config = config
        self.display_timezone = ZoneInfo(config.timezone)
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


    def accept_delivery(self, body: DeliveryRequest, request_id: str) -> AcceptedOperation:
        snapshot = None
        def prepare():
            nonlocal snapshot
            enabled = {"email": bool(self.config.smtp.host), "lark": bool(self.config.lark_webhook)}
            if any(not enabled[name] for name in body.channels):
                raise OperationError(400, "channel_not_configured")
            if any(address not in self.config.smtp.recipients for address in body.email_recipients):
                raise OperationError(400, "recipient_not_configured")
            snapshot, _ = self._read_report(body.report_date)
            if report_revision(snapshot) != body.report_revision:
                raise OperationError(409, "report_revision_changed")
        fingerprint = json.dumps({"kind": "delivery", **body.model_dump(mode="json")}, sort_keys=True, separators=(",", ":"))
        sources = {name: None for name in ("github_commits", "lark_tasks", "lark_messages")}
        deliveries = {name: {"status": "pending" if name in body.channels else "not_requested", "attempts": 0, "error_code": None}
                      for name in ("email", "lark")}
        record, is_new = self.store.accept(request_id, "delivery", body.report_date.isoformat(), fingerprint,
                                          body.report_revision, sources, deliveries, before_insert=prepare,
                                          email_recipients=body.email_recipients)
        return AcceptedOperation(OperationView.model_validate_json(json.dumps(record)), is_new, snapshot)


    def execute(self, operation_id: str, snapshot: DailyReport | None = None) -> None:
        record = self.store.get(operation_id)
        if record is None:
            raise KeyError(operation_id)
        if record["status"] != "running":
            return
        if record["kind"] == "delivery":
            self._execute_delivery(record, snapshot)
            return
        try:
            with self.client_factory() as client:
                result = run_report(self.config, date.fromisoformat(record["report_date"]), dry_run=True,
                                    client=client, smtp_factory=self.smtp_factory)
            sources = record["sources"]
            for name, outcome in result.sources.items():
                error = None
                if outcome.status == "failure":
                    if outcome.error_code == "lark_21001":
                        error = "source_access_policy_denied"
                    elif outcome.error_code in ("http_401", "http_403", "missing_credentials", "lark_99991663", "lark_99991664"):
                        error = "source_auth_failed"
                    elif outcome.error_code == "invalid_payload":
                        error = "source_payload_invalid"
                    else:
                        error = "source_unavailable"
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


    def _execute_delivery(self, record: dict, snapshot: DailyReport | None) -> None:
        outcomes = record["deliveries"]
        codes = {"rejected": "delivery_rejected", "partial_failure": "delivery_partial", "unknown": "delivery_unknown"}
        try:
            try:
                with self.client_factory() as client:
                    for channel, outcome in outcomes.items():
                        if outcome["status"] != "pending":
                            continue
                        try:
                            if snapshot is None:
                                raise ValueError("Confirmed snapshot is missing")
                            if channel == "email":
                                if not record.get("email_recipients"):
                                    raise ValueError("Confirmed recipients are missing")
                                result = send_email(snapshot, record["email_recipients"], self.config.smtp,
                                                    **({"smtp_factory": self.smtp_factory} if self.smtp_factory else {}))
                            else:
                                result = send_lark_message(snapshot, self.config.lark_webhook, client=client)
                            status = result.outcome if result.outcome in ("accepted", "rejected", "partial_failure", "unknown") else "unknown"
                            value = {"status": status, "attempts": result.attempts, "error_code": codes.get(status)}
                        except Exception:
                            value = {"status": "unknown", "attempts": 1, "error_code": "delivery_unknown"}
                        self._record_delivery(record["operation_id"], channel, value)
                        outcomes[channel] = value
            except _DeliveryPersistenceError:
                raise
            except Exception:
                for channel, outcome in outcomes.items():
                    if outcome["status"] == "pending":
                        value = {"status": "unknown", "attempts": outcome["attempts"], "error_code": "delivery_unknown"}
                        self._record_delivery(record["operation_id"], channel, value)
                        outcomes[channel] = value
            selected = [item["status"] for item in outcomes.values() if item["status"] != "not_requested"]
            if "unknown" in selected:
                status, error = "unknown", "delivery_unknown"
            elif all(item == "accepted" for item in selected):
                status, error = "succeeded", None
            elif "accepted" in selected or "partial_failure" in selected:
                status, error = "partial_failure", "delivery_partial"
            else:
                status, error = "failed", "delivery_rejected"
            self.store.finish(record["operation_id"], status=status, report_revision=record["report_revision"],
                              sources=record["sources"], deliveries=outcomes, error_code=error)
        except (_DeliveryPersistenceError, sqlite3.Error, OSError):
            logging.getLogger("smart_daily_report").error("operation_result_persistence_failed", extra={"error_code": "operation_storage_failed"})

    def _record_delivery(self, operation_id: str, channel: str, value: dict) -> None:
        try:
            self.store.record_delivery(operation_id, channel, value)
        except (sqlite3.Error, OSError):
            raise _DeliveryPersistenceError from None

    def _read_report(self, report_date: date):
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
            view = view.model_copy(update={
                "generated_at": view.generated_at.astimezone(self.display_timezone),
            })
        except (ValueError, TypeError, KeyError, AttributeError):
            raise OperationError(500, "invalid_report_data") from None
        return report, view

    def preview(self, report_date: date) -> PreviewView:
        report, view = self._read_report(report_date)
        revision = report_revision(report)
        sources, previous = self.store.preview_metadata(report_date.isoformat(), revision)
        recipients = list(dict.fromkeys(self.config.smtp.recipients)) if self.config.smtp.host else []
        targets = {
            "email": {"enabled": bool(self.config.smtp.host and recipients),
                      "label": f"邮件（{len(recipients)} 位可选收件人）" if self.config.smtp.host else "邮件未启用",
                      "recipients": recipients,
                      "previous": previous["email"]},
            "lark": {"enabled": bool(self.config.lark_webhook),
                     "label": "配置的日报群" if self.config.lark_webhook else "飞书未启用",
                     "previous": previous["lark"]},
        }
        return PreviewView.model_validate_json(json.dumps({"report": view.model_dump(mode="json"),
                         "report_revision": revision, "sources": sources, "targets": targets}))
