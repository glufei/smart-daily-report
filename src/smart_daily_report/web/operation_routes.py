from __future__ import annotations

import json
import sqlite3

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter

from ..shared.operation_storage import OperationConflict
from .operation_schemas import DeliveryRequest, GenerationRequest, OperationId, OperationView
from .operations import OperationError, OperationService

MESSAGES = {
    "non_workday": "该日期为非工作日，不能推送",
    "channel_not_configured": "所选推送渠道未配置",
    "report_revision_changed": "日报已更新，请重新预览后推送",
    "delivery_not_repeatable": "该渠道已接受或结果待核实，不能重复推送",
    "invalid_request": "操作参数无效",
    "invalid_report_date": "日期无效，请使用 YYYY-MM-DD",
    "report_not_found": "该日期尚无日报",
    "operation_not_found": "未找到该操作记录",
    "idempotency_conflict": "同一请求标识不能用于不同操作",
    "operation_busy": "已有操作正在执行，请先查看其结果",
    "storage_read_failed": "日报读取失败，请稍后重新查询",
    "invalid_report_data": "日报数据格式异常",
    "operation_storage_failed": "操作记录不可用，未接受新操作",
    "internal_error": "操作请求处理失败",
}


def _identifier(value: str | None) -> str:
    try:
        return TypeAdapter(OperationId).validate_python(value)
    except ValueError:
        raise OperationError(400, "invalid_request") from None


def _view(record: dict | None) -> OperationView:
    if record is None:
        raise OperationError(404, "operation_not_found")
    return OperationView.model_validate_json(json.dumps(record))


def attach_operation_routes(app: FastAPI, service: OperationService) -> None:
    @app.exception_handler(OperationError)
    async def operation_error(request: Request, error: OperationError):
        return JSONResponse({"error": {"code": error.code, "message": MESSAGES[error.code]}},
                            status_code=error.status_code, headers={"Cache-Control": "no-store"})

    @app.exception_handler(OperationConflict)
    async def operation_conflict(request: Request, error: OperationConflict):
        return JSONResponse({"error": {"code": error.code, "message": MESSAGES[error.code]}},
                            status_code=409, headers={"Cache-Control": "no-store"})

    @app.exception_handler(sqlite3.Error)
    async def storage_error(request: Request, error: sqlite3.Error):
        return await operation_error(request, OperationError(500, "operation_storage_failed"))

    @app.post("/api/v1/generations")
    async def generate(request: Request, background: BackgroundTasks):
        key = _identifier(request.headers.get("Idempotency-Key"))
        try:
            body = GenerationRequest.model_validate(await request.json())
        except ValueError:
            raise OperationError(400, "invalid_request") from None
        accepted = service.accept_generation(body, key)
        if accepted.is_new:
            background.add_task(service.execute, accepted.view.operation_id)
        return JSONResponse(accepted.view.model_dump(mode="json"),
                            status_code=202 if accepted.view.status == "running" else 200)

    @app.post("/api/v1/deliveries")
    async def deliver(request: Request, background: BackgroundTasks):
        key = _identifier(request.headers.get("Idempotency-Key"))
        try:
            body = DeliveryRequest.model_validate(await request.json())
        except ValueError:
            raise OperationError(400, "invalid_request") from None
        accepted = service.accept_delivery(body, key)
        if accepted.is_new:
            background.add_task(service.execute, accepted.view.operation_id, accepted.snapshot)
        return JSONResponse(accepted.view.model_dump(mode="json"), status_code=202 if accepted.view.status == "running" else 200)

    @app.get("/api/v1/operations/current")
    def current():
        record = service.store.current()
        return _view(record) if record else None

    @app.get("/api/v1/operations/by-key/{request_id}")
    def by_key(request_id: str):
        return _view(service.store.by_key(_identifier(request_id)))

    @app.get("/api/v1/operations/{operation_id}")
    def operation(operation_id: str):
        return _view(service.store.get(_identifier(operation_id)))

    @app.get("/api/v1/reports/{report_date}/preview")
    def preview(report_date: str):
        try:
            day = GenerationRequest.model_validate({"report_date": report_date}).report_date
        except ValueError:
            raise OperationError(400, "invalid_report_date") from None
        return service.preview(day)
