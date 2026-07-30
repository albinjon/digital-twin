#!/usr/bin/env python3
"""Prepare a worker worktree without shell composition or destructive cleanup."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def git(repo: Path, args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(["git", "-C", str(repo), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def prepare(repo: str, worktree: str, branch: str) -> dict[str, Any]:
    repo_path = Path(repo).expanduser().resolve()
    worktree_path = Path(worktree).expanduser()
    if not repo_path.is_dir():
        return {"ok": False, "error": "repo_missing", "message": f"Repository does not exist: {repo_path}"}
    if not BRANCH_RE.fullmatch(branch) or branch.startswith("/") or ".." in branch.split("/"):
        return {"ok": False, "error": "invalid_branch", "message": f"Unsafe branch name: {branch!r}"}
    if worktree_path.exists():
        return {"ok": False, "error": "worktree_exists", "message": f"Refusing to delete or overwrite existing path: {worktree_path}"}
    code, _, err = git(repo_path, ["fetch", "origin", "main"])
    if code:
        return {"ok": False, "error": "fetch_failed", "returncode": code, "stderr": err}
    code, out, err = git(repo_path, ["worktree", "add", str(worktree_path), "-b", branch, "origin/main"])
    if code:
        return {"ok": False, "error": "worktree_add_failed", "returncode": code, "stdout": out, "stderr": err}
    return {"ok": True, "repo": str(repo_path), "worktree": str(worktree_path), "branch": branch, "base": "origin/main"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--branch", required=True)
    args = parser.parse_args()
    result = prepare(args.repo, args.worktree, args.branch)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
