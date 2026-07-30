#!/usr/bin/env python3
"""Validate an action log, sum costs, and release a worker run atomically."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from runs import StateError, release_run  # noqa: E402


def validate_action_log(value: Any) -> tuple[list[dict[str, Any]], float, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return [], 0.0, [{"path": "$", "code": "type", "message": "Action log must be a JSON array.", "expected": "array[object]"}]
    total = 0.0
    for index, entry in enumerate(value):
        path = f"$[{index}]"
        if not isinstance(entry, dict):
            errors.append({"path": path, "code": "type", "message": "Action log entries must be objects.", "expected": "object"})
            continue
        action = entry.get("action", entry)
        if not isinstance(action, dict) or not isinstance(action.get("kind"), str):
            errors.append({"path": f"{path}.action.kind", "code": "required", "message": "Each action log entry requires action.kind.", "expected": "string"})
        cost = entry.get("cost_usd", 0.0)
        if cost is None:
            cost = 0.0
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(float(cost)) or float(cost) < 0:
            errors.append({"path": f"{path}.cost_usd", "code": "type", "message": "cost_usd must be a finite non-negative number.", "expected": "number >= 0", "received": cost})
        else:
            total += float(cost)
    return value if not errors else [], total, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--exit-reason", required=True)
    parser.add_argument("--owner-token", required=True)
    parser.add_argument("--action-log", required=True)
    parser.add_argument("--db")
    args = parser.parse_args()
    try:
        value = json.loads(Path(args.action_log).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": "invalid_action_log_json", "message": str(exc)}))
        return 2
    action_log, total, errors = validate_action_log(value)
    if errors:
        print(json.dumps({"ok": False, "error": "invalid_action_log", "errors": errors}, ensure_ascii=False, sort_keys=True))
        return 2
    try:
        run_id = release_run(args.ticket, args.exit_reason, "worker", action_log, total, owner_token=args.owner_token, path=args.db)
    except StateError as exc:
        print(json.dumps({"ok": False, "error": "state_release_failed", "message": str(exc)}, sort_keys=True))
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "unexpected_release_failure", "message": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, "run_id": run_id, "ticket": args.ticket, "exit_reason": args.exit_reason, "total_cost_usd": total}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
