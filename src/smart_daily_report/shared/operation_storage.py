from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class OperationConflict(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class OperationStore:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS operations (
                operation_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                request_fingerprint TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, payload TEXT NOT NULL
            )""")

    def accept(self, request_id: str, kind: str, report_date: str,
               request_fingerprint: str, report_revision: str | None,
               sources: dict, deliveries: dict) -> tuple[dict, bool]:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT payload, request_fingerprint FROM operations WHERE request_id=?", (request_id,)).fetchone()
            if existing:
                if existing[1] != request_fingerprint:
                    raise OperationConflict("idempotency_conflict")
                return json.loads(existing[0]), False
            if connection.execute("SELECT 1 FROM operations WHERE status='running' LIMIT 1").fetchone():
                raise OperationConflict("operation_busy")
            now = datetime.now(timezone.utc).isoformat()
            record = {"operation_id": str(uuid4()), "request_id": request_id,
                      "kind": kind, "report_date": report_date, "status": "running",
                      "created_at": now, "updated_at": now,
                      "report_revision": report_revision, "sources": sources,
                      "deliveries": deliveries, "error_code": None}
            connection.execute("INSERT INTO operations VALUES (?,?,?,?,?,?)",
                               (record["operation_id"], request_id, request_fingerprint,
                                "running", now, json.dumps(record)))
            return record, True


    def finish(self, operation_id: str, *, status: str, report_revision: str | None,
               sources: dict, deliveries: dict, error_code: str | None) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
            if row is None:
                raise KeyError(operation_id)
            record = json.loads(row[0])
            record.update(status=status, report_revision=report_revision, sources=sources,
                          deliveries=deliveries, error_code=error_code,
                          updated_at=datetime.now(timezone.utc).isoformat())
            connection.execute("UPDATE operations SET status=?,payload=? WHERE operation_id=?",
                               (status, json.dumps(record), operation_id))


    def _one(self, query: str, parameters: tuple = ()) -> dict | None:
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            row = connection.execute(query, parameters).fetchone()
            return json.loads(row[0]) if row else None

    def get(self, operation_id: str) -> dict | None:
        return self._one("SELECT payload FROM operations WHERE operation_id=?", (operation_id,))

    def by_key(self, request_id: str) -> dict | None:
        return self._one("SELECT payload FROM operations WHERE request_id=?", (request_id,))

    def current(self) -> dict | None:
        return self._one("SELECT payload FROM operations ORDER BY CASE WHEN status='running' THEN 0 ELSE 1 END, created_at DESC, operation_id DESC LIMIT 1")


    def recover_interrupted(self) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            for row in connection.execute("SELECT payload FROM operations WHERE status='running'").fetchall():
                record = json.loads(row[0])
                record.update(status="interrupted", error_code="operation_interrupted",
                              updated_at=datetime.now(timezone.utc).isoformat())
                for delivery in record["deliveries"].values():
                    if delivery["status"] == "pending":
                        delivery.update(status="unknown", error_code="delivery_unknown")
                connection.execute("UPDATE operations SET status=?,payload=? WHERE operation_id=?",
                                   (record["status"], json.dumps(record), record["operation_id"]))


    def record_delivery(self, operation_id: str, channel: str, outcome: dict) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
            if row is None:
                raise KeyError(operation_id)
            record = json.loads(row[0])
            if channel not in record["deliveries"]:
                raise KeyError(channel)
            record["deliveries"][channel] = outcome
            record["updated_at"] = datetime.now(timezone.utc).isoformat()
            connection.execute("UPDATE operations SET payload=? WHERE operation_id=?", (json.dumps(record), operation_id))


    def preview_metadata(self, report_date: str, revision: str) -> tuple[dict | None, dict]:
        sources = None
        deliveries = {"email": None, "lark": None}
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
            rows = connection.execute("SELECT payload FROM operations ORDER BY created_at DESC, operation_id DESC")
            for row in rows:
                record = json.loads(row[0])
                if record["report_date"] != report_date or record["report_revision"] != revision:
                    continue
                if record["kind"] == "generation" and sources is None:
                    sources = record["sources"]
                if record["kind"] == "delivery":
                    for channel, outcome in record["deliveries"].items():
                        if deliveries[channel] is None and outcome["status"] != "not_requested":
                            deliveries[channel] = outcome
        return sources, deliveries
