from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, time as datetime_time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .collector.github import collect_commits
from .collector.lark import TokenProvider, collect_messages, collect_tasks
from .generator.formatter import generate_daily_report
from .notifier.email import send_email
from .notifier.lark_bot import send_lark_message
from .shared.calendar import is_workday
from .shared.config import load_config
from .shared.health import check_dependencies
from .shared.identity import filter_sensitive_messages, map_records_to_members, resolve_github_member
from .shared.logging import configure_logging, new_run_id
from .shared.models import CollectResult, DeliveryResult, RunConfig, RunResult
from .shared.storage import write_report


def run_report(config: RunConfig, report_date: date, dry_run: bool = False,
               client: httpx.Client | None = None, smtp_factory=None, sleep=time.sleep) -> RunResult:
    logger = logging.getLogger("smart_daily_report")
    own_client = client is None
    client = client or httpx.Client(timeout=10)
    run_id = new_run_id()
    start = time.monotonic()
    try:
        logger.info("run_started", extra={"run_id": run_id})
        if not is_workday(report_date, config.holidays):
            logger.info("skipped_non_workday", extra={"run_id": run_id, "status": "skipped"})
            return RunResult(True, skipped=True)
        enabled = {"github_commits": bool(config.github_repositories),
                   "lark_tasks": bool(config.lark_project_ids), "lark_messages": bool(config.lark_chat_ids)}
        if not any(enabled.values()):
            return RunResult(False, error_code="no_sources_configured")
        zone = ZoneInfo(config.timezone)
        window = __import__("smart_daily_report.shared.models", fromlist=["CollectionWindow"]).CollectionWindow(
            datetime.combine(report_date, datetime_time.min, zone),
            datetime.combine(report_date.fromordinal(report_date.toordinal() + 1), datetime_time.min, zone),
        )
        token_provider = None
        if config.lark_app_id and config.lark_app_secret:
            token_provider = TokenProvider(client, config.lark_api_base_url, config.lark_token_path,
                                           config.lark_app_id, config.lark_app_secret)
        results = []
        def safely_collect(source: str, function, *args) -> CollectResult:
            try:
                return function(*args)
            except Exception as exc:
                logger.error("collector_unhandled_error", extra={"run_id": run_id, "source": source,
                             "status": "failure", "error_code": "collector_unhandled", "error_type": type(exc).__name__})
                return CollectResult(source, "failure", error_code="collector_unhandled", message="Collector failed unexpectedly")

        if config.github_repositories:
            results.append(safely_collect("github_commits", collect_commits, client, config.github_repositories,
                                           window, config.github_api_base_url, config.github_token, sleep))
        else:
            results.append(CollectResult("github_commits", "success"))
        if config.lark_project_ids:
            if token_provider:
                results.append(safely_collect("lark_tasks", collect_tasks, client, config.lark_project_ids, window,
                                              token_provider, config.lark_api_base_url, config.lark_task_search_path, sleep))
            else:
                results.append(CollectResult("lark_tasks", "failure", error_code="missing_credentials", message="Feishu credentials are not configured"))
        else:
            results.append(CollectResult("lark_tasks", "success"))
        if config.lark_chat_ids:
            if token_provider:
                results.append(safely_collect("lark_messages", collect_messages, client, config.lark_chat_ids, window,
                                              config.report_keywords, config.sensitive_keywords, token_provider,
                                              config.lark_api_base_url, config.lark_message_path, sleep))
            else:
                results.append(CollectResult("lark_messages", "failure", error_code="missing_credentials", message="Feishu credentials are not configured"))
        else:
            results.append(CollectResult("lark_messages", "success"))
        for result in results:
            logger.info("collection_finished", extra={"run_id": run_id, "source": result.source,
                        "status": result.status, "record_count": len(result.records), "attempt": result.attempts,
                        "error_code": result.error_code})
        source_results = {result.source: result for result in results if enabled[result.source]}
        if all(result.status == "failure" for result in source_results.values()):
            logger.error("all_sources_failed", extra={"run_id": run_id, "status": "failure"})
            return RunResult(False, error_code="all_sources_failed", sources=source_results)
        commits = next(item.records for item in results if item.source == "github_commits")
        tasks = next(item.records for item in results if item.source == "lark_tasks")
        messages = filter_sensitive_messages(next(item.records for item in results if item.source == "lark_messages"), config.sensitive_keywords)
        statuses = {item.source: item.status for item in results}
        assigned_commits = sum(1 for item in commits if resolve_github_member(config, item))
        assigned_tasks = sum(1 for item in tasks if any((item.assignee_user_id or "").casefold() == user_id.casefold()
                               for member in config.members for user_id in member.lark_user_ids))
        assigned_messages = sum(1 for item in messages if any((item.sender_user_id or "").casefold() == user_id.casefold()
                                  for member in config.members for user_id in member.lark_user_ids))
        unmapped_count = len(commits) + len(tasks) + len(messages) - assigned_commits - assigned_tasks - assigned_messages
        if unmapped_count:
            logger.warning("records_unmapped", extra={"run_id": run_id, "record_count": unmapped_count, "status": "warning"})
        members = map_records_to_members(config, commits, tasks, messages, statuses)
        report = generate_daily_report(report_date, config.team_name, members, statuses, datetime.now(timezone.utc))
        db_path = Path(config.database_path)
        write_report(db_path, report)
        deliveries = {}
        if not dry_run:
            try:
                email_result = send_email(report, config.smtp.recipients, config.smtp, **({"smtp_factory": smtp_factory} if smtp_factory else {}), sleep=sleep)
            except Exception as exc:
                email_result = DeliveryResult(False, 1, "email_unhandled")
                logger.error("notifier_unhandled_error", extra={"run_id": run_id, "channel": "email", "status": "failure", "error_code": "email_unhandled", "error_type": type(exc).__name__})
            deliveries["email"] = email_result
            logger.info("delivery_finished", extra={"run_id": run_id, "channel": "email", "status": "success" if email_result.success else "failure", "error_code": email_result.error_code})
            if config.lark_webhook:
                try:
                    lark_result = send_lark_message(report, config.lark_webhook, client=client, sleep=sleep)
                except Exception as exc:
                    lark_result = DeliveryResult(False, 1, "lark_unhandled")
                    logger.error("notifier_unhandled_error", extra={"run_id": run_id, "channel": "lark", "status": "failure", "error_code": "lark_unhandled", "error_type": type(exc).__name__})
                deliveries["lark"] = lark_result
                logger.info("delivery_finished", extra={"run_id": run_id, "channel": "lark", "status": "success" if lark_result.success else "failure", "error_code": lark_result.error_code})
        duration = round((time.monotonic() - start) * 1000)
        succeeded = all(item.success for item in deliveries.values())
        logger.info("run_finished", extra={"run_id": run_id, "status": "success" if succeeded else "failure", "duration_ms": duration})
        return RunResult(succeeded, report=report, deliveries=deliveries,
                         error_code=None if succeeded else "delivery_failed", sources=source_results)
    except Exception as exc:
        logger.error("run_failed", extra={"run_id": run_id, "status": "failure", "error_code": "internal_error", "error_type": type(exc).__name__})
        return RunResult(False, error_code="internal_error")
    finally:
        if own_client:
            client.close()


def run_health_check(config: RunConfig, client: httpx.Client | None = None):
    own_client = client is None
    client = client or httpx.Client(timeout=5)
    try:
        return check_dependencies(config, client)
    finally:
        if own_client:
            client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and deliver the team's daily report")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--check", action="store_true", help="validate configuration and external dependencies")
    parser.add_argument("--dry-run", action="store_true", help="collect and render without delivering")
    args = parser.parse_args(argv)
    configure_logging()
    try:
        config = load_config(args.config)
        report_date = args.date or datetime.now(ZoneInfo(config.timezone)).date()
        if args.check:
            result = run_health_check(config)
            logging.getLogger("smart_daily_report").info("health_check_finished", extra={"run_id": new_run_id(), "status": "success" if result.success else "failure", "checks": result.checks})
            return 0 if result.success else 1
        result = run_report(config, report_date, args.dry_run)
        return 0 if result.success else 1
    except Exception as exc:
        logging.getLogger("smart_daily_report").error("configuration_failed", extra={"run_id": new_run_id(), "error_code": type(exc).__name__})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
