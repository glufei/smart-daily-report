from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

import uvicorn

from ..shared.logging import configure_logging
from ..shared.config import load_config
from ..shared.operation_storage import OperationStore
from .operations import OperationService, validate_operation_config
from .app import create_app


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本机日报服务")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--database", type=Path, help="既有日报 SQLite 文件（只读）")
    mode.add_argument("--config", type=Path, help="日报配置（生成与推送）")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    configure_logging()
    if args.config is not None:
        config = load_config(args.config)
        token = os.environ.get("DAILY_REPORT_WEB_TOKEN", "")
        validate_operation_config(config, token)
        database = Path(config.database_path)
        service = OperationService(config, OperationStore(database.with_name(database.name + ".operations.sqlite3")))
        app = create_app(database, operations=service, operation_token=token)
    else:
        app = create_app(args.database)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
