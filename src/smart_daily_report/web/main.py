from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import uvicorn

from ..shared.logging import configure_logging
from .app import create_app


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本机只读日报服务")
    parser.add_argument("--database", type=Path, required=True, help="既有日报 SQLite 文件")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    configure_logging()
    uvicorn.run(create_app(args.database), host="127.0.0.1", port=args.port, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
