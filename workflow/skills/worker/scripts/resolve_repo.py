#!/usr/bin/env python3
"""Resolve a served team prefix to an explicitly configured local repository."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_MAP_PATH = Path("~/.hermes/local-repositories.json")


def map_path() -> Path:
    return Path(os.environ.get("HERMES_LOCAL_REPOSITORIES", str(DEFAULT_MAP_PATH))).expanduser().resolve()


def load_map(path: Path | None = None) -> dict[str, str]:
    path = path or map_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read local repository map {path}: {exc}") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(repo, str) for key, repo in value.items()):
        raise ValueError(f"local repository map {path} must be a JSON object of TEAM_PREFIX to local path")
    return value


def resolve_repo(prefix: str, path: Path | None = None) -> dict[str, Any]:
    prefix = prefix.upper()
    config_path = path or map_path()
    try:
        mapping = load_map(config_path)
    except ValueError as exc:
        return {"ok": False, "error": "repo_map_invalid", "map_path": str(config_path), "message": str(exc)}
    repo = mapping.get(prefix)
    if not repo:
        return {"ok": False, "error": "repo_mapping_missing", "team_prefix": prefix, "map_path": str(config_path), "expected": f"JSON key {prefix!r} containing the local repository path"}
    repo_path = Path(repo).expanduser().resolve()
    if not repo_path.is_dir():
        return {"ok": False, "error": "repo_missing", "team_prefix": prefix, "repo": str(repo_path), "map_path": str(config_path)}
    return {"ok": True, "team_prefix": prefix, "repo": str(repo_path), "map_path": str(config_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("team_prefix")
    parser.add_argument("--map")
    args = parser.parse_args()
    result = resolve_repo(args.team_prefix, Path(args.map).expanduser().resolve() if args.map else None)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
