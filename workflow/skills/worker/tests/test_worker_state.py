from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from worker_state import (
    StateError,
    acquire_lock,
    connect,
    get_review_target,
    list_review_candidates,
    list_unresolved_findings,
    refresh_lock,
    record_review,
    replace_review_findings,
    release_run,
    review_needed,
    upsert_review_target,
)


class WorkerStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tempdir.name) / "worker-state.db")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_lock_and_cooldown_are_atomic(self) -> None:
        owner = acquire_lock("VER-1", path=self.db)
        self.assertTrue(owner)
        with self.assertRaisesRegex(StateError, "ACTIVE_RUN_LOCK_HELD"):
            acquire_lock("VER-1", path=self.db)

        run_id = release_run(
            "VER-1",
            "stop:done",
            action_log=[
                {
                    "action": {"kind": "stop", "args": {"reason": "done"}},
                    "result": {"ok": True},
                    "cost_usd": 0.12,
                }
            ],
            total_cost_usd=0.12,
            owner_token=owner,
            path=self.db,
        )
        self.assertTrue(run_id)
        with self.assertRaisesRegex(StateError, "COOLDOWN_ACTIVE"):
            acquire_lock("VER-1", path=self.db)

        connection = connect(self.db)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 1)
            action = connection.execute(
                "SELECT action_kind, result_json FROM actions WHERE run_id = ?", (run_id,)
            ).fetchone()
            self.assertEqual(action["action_kind"], "stop")
            self.assertEqual(json.loads(action["result_json"])["ok"], True)
        finally:
            connection.close()

    def test_stale_lock_is_reclaimed(self) -> None:
        connection = connect(self.db)
        connection.execute(
            "INSERT INTO worker_locks VALUES (?, ?, ?, ?, ?)",
            ("LAV-1", "worker", "stale", "2020-01-01T00:00:00Z", "2020-01-01T01:00:00Z"),
        )
        connection.commit()
        connection.close()
        self.assertTrue(acquire_lock("LAV-1", path=self.db))

    def test_late_owner_cannot_release_replacement_lock(self) -> None:
        first = acquire_lock("VER-2", path=self.db, ttl_hours=0)
        second = acquire_lock("VER-2", path=self.db, cooldown_minutes=0)
        with self.assertRaisesRegex(StateError, "LOCK_NOT_OWNED"):
            release_run("VER-2", "late", owner_token=first, path=self.db)
        connection = connect(self.db)
        try:
            row = connection.execute(
                "SELECT owner_token FROM worker_locks WHERE ticket = ?", ("VER-2",)
            ).fetchone()
            self.assertEqual(row["owner_token"], second)
        finally:
            connection.close()

    def test_lock_can_be_refreshed_only_by_owner(self) -> None:
        owner = acquire_lock("VER-3", path=self.db)
        with self.assertRaisesRegex(StateError, "LOCK_NOT_OWNED"):
            refresh_lock("VER-3", "worker", "wrong", path=self.db)
        self.assertTrue(refresh_lock("VER-3", "worker", owner, path=self.db))

    def test_owner_cannot_release_after_lock_disappears(self) -> None:
        owner = acquire_lock("VER-4", path=self.db)
        connection = connect(self.db)
        connection.execute("DELETE FROM worker_locks WHERE ticket = ?", ("VER-4",))
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(StateError, "LOCK_NOT_OWNED"):
            release_run("VER-4", "late", owner_token=owner, path=self.db)

    def test_missing_review_target_is_an_error(self) -> None:
        with self.assertRaisesRegex(StateError, "REVIEW_TARGET_NOT_FOUND"):
            record_review(repo="org/web", pr_number=99, reviewed_sha="abc", status="approved", path=self.db)

    def test_exit_cli_releases_owned_lock_on_malformed_action_log(self) -> None:
        owner = acquire_lock("VER-5", path=self.db)
        script = Path(__file__).resolve().parents[1] / "scripts" / "release_run.py"
        env = os.environ.copy()
        env["HERMES_HOME"] = self.tempdir.name
        result = subprocess.run(
            [sys.executable, str(script), "--ticket", "VER-5", "--exit-reason", "malformed", "--role", "worker", "--action-log", str(Path(self.tempdir.name) / "missing.json"), "--total-cost-usd", "0", "--owner-token", owner],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        connection = connect(self.db)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM worker_locks").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 1)
        finally:
            connection.close()

    def test_findings_are_replaced_and_unresolved_candidates_are_listed(self) -> None:
        target_id = upsert_review_target(
            ticket="ZBS-2", repo="org/web", pr_number=8, current_sha="abc", path=self.db
        )
        replace_review_findings(
            target_id,
            [{"external_thread_id": "t1", "severity": "blocking", "status": "unresolved", "summary": "bug"}],
            path=self.db,
        )
        self.assertEqual(len(list_unresolved_findings(target_id, path=self.db)), 1)
        self.assertEqual(list_review_candidates(path=self.db)[0]["pr_number"], 8)

    def test_review_is_keyed_by_pr_head_sha(self) -> None:
        upsert_review_target(
            ticket="APPAI-1", repo="skry-ab/appraisal", pr_number=12, path=self.db
        )
        self.assertTrue(review_needed("skry-ab/appraisal", 12, "abc", path=self.db))
        record_review(
            repo="skry-ab/appraisal",
            pr_number=12,
            reviewed_sha="abc",
            status="approved",
            path=self.db,
        )
        self.assertFalse(review_needed("skry-ab/appraisal", 12, "abc", path=self.db))
        self.assertTrue(review_needed("skry-ab/appraisal", 12, "def", path=self.db))
        target = get_review_target("skry-ab/appraisal", 12, path=self.db)
        self.assertEqual(target["last_reviewed_sha"], "abc")
        self.assertEqual(target["review_status"], "approved")

    def test_review_request_is_upserted_per_pr(self) -> None:
        first = upsert_review_target(
            ticket="ZBS-1", repo="org/web", pr_number=7, current_sha="a", path=self.db
        )
        second = upsert_review_target(
            ticket="ZBS-1", repo="org/web", pr_number=7, current_sha="b", path=self.db
        )
        self.assertEqual(first, second)
        target = get_review_target("org/web", 7, path=self.db)
        self.assertEqual(target["current_sha"], "b")
        connection = connect(self.db)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM review_targets").fetchone()[0], 1)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
