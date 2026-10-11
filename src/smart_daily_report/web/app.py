from __future__ import annotations

import hmac
import logging
import re
import sqlite3
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .. import __version__
from ..shared.logging import new_run_id
from ..shared.storage import get_report
from .schemas import ErrorResponse, ReportView

ALLOWED_ORIGINS = ("http://127.0.0.1:5173", "http://127.0.0.1:4173")
ERROR_MESSAGES = {
    "operation_unauthorized": "操作令牌无效或未提供",
    "invalid_report_date": "日期无效，请使用 YYYY-MM-DD",
    "origin_not_allowed": "请求来源未允许",
    "report_not_found": "该日期尚无日报",
    "method_not_allowed": "此接口仅允许查询",
    "storage_read_failed": "日报读取失败，请稍后重新查询",
    "invalid_report_data": "日报数据格式异常",
    "internal_error": "日报查询失败",
    "endpoint_not_found": "查询接口不存在",
}
logger = logging.getLogger("smart_daily_report")


def _error(status: int, code: str, run_id: str, *, operation: bool = False) -> JSONResponse:
    logger.warning("report_query_failed", extra={"run_id": run_id, "source": "history",
                                               "status": "failure", "error_code": code})
    return JSONResponse({"error": {"code": code, "message": "操作请求处理失败" if operation and code == "internal_error" else ERROR_MESSAGES[code]}},
                        status_code=status, headers={"Cache-Control": "no-store"})


def create_app(db_path: Path, allowed_hosts: Sequence[str] = ("127.0.0.1", "localhost"), *,
               operations=None, operation_token: str | None = None,
               allowed_origins: Sequence[str] = ALLOWED_ORIGINS,
               display_timezone: str | None = None) -> FastAPI:
    """Read a fixed database; no collectors, notifiers or secret configuration."""
    app = FastAPI(title="智能日报只读接口", version=__version__, docs_url=None, redoc_url=None)
    database = db_path.resolve()
    timezone_name = display_timezone or "UTC"
    display_zone = ZoneInfo(timezone_name)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))
    app.add_middleware(CORSMiddleware, allow_origins=list(allowed_origins),
                       allow_methods=["GET", "POST", "OPTIONS"] if operations is not None else ["GET"],
                       allow_headers=["Authorization", "Content-Type", "Idempotency-Key"] if operations is not None else [])
    bearer = HTTPBearer(auto_error=False)

    @app.middleware("http")
    async def guard_request(request: Request, call_next):
        request.state.run_id = new_run_id()
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed_origins:
            return _error(403, "origin_not_allowed", request.state.run_id)
        protected = (request.url.path in ("/api/v1/generations", "/api/v1/deliveries")
                     or request.url.path.startswith("/api/v1/operations/")
                     or request.url.path.endswith("/preview"))
        if operations is not None and protected and request.method != "OPTIONS":
            credentials = await bearer(request)
            if not credentials or not operation_token or not hmac.compare_digest(credentials.credentials.encode(), operation_token.encode()):
                response = _error(401, "operation_unauthorized", request.state.run_id)
                if origin is not None:
                    response.headers["Access-Control-Allow-Origin"] = origin
                return response
        try:
            response = await call_next(request)
        except Exception:
            response = _error(500, "internal_error", request.state.run_id, operation=operations is not None and protected)
            if origin is not None:
                response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = "method_not_allowed" if exc.status_code == 405 else "endpoint_not_found"
        response = _error(exc.status_code, code, request.state.run_id)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.get("/api/v1/reports/{report_date}", response_model=ReportView,
             responses={status: {"model": ErrorResponse} for status in (400, 403, 404, 405, 500)})
    def read_report(report_date: str, request: Request):
        run_id = request.state.run_id
        try:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", report_date):
                raise ValueError("Invalid date format")
            day = date.fromisoformat(report_date)
        except ValueError:
            return _error(400, "invalid_report_date", run_id)
        try:
            report = get_report(database, day)
            if report is None:
                return _error(404, "report_not_found", run_id)
            if report.generated_at.tzinfo is None or report.generated_at.utcoffset() is None:
                raise ValueError("generated_at must include a timezone")
            report = replace(report, generated_at=report.generated_at.astimezone(display_zone))
            view = ReportView.model_validate(report)
        except (sqlite3.Error, OSError):
            return _error(500, "storage_read_failed", run_id)
        except (ValueError, TypeError, KeyError, AttributeError):
            return _error(500, "invalid_report_data", run_id)
        except Exception:
            return _error(500, "internal_error", run_id)
        logger.info("report_query_succeeded", extra={"run_id": run_id, "source": "history",
                                                   "status": "success"})
        return view

    if operations is not None:
        from .operation_routes import attach_operation_routes
        attach_operation_routes(app, operations)
    return app
