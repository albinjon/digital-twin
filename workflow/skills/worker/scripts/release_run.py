#!/usr/bin/env python3
"""Release a /worker lock and persist its run/action history in SQLite.

Usage: release_run.py --ticket KEY --exit-reason REASON [options]
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from runs import StateError, release_run


def _release_after_input_failure(ticket: str, exit_reason: str, role: str, owner_token: str | None, error: Exception) -> int:
    print(f"invalid release input: {error}", file=sys.stderr)
    if not owner_token:
        print("--owner-token is required for fail-safe cleanup", file=sys.stderr)
        return 2
    try:
        run_id = release_run(ticket, exit_reason, role, action_log=[], total_cost_usd=0.0, owner_token=owner_token)
    except Exception as cleanup_error:
        print(f"fail-safe cleanup failed: {cleanup_error}", file=sys.stderr)
        return 2
    print(f"RELEASED run_id={run_id} exit_reason={exit_reason} input_error=true")
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--exit-reason", required=True)
    parser.add_argument("--role", default="worker")
    parser.add_argument("--action-log", type=str)
    parser.add_argument("--total-cost-usd", type=float, default=0.0)
    parser.add_argument("--owner-token")
    args = parser.parse_args()
    try:
        action_log: list[dict[str, Any]] = []
        if args.action_log:
            with open(args.action_log, encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, list):
                raise ValueError("action log must be a JSON array")
            action_log = loaded
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        return _release_after_input_failure(args.ticket, args.exit_reason, args.role, args.owner_token, error)

    try:
        run_id = release_run(args.ticket, args.exit_reason, args.role, action_log, args.total_cost_usd, owner_token=args.owner_token)
    except StateError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"RELEASED run_id={run_id} exit_reason={args.exit_reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
