#!/usr/bin/env python3
"""Acquire the SQLite-backed /worker lock.

Usage: acquire_lock.py --ticket TICKET-KEY [--role ROLE]
"""
from __future__ import annotations

import argparse

from locks import StateError, acquire_lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--role", default="worker")
    args = parser.parse_args()
    try:
        token = acquire_lock(args.ticket, args.role)
    except StateError as error:
        print(str(error))
        return 1
    print(f"OWNER_TOKEN={token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
