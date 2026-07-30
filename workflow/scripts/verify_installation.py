#!/usr/bin/env python3
"""Resolve and verify the canonical digital-twin workflow installation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

ASSETS = (
    "teams.md",
    "delegation-contract.md",
    "automation-playbook.md",
    "skills/poller/SKILL.md",
    "skills/poller/poller_policy.py",
    "skills/poller/scripts/dispatch_worker.py",
    "skills/worker/SKILL.md",
    "skills/worker/delegated-decide.md",
    "skills/worker/delegated-code.md",
    "skills/worker/delegated-test.md",
    "skills/worker/scripts/action_payload.py",
    "skills/worker/scripts/finalize_run.py",
    "skills/worker/scripts/github_payload.py",
    "skills/worker/scripts/normalize_reasoner_result.py",
    "skills/worker/scripts/prepare_worktree.py",
    "skills/worker/scripts/resolve_repo.py",
    "skills/worker/scripts/preflight.py",
)


def source_root() -> Path:
    configured = os.environ.get("HERMES_WORKFLOW_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser().resolve()


def expected_targets(root: Path | None = None, home: Path | None = None) -> dict[str, Path]:
    root = root or source_root()
    home = home or hermes_home()
    return {
        "source_root": root,
        "hermes_home": home,
        "hermes_teams": home / "teams.md",
        "hermes_contract": home / "delegation-contract.md",
        "hermes_poller": home / "skills" / "poller",
        "hermes_worker": home / "skills" / "worker",
    }


def verify_installation(root: Path | None = None, home: Path | None = None) -> dict[str, Any]:
    paths = expected_targets(root, home)
    source = paths["source_root"]
    links = {
        "teams.md": paths["hermes_teams"],
        "delegation-contract.md": paths["hermes_contract"],
        "skills/poller": paths["hermes_poller"],
        "skills/worker": paths["hermes_worker"],
    }
    missing: list[str] = []
    mismatched: list[dict[str, str]] = []
    resolved_assets: list[str] = []
    for asset in ASSETS:
        path = source / asset
        if path.is_file():
            resolved_assets.append(asset)
        else:
            missing.append(str(path))
    for name, target in links.items():
        expected = source / name
        if not target.exists() and not target.is_symlink():
            missing.append(str(target))
            continue
        if not target.is_symlink():
            mismatched.append({"target": str(target), "expected": str(expected), "reason": "target is not a symlink"})
            continue
        actual = target.resolve()
        if actual != expected.resolve():
            mismatched.append({"target": str(target), "expected": str(expected), "actual": str(actual), "reason": "symlink target mismatch"})
    return {
        "valid": not missing and not mismatched,
        "source_root": str(source),
        "hermes_home": str(paths["hermes_home"]),
        "assets": resolved_assets,
        "links": [{"target": str(target), "source": str(source / name)} for name, target in links.items()],
        "missing": missing,
        "mismatched": mismatched,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root")
    parser.add_argument("--hermes-home")
    args = parser.parse_args()
    result = verify_installation(
        Path(args.source_root).expanduser().resolve() if args.source_root else None,
        Path(args.hermes_home).expanduser().resolve() if args.hermes_home else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
