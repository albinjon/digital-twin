#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from verify_installation import ASSETS, verify_installation  # noqa: E402


class InstallationVerificationTests(unittest.TestCase):
    def _source(self, root: Path) -> None:
        for asset in ASSETS:
            path = root / asset
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(asset + "\n")

    def test_accepts_complete_symlinked_installation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "workflow"
            home = base / "hermes"
            self._source(source)
            (home / "skills").mkdir(parents=True)
            (home / "teams.md").symlink_to(source / "teams.md")
            (home / "delegation-contract.md").symlink_to(source / "delegation-contract.md")
            (home / "skills" / "poller").symlink_to(source / "skills" / "poller")
            (home / "skills" / "worker").symlink_to(source / "skills" / "worker")
            result = verify_installation(source, home)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["mismatched"], [])

    def test_reports_missing_and_non_symlink_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "workflow"
            home = base / "hermes"
            self._source(source)
            (home / "skills" / "poller").mkdir(parents=True)
            result = verify_installation(source, home)
        self.assertFalse(result["valid"])
        self.assertIn(str(home / "teams.md"), result["missing"])
        self.assertTrue(any(item["target"] == str(home / "skills" / "poller") for item in result["mismatched"]))


if __name__ == "__main__":
    unittest.main()
