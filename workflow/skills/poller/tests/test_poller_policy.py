from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from poller_policy import Candidate, DEFAULT_RULES, PolicyContext, parse_scope, select_candidate  # noqa: E402


CANDIDATES = [
    {"identifier": "ZBS-1", "state": "Todo", "labels": [], "created_at": "2026-07-20T12:00:00Z"},
    {"identifier": "ZBS-2", "state": "Todo", "labels": [], "created_at": "2026-07-20T12:05:00Z"},
]


class PollerPolicyTests(unittest.TestCase):
    def test_empty_scope_means_all_authorized_prefixes(self) -> None:
        self.assertEqual(parse_scope(None, ["zbs", "APPAI"]), {"ZBS", "APPAI"})

    def test_scope_cannot_authorize_unknown_prefix(self) -> None:
        self.assertEqual(parse_scope("ZBS,EVIL", ["ZBS"]), {"ZBS"})

    def test_selects_newest_eligible_ticket(self) -> None:
        result = select_candidate(CANDIDATES, allowed_prefixes=["ZBS"], now="2026-07-20T13:00:00Z")
        self.assertIsNotNone(result.selected)
        self.assertEqual(result.selected.identifier, "ZBS-2")

    def test_rejects_non_todo_human_locked_and_cooled_tickets(self) -> None:
        candidates = [
            {"identifier": "ZBS-1", "state": "In Progress", "labels": [], "created_at": "2026-07-20T12:10:00Z"},
            {"identifier": "ZBS-2", "state": "Todo", "labels": ["Human"], "created_at": "2026-07-20T12:09:00Z"},
            {"identifier": "ZBS-3", "state": "Todo", "labels": [], "created_at": "2026-07-20T12:08:00Z"},
            {"identifier": "ZBS-4", "state": "Todo", "labels": [], "created_at": "2026-07-20T12:07:00Z"},
        ]
        result = select_candidate(
            candidates,
            allowed_prefixes=["ZBS"],
            active_locks={"ZBS-3:worker": {"expires_at": "2026-07-20T14:00:00Z"}},
            cooldowns={"ZBS-4": "2026-07-20T12:55:00Z"},
            now="2026-07-20T13:00:00Z",
        )
        self.assertIsNone(result.selected)
        self.assertEqual(result.skipped["ZBS-1"], "not-todo")
        self.assertEqual(result.skipped["ZBS-2"], "human-label")
        self.assertEqual(result.skipped["ZBS-3"], "active-lock")
        self.assertEqual(result.skipped["ZBS-4"], "cooldown")

    def test_expired_lock_and_elapsed_cooldown_do_not_block(self) -> None:
        result = select_candidate(
            CANDIDATES,
            allowed_prefixes=["ZBS"],
            active_locks={"ZBS-2:worker": "2026-07-20T12:00:00Z"},
            cooldowns={"ZBS-1": "2026-07-20T12:00:00Z"},
            now=datetime(2026, 7, 20, 13, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(result.selected)
        self.assertEqual(result.selected.identifier, "ZBS-2")

    def test_tie_break_is_stable_by_ticket_key(self) -> None:
        candidates = [
            {"identifier": "ZBS-2", "state": "Todo", "labels": [], "created_at": "2026-07-20T12:00:00Z"},
            {"identifier": "ZBS-1", "state": "Todo", "labels": [], "created_at": "2026-07-20T12:00:00Z"},
        ]
        result = select_candidate(candidates, allowed_prefixes=["ZBS"], now="2026-07-20T13:00:00Z")
        self.assertIsNotNone(result.selected)
        self.assertEqual(result.selected.identifier, "ZBS-1")

    def test_pydantic_normalizes_linear_key_and_rejects_bad_dates(self) -> None:
        result = select_candidate(
            [{"key": "ZBS-9", "state": "Todo", "labels": [{"name": "Routine"}], "created_at": "2026-07-20T12:00:00Z"}],
            allowed_prefixes=["ZBS"],
            now="2026-07-20T13:00:00Z",
        )
        self.assertIsNotNone(result.selected)
        self.assertEqual(result.selected.identifier, "ZBS-9")
        with self.assertRaises(ValidationError):
            select_candidate(
                [{"identifier": "ZBS-10", "state": "Todo", "created_at": "not-a-date"}],
                allowed_prefixes=["ZBS"],
                now="2026-07-20T13:00:00Z",
            )

    def test_custom_rule_can_be_added_without_editing_default_rules(self) -> None:
        def block_zbs_two(candidate: Candidate, context: PolicyContext) -> str | None:
            return "temporary-business-rule" if candidate.identifier == "ZBS-2" else None

        result = select_candidate(
            CANDIDATES,
            allowed_prefixes=["ZBS"],
            now="2026-07-20T13:00:00Z",
            rules=(block_zbs_two, *DEFAULT_RULES),
        )
        self.assertIsNotNone(result.selected)
        self.assertEqual(result.selected.identifier, "ZBS-1")
        self.assertEqual(result.skipped["ZBS-2"], "temporary-business-rule")

    def test_cli_returns_structured_selection(self) -> None:
        payload = {"candidates": CANDIDATES, "allowed_prefixes": ["ZBS"], "now": "2026-07-20T13:00:00Z"}
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "policy.json"
            input_path.write_text(json.dumps(payload))
            result = subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "poller_policy.py"), "--input", str(input_path)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["selected"]["identifier"], "ZBS-2")


if __name__ == "__main__":
    unittest.main()
