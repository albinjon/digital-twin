#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from runner.subprocess_runner import run_argv, run_stdin  # noqa: E402


class SubprocessRunnerTests(unittest.TestCase):
    def test_run_argv_does_not_use_shell(self) -> None:
        result = run_argv([sys.executable, "-c", "print('ok')"])
        self.assertTrue(result.ok, result)
        self.assertEqual(result.stdout.strip(), "ok")
        self.assertEqual(result.argv[0], sys.executable)

    def test_run_stdin_passes_input(self) -> None:
        result = run_stdin([sys.executable, "-c", "import sys; print(sys.stdin.read(), end='')"], "payload")
        self.assertTrue(result.ok, result)
        self.assertEqual(result.stdout, "payload")

    def test_nonzero_result_is_structured(self) -> None:
        result = run_argv([sys.executable, "-c", "import sys; print('bad', file=sys.stderr); sys.exit(3)"])
        self.assertFalse(result.ok)
        self.assertEqual(result.returncode, 3)
        self.assertIn("bad", result.stderr)

    def test_rejects_empty_or_nul_argv(self) -> None:
        with self.assertRaises(ValueError):
            run_argv([])
        with self.assertRaises(ValueError):
            run_argv(["bad\x00command"])


if __name__ == "__main__":
    unittest.main()
