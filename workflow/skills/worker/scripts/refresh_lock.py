#!/usr/bin/env python3
"""Refresh an owned SQLite worker lock.

Usage: refresh_lock.py --ticket TICKET-KEY --owner-token TOKEN [--role ROLE]
"""
from __future__ import annotations

import argparse

from locks import StateError, refresh_lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--owner-token", required=True)
    parser.add_argument("--role", default="worker")
    args = parser.parse_args()
    try:
        expires_at = refresh_lock(args.ticket, args.role, args.owner_token)
    except StateError as error:
        print(str(error))
        return 1
    print(f"EXPIRES_AT={expires_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
