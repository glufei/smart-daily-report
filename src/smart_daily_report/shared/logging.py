import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "run_id": getattr(record, "run_id", ""),
        }
        for key in ("source", "status", "attempt", "duration_ms", "record_count", "error_code", "error_type", "channel", "checks"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("smart_daily_report")
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def new_run_id() -> str:
    return str(uuid.uuid4())
