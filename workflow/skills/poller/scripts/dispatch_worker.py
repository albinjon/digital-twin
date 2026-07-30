#!/usr/bin/env python3
"""Create one durable worker cron job from a cron-run poller.

Hermes intentionally withholds the cronjob agent tool from cron sessions to
prevent recursive scheduling. This wrapper uses the scheduler's CLI directly,
with argv (not a shell), and emits a machine-readable result. It is safe to
invoke from the poller through terminal.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any

TICKET_RE = re.compile(r"^[A-Z][A-Z0-9_]*-[0-9]+$")


def dispatch(ticket: str, *, schedule: str = "5m", deliver: str = "origin") -> dict[str, Any]:
    if not TICKET_RE.fullmatch(ticket):
        return {"ok": False, "error": "invalid_ticket", "message": f"Invalid ticket key {ticket!r}; expected TEAM-123."}
    if not re.fullmatch(r"[0-9]+m", schedule):
        return {"ok": False, "error": "invalid_schedule", "message": f"Invalid schedule {schedule!r}; expected a duration such as 5m."}
    name = f"worker-{ticket}"
    command = [
        "hermes", "cron", "create", schedule, ticket,
        "--name", name,
        "--skill", "worker",
        "--repeat", "1",
        "--deliver", deliver,
    ]
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode:
        return {"ok": False, "error": "scheduler_failed", "returncode": proc.returncode, "command": command, "output": output}
    match = re.search(r"Created job:\s*([A-Za-z0-9_-]+)", output)
    if not match:
        return {"ok": False, "error": "scheduler_unparseable", "command": command, "output": output, "message": "Hermes returned success but no durable job ID was found."}
    return {"ok": True, "job_id": match.group(1), "ticket": ticket, "name": name, "schedule": schedule, "command": command, "output": output}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--schedule", default="5m")
    parser.add_argument("--deliver", default="origin")
    args = parser.parse_args()
    result = dispatch(args.ticket, schedule=args.schedule, deliver=args.deliver)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
