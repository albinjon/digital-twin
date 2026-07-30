#!/usr/bin/env python3
"""Worker preflight: verify local capabilities before external mutation."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from resolve_repo import resolve_repo


def preflight(repo: str | None = None, *, team: str | None = None, require_claude: bool = True) -> dict[str, Any]:
    repo_mapping = resolve_repo(team) if team and not repo else None
    if repo_mapping and repo_mapping["ok"]:
        repo = str(repo_mapping["repo"])
    skill_root = Path(__file__).resolve().parents[1]
    workflow_root = skill_root.parents[1]
    required = [
        skill_root / "SKILL.md",
        skill_root / "delegated-decide.md",
        skill_root / "delegated-code.md",
        skill_root / "delegated-test.md",
        skill_root / "scripts" / "action_payload.py",
        skill_root / "scripts" / "normalize_reasoner_result.py",
        workflow_root / "teams.md",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    commands = {name: bool(shutil.which(name)) for name in (["git", "python3", "claude"] if require_claude else ["git", "python3"])}
    repo_result = None
    if repo:
        repo_path = Path(repo).expanduser().resolve()
        repo_result = {"path": str(repo_path), "exists": repo_path.is_dir()}
    errors: list[dict[str, Any]] = []
    if repo_mapping and not repo_mapping["ok"]:
        errors.append(repo_mapping)
    if missing:
        errors.append({"code": "workflow_assets_missing", "missing": missing})
    unavailable = sorted(name for name, available in commands.items() if not available)
    if unavailable:
        errors.append({"code": "commands_unavailable", "commands": unavailable, "expected": "commands available on PATH"})
    if repo_result and not repo_result["exists"]:
        errors.append({"code": "repo_missing", "repo": repo_result["path"]})
    return {"ok": not errors, "skill_root": str(skill_root), "workflow_root": str(workflow_root), "repo": repo_result, "commands": commands, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo")
    parser.add_argument("--team")
    parser.add_argument("--no-claude", action="store_true")
    args = parser.parse_args()
    result = preflight(args.repo, team=args.team, require_claude=not args.no_claude)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
