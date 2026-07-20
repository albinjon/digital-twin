#!/usr/bin/env python3
"""Ticket lock acquisition and owner-token lease refresh."""
from __future__ import annotations

import datetime as dt
import os
import uuid
from pathlib import Path

from state_db import (
    DEFAULT_COOLDOWN_MINUTES,
    DEFAULT_LOCK_TTL_HOURS,
    connect,
    iso,
    parse_iso,
    StateError,
    utc_now,
)


def acquire_lock(
    ticket: str,
    role: str = "worker",
    *,
    path: str | os.PathLike[str] | None = None,
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
    ttl_hours: int = DEFAULT_LOCK_TTL_HOURS,
) -> str:
    """Acquire a lock and return its opaque owner token."""
    connection = connect(path)
    now = utc_now()
    owner_token = uuid.uuid4().hex
    started_at = iso(now)
    expires_at = iso(now + dt.timedelta(hours=ttl_hours))
    try:
        connection.execute("BEGIN IMMEDIATE")
        cooldown = connection.execute("SELECT last_exit_at FROM cooldowns WHERE ticket = ?", (ticket,)).fetchone()
        if cooldown:
            elapsed = (now - parse_iso(cooldown["last_exit_at"])).total_seconds() / 60
            if elapsed < cooldown_minutes:
                raise StateError("COOLDOWN_ACTIVE", remaining_min=f"{cooldown_minutes - elapsed:.1f}")
        existing = connection.execute(
            "SELECT expires_at FROM worker_locks WHERE ticket = ? AND role = ?", (ticket, role)
        ).fetchone()
        if existing and parse_iso(existing["expires_at"]) > now:
            raise StateError("ACTIVE_RUN_LOCK_HELD", expires_at=existing["expires_at"])
        connection.execute(
            "INSERT OR REPLACE INTO worker_locks(ticket, role, owner_token, started_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (ticket, role, owner_token, started_at, expires_at),
        )
        connection.commit()
        return owner_token
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def refresh_lock(
    ticket: str,
    role: str,
    owner_token: str,
    *,
    path: str | os.PathLike[str] | None = None,
    ttl_hours: int = DEFAULT_LOCK_TTL_HOURS,
) -> str:
    connection = connect(path)
    expires_at = iso(utc_now() + dt.timedelta(hours=ttl_hours))
    try:
        connection.execute("BEGIN IMMEDIATE")
        result = connection.execute(
            "UPDATE worker_locks SET expires_at = ? WHERE ticket = ? AND role = ? AND owner_token = ?",
            (expires_at, ticket, role, owner_token),
        )
        if result.rowcount != 1:
            raise StateError("LOCK_NOT_OWNED")
        connection.commit()
        return expires_at
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
