#!/usr/bin/env python3
"""Idempotently import the legacy run-table.json into worker-state.db."""
from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path

from state_db import connect, db_path


def migrate(source: Path, destination: Path) -> dict[str, int | str]:
    raw = source.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("legacy state must be a JSON object")
    connection = connect(destination)
    counts = {"cooldowns": 0, "locks": 0, "runs": 0, "actions": 0}
    marker = f"legacy_run_table:{source_hash}"
    try:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT 1 FROM schema_meta WHERE key = ?", (marker,)).fetchone():
            connection.rollback()
            return {**counts, "source_sha256": source_hash, "already_imported": "true"}

        for ticket, last_exit_at in data.get("cooldowns", {}).items():
            connection.execute(
                "INSERT INTO cooldowns(ticket, last_exit_at) VALUES (?, ?) "
                "ON CONFLICT(ticket) DO UPDATE SET last_exit_at = MAX(cooldowns.last_exit_at, excluded.last_exit_at)",
                (ticket, last_exit_at),
            )
            counts["cooldowns"] += 1
        for key, lock in data.get("active_runs", {}).items():
            ticket, _, role = key.partition(":")
            if not ticket or not role:
                continue
            owner = "legacy-" + hashlib.sha256(f"{source_hash}:{key}".encode()).hexdigest()[:32]
            connection.execute(
                "INSERT INTO worker_locks(ticket, role, owner_token, started_at, expires_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(ticket, role) DO NOTHING",
                (ticket, role, owner, lock["started_at"], lock["expires_at"]),
            )
            counts["locks"] += 1
        for run in data.get("runs", []):
            identity = {
                "ticket": run["ticket"],
                "role": run.get("role", "worker"),
                "started_at": run["started_at"],
                "ended_at": run["ended_at"],
                "exit_reason": run["exit_reason"],
            }
            run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "legacy-run:" + json.dumps(identity, sort_keys=True)))
            connection.execute(
                "INSERT OR IGNORE INTO runs(id, ticket, role, started_at, ended_at, exit_reason, total_cost_usd, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, run["ticket"], run.get("role", "worker"), run["started_at"], run["ended_at"],
                 run["exit_reason"], run.get("total_cost_usd", 0.0), run["ended_at"]),
            )
            if connection.execute("SELECT changes()").fetchone()[0]:
                counts["runs"] += 1
            for sequence, action in enumerate(run.get("action_log", [])):
                action_obj = action.get("action", action)
                result_obj = action.get("result")
                cur = connection.execute(
                    "INSERT OR IGNORE INTO actions(run_id, sequence, action_kind, action_json, result_json, cost_usd, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (run_id, sequence, action_obj.get("kind", "unknown"), json.dumps(action_obj, sort_keys=True),
                     json.dumps(result_obj, sort_keys=True) if result_obj is not None else None,
                     action.get("cost_usd"), run["ended_at"]),
                )
                if cur.rowcount:
                    counts["actions"] += 1
        connection.execute(
            "INSERT INTO schema_meta(key, value) VALUES (?, ?)",
            (marker, json.dumps({"source": str(source), "sha256": source_hash})),
        )
        connection.commit()
        return {**counts, "source_sha256": source_hash, "already_imported": "false"}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> int:
    home = Path(__import__("os").environ.get("HERMES_HOME", Path.home() / ".hermes"))
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=home / "run-table.json")
    parser.add_argument("--destination", type=Path, default=db_path())
    args = parser.parse_args()
    if not args.source.exists():
        print(f"source not found: {args.source}")
        return 1
    print(json.dumps(migrate(args.source, args.destination), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
