#!/usr/bin/env python3
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

WORKER_SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
POLLER_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "poller" / "scripts"
sys.path.insert(0, str(WORKER_SCRIPT_DIR))
sys.path.insert(0, str(POLLER_SCRIPT_DIR))
from action_payload import validate_action  # noqa: E402
from dispatch_worker import dispatch  # noqa: E402
from prepare_worktree import prepare  # noqa: E402
from normalize_reasoner_result import normalize_envelope  # noqa: E402
from preflight import preflight  # noqa: E402
from finalize_run import validate_action_log  # noqa: E402
from github_payload import validate_github_payload  # noqa: E402


class ActionPayloadTests(unittest.TestCase):
    def test_valid_start_implementation(self) -> None:
        result = validate_action({
            "kind": "start_implementation",
            "args": {"branch_name": "feature/zbs-1-example", "task_spec": "Implement the change."},
            "reason": "The ticket is clear.",
        })
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["errors"], [])

    def test_reports_missing_field_with_expected_structure(self) -> None:
        result = validate_action({
            "kind": "start_implementation",
            "args": {"title": "wrong alias"},
            "reason": "Try implementation.",
        })
        self.assertFalse(result["valid"])
        paths = {error["path"] for error in result["errors"]}
        self.assertIn("args.branch_name", paths)
        self.assertIn("args.task_spec", paths)
        alias_error = next(error for error in result["errors"] if error["path"] == "args.title")
        self.assertEqual(alias_error["code"], "additional_property")
        self.assertEqual(alias_error["expected"], {"branch_name": "string", "task_spec": "string"})

    def test_reports_wrong_type_and_invalid_enum(self) -> None:
        result = validate_action({
            "kind": "move_state",
            "args": {"state": "Finished", "comment": 123},
            "reason": "Move it.",
        })
        self.assertFalse(result["valid"])
        self.assertTrue(any(error["path"] == "args.state" and error["code"] == "enum" for error in result["errors"]))
        self.assertTrue(any(error["path"] == "args.comment" and error["code"] == "type" for error in result["errors"]))

    def test_rejects_unknown_top_level_field(self) -> None:
        result = validate_action({"kind": "stop", "args": {"reason": "done"}, "reason": "done", "task": "wrong"})
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["path"], "task")


class DispatchWorkerTests(unittest.TestCase):
    @patch("dispatch_worker.subprocess.run")
    def test_dispatch_uses_argv_and_returns_job_id(self, run) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Created job: worker-ZBS-123\n", stderr=""
        )
        result = dispatch("ZBS-123")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["job_id"], "worker-ZBS-123")
        command = run.call_args.args[0]
        self.assertIsInstance(command, list)
        self.assertIn("cron", command)
        self.assertIn("worker", command)

    def test_dispatch_rejects_bad_ticket_without_running_scheduler(self) -> None:
        with patch("dispatch_worker.subprocess.run") as run:
            result = dispatch("not-a-ticket")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid_ticket")
        run.assert_not_called()

    @patch("prepare_worktree.subprocess.run")
    def test_prepare_worktree_uses_separate_argv_git_calls(self, run) -> None:
        run.side_effect = [
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]
        with __import__("tempfile").TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            result = prepare(str(repo), str(Path(directory) / "worktree"), "feature/ZBS-1-example")
        self.assertTrue(result["ok"], result)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][:4], ["git", "-C", str(repo), "fetch"])
        self.assertEqual(run.call_args_list[1].args[0][:4], ["git", "-C", str(repo), "worktree"])

    def test_prepare_worktree_refuses_existing_path(self) -> None:
        with __import__("tempfile").TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            worktree = Path(directory) / "worktree"
            repo.mkdir()
            worktree.mkdir()
            with patch("prepare_worktree.subprocess.run") as run:
                result = prepare(str(repo), str(worktree), "feature/ZBS-1-example")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "worktree_exists")
        run.assert_not_called()

    def test_normalizes_structured_output_and_preserves_cost(self) -> None:
        result = normalize_envelope({
            "structured_output": {"kind": "stop", "args": {"reason": "done"}, "reason": "done"},
            "total_cost_usd": 0.12,
        })
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["source"], "structured_output")
        self.assertEqual(result["total_cost_usd"], 0.12)

    def test_normalizes_one_fenced_result(self) -> None:
        result = normalize_envelope({
            "result": """```json
{"kind":"stop","args":{"reason":"done"},"reason":"done"}
```"""
        })
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["action"]["kind"], "stop")

    def test_rejects_prose_and_missing_envelope_fields(self) -> None:
        result = normalize_envelope({"result": "Here is the action: {\"kind\":\"stop\"}"})
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "invalid_json")

    def test_rejects_multiple_top_level_action_fields(self) -> None:
        result = normalize_envelope({"structured_output": {"kind": "stop", "args": {}, "reason": "x", "extra": True}})
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["code"], "additional_property")

    def test_preflight_reports_missing_repository_without_linear_mutation(self) -> None:
        result = preflight("/root/does-not-exist", require_claude=False)
        self.assertFalse(result["ok"])
        self.assertTrue(any(error["code"] == "repo_missing" for error in result["errors"]))

    def test_finalize_validates_and_sums_action_costs(self) -> None:
        log, total, errors = validate_action_log([
            {"action": {"kind": "start_implementation"}, "cost_usd": 0.25},
            {"action": {"kind": "run_tests"}, "cost_usd": 0.75},
        ])
        self.assertEqual(len(log), 2)
        self.assertEqual(total, 1.0)
        self.assertEqual(errors, [])

    def test_finalize_rejects_bad_cost_without_guessing(self) -> None:
        log, total, errors = validate_action_log([
            {"action": {"kind": "stop"}, "cost_usd": "0.5"},
        ])
        self.assertEqual(log, [])
        self.assertEqual(total, 0.0)
        self.assertEqual(errors[0]["path"], "$[0].cost_usd")

    def test_github_lookup_requires_owner_repo_and_path(self) -> None:
        result = validate_github_payload("get_file_contents", {"path": "src/app.ts"})
        self.assertFalse(result["valid"])
        self.assertEqual({error["path"] for error in result["errors"]}, {"owner", "repo"})

    def test_github_lookup_accepts_valid_pull_request_payload(self) -> None:
        result = validate_github_payload("get_pull_request", {"owner": "Zenbuddhistiska-Samfundet", "repo": "web", "pull_number": 114})
        self.assertTrue(result["valid"], result)


if __name__ == "__main__":
    unittest.main()
