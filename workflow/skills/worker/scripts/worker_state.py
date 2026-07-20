#!/usr/bin/env python3
"""Compatibility facade for the worker state modules.

New code should import from state_db, locks, runs, or reviews directly. This
facade preserves the existing worker/test imports during the refactor.
"""
from __future__ import annotations

import argparse
import sys

from state_db import (  # noqa: F401
    DEFAULT_BUSY_TIMEOUT_SECONDS,
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_LOCK_TTL_HOURS,
    MAX_RUNS,
    StateError,
    connect,
    db_path,
    iso,
    parse_iso,
    utc_now,
)
from locks import acquire_lock, refresh_lock  # noqa: F401
from runs import release_run  # noqa: F401
from reviews import (  # noqa: F401
    get_review_target,
    list_review_candidates,
    list_unresolved_findings,
    record_review,
    replace_review_findings,
    review_needed,
    upsert_review_target,
)


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="override SQLite path")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create or upgrade the SQLite schema")
    init.set_defaults(handler=lambda args: (connect(args.db).close(), print(args.db or db_path()), 0)[-1])
    args = parser.parse_args()
    return args.handler(args) if hasattr(args, "handler") else 0


if __name__ == "__main__":
    sys.exit(_cli())
