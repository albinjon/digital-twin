from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from migrate_legacy_state import migrate  # noqa: E402
from worker_state import connect  # noqa: E402


class MigrationTests(unittest.TestCase):
    def test_migration_is_idempotent_and_preserves_latest_cooldown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "run-table.json"
            destination = root / "worker-state.db"
            source.write_text(json.dumps({
                "cooldowns": {"ZBS-1": "2026-01-01T00:00:00Z"},
                "active_runs": {"ZBS-1:worker": {"started_at": "2026-01-01T00:00:00Z", "expires_at": "2026-01-01T01:00:00Z"}},
                "runs": [{"ticket": "ZBS-1", "started_at": "2026-01-01T00:00:00Z", "ended_at": "2026-01-01T00:05:00Z", "exit_reason": "stop"}],
            }))
            first = migrate(source, destination)
            second = migrate(source, destination)
            source.write_text(json.dumps({
                "cooldowns": {"ZBS-1": "2026-01-01T00:00:00Z"},
                "active_runs": {},
                "runs": [
                    {"ticket": "ZBS-1", "started_at": "2026-01-01T00:00:00Z", "ended_at": "2026-01-01T00:05:00Z", "exit_reason": "stop"},
                    {"ticket": "ZBS-2", "started_at": "2026-01-02T00:00:00Z", "ended_at": "2026-01-02T00:05:00Z", "exit_reason": "stop"},
                ],
            }))
            third = migrate(source, destination)
            self.assertEqual(first["already_imported"], "false")
            self.assertEqual(second["already_imported"], "true")
            self.assertEqual(third["already_imported"], "false")
            connection = connect(destination)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 2)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM worker_locks").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM schema_meta WHERE key LIKE 'legacy_run_table:%'").fetchone()[0], 2)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
