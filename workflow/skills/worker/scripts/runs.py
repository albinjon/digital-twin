#!/usr/bin/env python3
"""Run history persistence and owner-conditional lock release."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Iterable

from state_db import MAX_RUNS, connect, iso, StateError


def release_run(
    ticket: str,
    exit_reason: str,
    role: str = "worker",
    action_log: Iterable[dict[str, Any]] = (),
    total_cost_usd: float = 0.0,
    *,
    owner_token: str | None = None,
    path: str | os.PathLike[str] | None = None,
) -> str:
    """Release the owned lock, persist history, and set cooldown atomically."""
    connection = connect(path)
    ended_at = iso()
    run_id = str(uuid.uuid4())
    actions = list(action_log)
    try:
        connection.execute("BEGIN IMMEDIATE")
        lock = connection.execute(
            "SELECT owner_token, started_at FROM worker_locks WHERE ticket = ? AND role = ?", (ticket, role)
        ).fetchone()
        if lock and not owner_token:
            raise StateError("OWNER_TOKEN_REQUIRED")
        if owner_token and (not lock or lock["owner_token"] != owner_token):
            raise StateError("LOCK_NOT_OWNED")
        started_at = lock["started_at"] if lock else ended_at
        if lock:
            connection.execute(
                "DELETE FROM worker_locks WHERE ticket = ? AND role = ? AND owner_token = ?",
                (ticket, role, owner_token),
            )
        connection.execute(
            "INSERT INTO runs(id, ticket, role, started_at, ended_at, exit_reason, total_cost_usd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, ticket, role, started_at, ended_at, exit_reason, total_cost_usd, ended_at),
        )
        for sequence, action in enumerate(actions):
            action_obj = action.get("action", action)
            result_obj = action.get("result")
            connection.execute(
                "INSERT INTO actions(run_id, sequence, action_kind, action_json, result_json, cost_usd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, sequence, str(action_obj.get("kind", "unknown")), json.dumps(action_obj, sort_keys=True),
                 json.dumps(result_obj, sort_keys=True) if result_obj is not None else None,
                 action.get("cost_usd"), ended_at),
            )
        connection.execute(
            "INSERT INTO cooldowns(ticket, last_exit_at) VALUES (?, ?) ON CONFLICT(ticket) DO UPDATE SET last_exit_at = excluded.last_exit_at",
            (ticket, ended_at),
        )
        connection.execute(
            "DELETE FROM runs WHERE id IN (SELECT id FROM runs ORDER BY created_at DESC LIMIT -1 OFFSET ?)",
            (MAX_RUNS,),
        )
        connection.commit()
        return run_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
