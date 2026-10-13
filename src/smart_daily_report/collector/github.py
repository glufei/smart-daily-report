from __future__ import annotations

from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Sequence

import httpx

from ..shared.http import request_with_retry
from ..shared.models import CollectResult, CollectionWindow, CommitRecord


def _get_github(client, url, sleep=None, **args):
    response, attempts, error = request_with_retry(client, "GET", url, **args) if sleep is None else request_with_retry(client, "GET", url, sleep=sleep, **args)
    if response is not None and response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        reset = response.headers.get("X-RateLimit-Reset")
        if reset:
            try:
                delay = max(0, min(float(reset) - __import__("time").time(), 30))
            except ValueError:
                return response, attempts, error
            (sleep or __import__("time").sleep)(delay)
            response, used, error = request_with_retry(client, "GET", url, **args) if sleep is None else request_with_retry(client, "GET", url, sleep=sleep, **args)
            attempts += used
    return response, attempts, error


def collect_commits(client: httpx.Client, repositories: Sequence[str], window: CollectionWindow,
                    api_base_url: str = "https://api.github.com", token: str | None = None,
                    sleep=None) -> CollectResult[CommitRecord]:
    records: list[CommitRecord] = []
    total_attempts = 1
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for repository in repositories:
        page_url = f"{api_base_url.rstrip('/')}/repos/{repository}/commits"
        seen_pages: set[str] = set()
        params = {"since": window.start.isoformat(), "until": window.end.isoformat(), "per_page": 100}
        while page_url:
            if page_url in seen_pages:
                return CollectResult("github_commits", "failure", error_code="invalid_pagination", message="GitHub commit pagination failed", attempts=total_attempts)
            seen_pages.add(page_url)
            args = {"headers": headers, "params": params, "timeout": 10}
            response, attempts, error = _get_github(client, page_url, sleep, **args)
            total_attempts += attempts - 1
            if error or response is None or response.is_error:
                code = error or f"http_{response.status_code if response else 'unknown'}"
                return CollectResult("github_commits", "failure", error_code=code, message="GitHub collection failed", attempts=total_attempts)
            try:
                items = response.json()
                if not isinstance(items, list):
                    raise ValueError("unexpected payload")
                for item in items:
                    commit = item.get("commit") or {}
                    author = commit.get("author") or {}
                    stats = item.get("stats") or {}
                    changed_files = item.get("files") or []
                    if "stats" not in item:
                        details_url = item.get("url") or f"{api_base_url.rstrip('/')}/repos/{repository}/commits/{item.get('sha', '')}"
                        detail_args = {"headers": headers, "timeout": 10}
                        filenames: set[str] = set()
                        seen_detail_pages: set[str] = set()
                        while details_url:
                            if details_url in seen_detail_pages:
                                return CollectResult("github_commits", "failure", error_code="invalid_pagination", message="GitHub commit pagination failed", attempts=total_attempts)
                            seen_detail_pages.add(details_url)
                            detail_response, detail_attempts, detail_error = _get_github(client, details_url, sleep, **detail_args)
                            total_attempts += detail_attempts
                            if detail_error or detail_response is None:
                                code = detail_error or "details_unavailable"
                                return CollectResult("github_commits", "failure", error_code=code, message="GitHub commit details failed", attempts=total_attempts)
                            details = detail_response.json()
                            files = details["files"]
                            if not isinstance(files, list):
                                raise ValueError("Invalid commit files")
                            for file in files:
                                filename = file["filename"]
                                if not isinstance(filename, str) or not filename:
                                    raise ValueError("Invalid commit filename")
                                filenames.add(filename)
                            if len(seen_detail_pages) == 1:
                                stats = details["stats"]
                            if len(filenames) >= 3000:
                                return CollectResult("github_commits", "failure", error_code="details_file_limit", message="GitHub commit file completeness unavailable", attempts=total_attempts)
                            details_url = detail_response.links.get("next", {}).get("url")
                        changed_files = filenames
                    api_author = item.get("author") or {}
                    author_login, author_name = api_author.get("login"), author.get("name")
                    if (author_login is not None and not isinstance(author_login, str)
                            or author_name is not None and not isinstance(author_name, str)):
                        raise ValueError("Invalid commit author identity")
                    committed = author.get("date")
                    records.append(CommitRecord(
                        record_id=str(item["sha"]), repository=repository,
                        author_login=author_login, author_name=author_name,
                        message=(str(commit.get("message", "")).splitlines() or [""])[0],
                        committed_at=__import__("datetime").datetime.fromisoformat(committed.replace("Z", "+00:00")),
                        url=str(item.get("html_url", "")),
                        additions=int(stats.get("additions", 0)), deletions=int(stats.get("deletions", 0)),
                        files_changed=len(changed_files),
                    ))
            except (KeyError, TypeError, ValueError, AttributeError):
                return CollectResult("github_commits", "failure", error_code="invalid_payload", message="GitHub response could not be parsed", attempts=total_attempts)
            page_url = response.links.get("next", {}).get("url")
            params = None
    return CollectResult("github_commits", "success", records, attempts=total_attempts)
