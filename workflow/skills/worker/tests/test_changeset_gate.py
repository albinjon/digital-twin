#!/usr/bin/env python3
import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from changeset_gate import GateError, commit_changes, inspect_worktree  # noqa: E402


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True)


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("base\n")
    subprocess.check_call(["git", "-C", str(repo), "add", "README.md"])
    subprocess.check_call(["git", "-C", str(repo), "commit", "-m", "base"])
    return repo


class ChangesetGateTests(unittest.TestCase):
    def test_inspect_rejects_detached_worktree(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            subprocess.check_call(
                ["git", "-C", str(repo), "checkout", "--detach", "HEAD"],
                stdout=subprocess.DEVNULL,
            )
            with self.assertRaisesRegex(GateError, "detached"):
                inspect_worktree(repo)

    def test_inspect_reports_only_actual_changes(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            (repo / "README.md").write_text("changed\n")
            result = inspect_worktree(repo)
            self.assertEqual(result["branch"], "main")
            self.assertEqual(result["changed_files"], ["README.md"])
            self.assertEqual(result["diff_check"], "passed")

    def test_commit_stages_only_inspected_paths(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            (repo / "README.md").write_text("changed\n")
            result = commit_changes(repo, "TEST-1", "fix: update readme", push=False)
            self.assertFalse(result["pushed"])
            self.assertEqual(git(repo, "log", "-1", "--format=%s").strip(), "fix: update readme")
            self.assertEqual(git(repo, "status", "--porcelain"), "")

    def test_commit_rejects_empty_changeset(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            repo = make_repo(Path(directory))
            with self.assertRaisesRegex(GateError, "empty changeset"):
                commit_changes(repo, "TEST-1", "fix: no-op", push=False)

    def test_error_cli_is_machine_readable(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            script = SCRIPT_DIR / "changeset_gate.py"
            proc = subprocess.run(
                [sys.executable, str(script), "inspect", "--worktree", str(Path(directory) / "missing")],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stdout)["status"], "error")


if __name__ == "__main__":
    unittest.main()
