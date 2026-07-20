#!/usr/bin/env python3
"""Review target, finding, and review-queue persistence."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

from state_db import connect, iso, StateError


def upsert_review_target(*, ticket: str, repo: str, pr_number: int, current_sha: str | None = None,
                         review_status: str = "requested", blocking_findings: int = 0,
                         non_blocking_findings: int = 0, unresolved_findings: int = 0,
                         github_review_id: str | None = None, payload_url: str | None = None,
                         path: str | os.PathLike[str] | None = None) -> int:
    connection = connect(path)
    updated_at = iso()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO review_targets(ticket, repo, pr_number, current_sha, review_status, blocking_findings, non_blocking_findings, unresolved_findings, github_review_id, payload_url, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(repo, pr_number) DO UPDATE SET ticket=excluded.ticket, current_sha=COALESCE(excluded.current_sha, review_targets.current_sha), review_status=excluded.review_status, blocking_findings=excluded.blocking_findings, non_blocking_findings=excluded.non_blocking_findings, unresolved_findings=excluded.unresolved_findings, github_review_id=COALESCE(excluded.github_review_id, review_targets.github_review_id), payload_url=COALESCE(excluded.payload_url, review_targets.payload_url), updated_at=excluded.updated_at",
            (ticket, repo, pr_number, current_sha, review_status, blocking_findings, non_blocking_findings, unresolved_findings, github_review_id, payload_url, updated_at),
        )
        row = connection.execute("SELECT id FROM review_targets WHERE repo = ? AND pr_number = ?", (repo, pr_number)).fetchone()
        connection.commit()
        return int(row["id"])
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def record_review(*, repo: str, pr_number: int, reviewed_sha: str, status: str,
                  blocking_findings: int = 0, non_blocking_findings: int = 0,
                  unresolved_findings: int = 0, github_review_id: str | None = None,
                  payload_url: str | None = None, path: str | os.PathLike[str] | None = None) -> None:
    connection = connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        result = connection.execute(
            "UPDATE review_targets SET last_reviewed_sha = ?, current_sha = ?, review_status = ?, blocking_findings = ?, non_blocking_findings = ?, unresolved_findings = ?, github_review_id = COALESCE(?, github_review_id), payload_url = COALESCE(?, payload_url), updated_at = ? WHERE repo = ? AND pr_number = ?",
            (reviewed_sha, reviewed_sha, status, blocking_findings, non_blocking_findings, unresolved_findings, github_review_id, payload_url, iso(), repo, pr_number),
        )
        if result.rowcount != 1:
            raise StateError("REVIEW_TARGET_NOT_FOUND", repo=repo, pr_number=pr_number)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def review_needed(repo: str, pr_number: int, current_sha: str, *, path: str | os.PathLike[str] | None = None) -> bool:
    connection = connect(path)
    try:
        row = connection.execute("SELECT last_reviewed_sha FROM review_targets WHERE repo = ? AND pr_number = ?", (repo, pr_number)).fetchone()
        return row is None or row["last_reviewed_sha"] != current_sha
    finally:
        connection.close()


def get_review_target(repo: str, pr_number: int, *, path: str | os.PathLike[str] | None = None) -> dict[str, Any] | None:
    connection = connect(path)
    try:
        row = connection.execute("SELECT * FROM review_targets WHERE repo = ? AND pr_number = ?", (repo, pr_number)).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def replace_review_findings(target_id: int, findings: Iterable[dict[str, Any]], *, path: str | os.PathLike[str] | None = None) -> None:
    connection = connect(path)
    now = iso()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM review_findings WHERE review_target_id = ?", (target_id,))
        for finding in findings:
            connection.execute(
                "INSERT INTO review_findings(review_target_id, external_thread_id, severity, status, path, line, summary, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (target_id, finding["external_thread_id"], finding.get("severity", "non_blocking"), finding.get("status", "unresolved"), finding.get("path"), finding.get("line"), finding.get("summary"), now),
            )
        connection.execute(
            "UPDATE review_targets SET blocking_findings = (SELECT COUNT(*) FROM review_findings WHERE review_target_id = ? AND severity = 'blocking'), non_blocking_findings = (SELECT COUNT(*) FROM review_findings WHERE review_target_id = ? AND severity != 'blocking'), unresolved_findings = (SELECT COUNT(*) FROM review_findings WHERE review_target_id = ? AND status != 'resolved'), updated_at = ? WHERE id = ?",
            (target_id, target_id, target_id, now, target_id),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def list_unresolved_findings(target_id: int, *, path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    connection = connect(path)
    try:
        rows = connection.execute("SELECT * FROM review_findings WHERE review_target_id = ? AND status != 'resolved' ORDER BY id", (target_id,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def list_review_candidates(*, limit: int = 50, path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    connection = connect(path)
    try:
        rows = connection.execute("SELECT * FROM review_targets WHERE last_reviewed_sha IS NULL OR current_sha IS NULL OR current_sha != last_reviewed_sha ORDER BY updated_at ASC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()
