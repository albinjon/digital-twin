#!/usr/bin/env python3
"""Shared SQLite connection, schema, timestamp, and error primitives."""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any

DEFAULT_COOLDOWN_MINUTES = 15
DEFAULT_LOCK_TTL_HOURS = 6
DEFAULT_BUSY_TIMEOUT_SECONDS = 10
MAX_RUNS = 500

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS worker_locks (
    ticket TEXT NOT NULL, role TEXT NOT NULL, owner_token TEXT NOT NULL,
    started_at TEXT NOT NULL, expires_at TEXT NOT NULL,
    PRIMARY KEY (ticket, role)
);
CREATE TABLE IF NOT EXISTS cooldowns (ticket TEXT PRIMARY KEY, last_exit_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, ticket TEXT NOT NULL, role TEXT NOT NULL,
    started_at TEXT NOT NULL, ended_at TEXT NOT NULL, exit_reason TEXT NOT NULL,
    total_cost_usd REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_ticket_created ON runs(ticket, created_at DESC);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL, action_kind TEXT NOT NULL, action_json TEXT NOT NULL,
    result_json TEXT, cost_usd REAL, created_at TEXT NOT NULL,
    UNIQUE(run_id, sequence)
);
CREATE TABLE IF NOT EXISTS review_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ticket TEXT NOT NULL, repo TEXT NOT NULL,
    pr_number INTEGER NOT NULL, current_sha TEXT, last_reviewed_sha TEXT,
    review_status TEXT NOT NULL DEFAULT 'requested', blocking_findings INTEGER NOT NULL DEFAULT 0,
    non_blocking_findings INTEGER NOT NULL DEFAULT 0, unresolved_findings INTEGER NOT NULL DEFAULT 0,
    github_review_id TEXT, payload_url TEXT, updated_at TEXT NOT NULL,
    UNIQUE(repo, pr_number)
);
CREATE INDEX IF NOT EXISTS idx_review_targets_queue ON review_targets(review_status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_review_targets_ticket ON review_targets(ticket);
CREATE TABLE IF NOT EXISTS review_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_target_id INTEGER NOT NULL REFERENCES review_targets(id) ON DELETE CASCADE,
    external_thread_id TEXT NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL,
    path TEXT, line INTEGER, summary TEXT, created_at TEXT NOT NULL, resolved_at TEXT,
    UNIQUE(review_target_id, external_thread_id)
);
CREATE INDEX IF NOT EXISTS idx_review_findings_unresolved
    ON review_findings(review_target_id, status, severity);
"""


class StateError(RuntimeError):
    def __init__(self, code: str, **details: Any):
        self.code = code
        self.details = details
        detail_text = " ".join(f"{key}={value}" for key, value in details.items())
        super().__init__(f"{code}{(' ' + detail_text) if detail_text else ''}")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime | None = None) -> str:
    return (value or utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def db_path() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")) / "worker-state.db"


def connect(path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    target = Path(path) if path else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=DEFAULT_BUSY_TIMEOUT_SECONDS, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {DEFAULT_BUSY_TIMEOUT_SECONDS * 1000}")
    connection.executescript(SCHEMA)
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(worker_locks)")}
    if "owner_token" not in columns:
        connection.execute("ALTER TABLE worker_locks ADD COLUMN owner_token TEXT")
        connection.execute("UPDATE worker_locks SET owner_token = ? WHERE owner_token IS NULL", ("legacy-" + uuid.uuid4().hex,))
    connection.execute(
        "INSERT INTO schema_meta(key, value) VALUES ('schema_version', '2') "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    )
    return connection
