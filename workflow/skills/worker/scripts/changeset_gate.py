#!/usr/bin/env python3
"""Validate, review, commit, and optionally push a worker changeset.

The helper deliberately owns only local git/worktree operations and the
read-only Claude review. Hermes remains responsible for GitHub and Linear
MCP mutations.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


class GateError(RuntimeError):
    """A recoverable changeset-gate failure."""


def run_git(worktree: Path, args: Sequence[str], *, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(worktree), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode:
        raise GateError(f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def status_entries(worktree: Path) -> list[dict[str, str]]:
    raw = run_git(worktree, ["status", "--porcelain=v1", "-z"])
    entries: list[dict[str, str]] = []
    fields = raw.split("\0")
    i = 0
    while i < len(fields):
        item = fields[i]
        i += 1
        if not item:
            continue
        code = item[:2]
        path = item[3:]
        if code[0] in {"R", "C"}:
            if i < len(fields):
                path = fields[i]
                i += 1
        entries.append({"code": code, "path": path})
    return entries


def changed_paths(worktree: Path) -> list[str]:
    return [entry["path"] for entry in status_entries(worktree)]


def _untracked_patch(worktree: Path, paths: list[str]) -> str:
    chunks: list[str] = []
    for path in paths:
        absolute = worktree / path
        if absolute.is_file() and not run_git(worktree, ["ls-files", "--error-unmatch", "--", path], check=False).strip():
            proc = subprocess.run(
                ["git", "-C", str(worktree), "diff", "--no-index", "--binary", "/dev/null", str(absolute)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
            )
            chunks.append(proc.stdout)
    return "".join(chunks)


def combined_diff(worktree: Path, paths: list[str]) -> str:
    return run_git(worktree, ["diff", "HEAD", "--binary"]) + _untracked_patch(worktree, paths)


def inspect_worktree(worktree: Path, expected_branch: str | None = None) -> dict[str, Any]:
    worktree = worktree.resolve()
    if not worktree.is_dir():
        raise GateError(f"worktree does not exist: {worktree}")

    branch = run_git(worktree, ["branch", "--show-current"]).strip()
    head = run_git(worktree, ["rev-parse", "HEAD"]).strip()
    if not branch:
        raise GateError("worktree is detached")
    if expected_branch and branch != expected_branch:
        raise GateError(f"expected branch {expected_branch!r}, found {branch!r}")

    paths = changed_paths(worktree)
    diff = combined_diff(worktree, paths)
    cached_diff = run_git(worktree, ["diff", "--cached", "--binary"])
    if not paths and not cached_diff:
        raise GateError("empty changeset")

    check = subprocess.run(
        ["git", "-C", str(worktree), "diff", "--check"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check.returncode:
        raise GateError(f"git diff --check failed: {(check.stdout + check.stderr).strip()}")

    return {
        "worktree": str(worktree),
        "branch": branch,
        "base_sha": head,
        "changed_files": paths,
        "diff": diff,
        "cached_diff": cached_diff,
        "status": status_entries(worktree),
        "diff_check": "passed",
    }


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GateError(f"expected JSON object in {path}")
    return value


def review_prompt(issue: dict[str, Any], inspection: dict[str, Any]) -> str:
    payload = {
        "kind": "changeset_review",
        "issue": issue,
        "changeset": {
            "branch": inspection["branch"],
            "changed_files": inspection["changed_files"],
            "diff": inspection["diff"],
        },
    }
    return (
        "Review this proposed worker changeset against the issue. "
        "Do not edit files, commit, push, or call external services. "
        "Return only the requested JSON schema. Reject unrelated or missing work.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["ready", "needs_changes", "blocked"]},
        "summary": {"type": "string"},
        "pr_title": {"type": "string"},
        "pr_description": {"type": ["string", "null"]},
        "changed_files": {"type": "array", "items": {"type": "string"}},
        "missing_requirements": {"type": "array", "items": {"type": "string"}},
        "scope_findings": {"type": "array", "items": {"type": "string"}},
        "feedback": {"type": "string"},
    },
    "required": [
        "verdict",
        "summary",
        "pr_title",
        "pr_description",
        "changed_files",
        "missing_requirements",
        "scope_findings",
        "feedback",
    ],
}


def invoke_review(
    worktree: Path,
    prompt: str,
    *,
    model: str = "sonnet-5",
    timeout: int = 1200,
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as schema_file:
        json.dump(REVIEW_SCHEMA, schema_file, separators=(",", ":"))
        schema_path = Path(schema_file.name)
    try:
        proc = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--model",
                model,
                "--effort",
                "high",
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(REVIEW_SCHEMA, separators=(",", ":")),
                "--allowedTools",
                "Read",
                "--add-dir",
                str(worktree),
                "--max-budget-usd",
                "10",
                "--max-turns",
                "20",
                "--fallback-model",
                "haiku",
            ],
            cwd=worktree,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GateError(f"reviewer timed out after {timeout}s") from exc
    finally:
        schema_path.unlink(missing_ok=True)

    if proc.returncode:
        raise GateError(f"reviewer failed ({proc.returncode}): {proc.stderr.strip()}")
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise GateError(f"reviewer returned invalid JSON: {exc}") from exc

    candidate = envelope.get("structured_output")
    if candidate is None:
        candidate = envelope.get("result")
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise GateError(f"reviewer nested result is invalid JSON: {exc}") from exc
    if not isinstance(candidate, dict):
        raise GateError("reviewer returned no structured review object")
    missing = [key for key in REVIEW_SCHEMA["required"] if key not in candidate]
    if missing:
        raise GateError(f"reviewer response missing fields: {', '.join(missing)}")
    return candidate


def commit_changes(
    worktree: Path,
    ticket_key: str,
    commit_message: str,
    *,
    push: bool = True,
) -> dict[str, Any]:
    inspection = inspect_worktree(worktree)
    paths = inspection["changed_files"]
    if not paths:
        raise GateError("cannot commit an empty changeset")

    run_git(worktree, ["add", "--", *paths])
    staged = run_git(worktree, ["diff", "--cached", "--name-only"]).splitlines()
    if sorted(staged) != sorted(paths):
        raise GateError("staged paths differ from inspected paths")
    check = subprocess.run(
        ["git", "-C", str(worktree), "diff", "--cached", "--check"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check.returncode:
        raise GateError(f"staged diff check failed: {(check.stdout + check.stderr).strip()}")

    run_git(worktree, ["commit", "-m", commit_message])
    sha = run_git(worktree, ["rev-parse", "HEAD"]).strip()
    if push:
        run_git(worktree, ["push", "--set-upstream", "origin", inspection["branch"]])
    return {
        "commit_sha": sha,
        "branch": inspection["branch"],
        "changed_files": paths,
        "pushed": push,
    }


def save_recovery_patch(worktree: Path, output: Path) -> dict[str, Any]:
    inspection = inspect_worktree(worktree)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(inspection["diff"] or inspection["cached_diff"], encoding="utf-8")
    return {
        "status": "preserved",
        "patch": str(output),
        "branch": inspection["branch"],
        "changed_files": inspection["changed_files"],
    }


def cmd_inspect(args: argparse.Namespace) -> dict[str, Any]:
    return inspect_worktree(Path(args.worktree), args.branch)


def cmd_review(args: argparse.Namespace) -> dict[str, Any]:
    worktree = Path(args.worktree)
    inspection = inspect_worktree(worktree, args.branch)
    issue = load_json(Path(args.issue_json))
    review = invoke_review(worktree, review_prompt(issue, inspection), model=args.model, timeout=args.timeout)
    result: dict[str, Any] = {"review": review, "inspection": {k: v for k, v in inspection.items() if k != "diff"}}
    if review["verdict"] != "ready":
        result["status"] = review["verdict"]
        return result

    reported = set(review["changed_files"])
    actual = set(inspection["changed_files"])
    if reported != actual:
        raise GateError("reviewer changed_files does not match the inspected changeset")
    if not review["pr_description"]:
        raise GateError("ready review did not provide pr_description")
    commit = commit_changes(worktree, args.ticket, args.commit_message or review["pr_title"], push=not args.no_push)
    result.update({"status": "committed", "commit": commit})
    return result


def cmd_recover(args: argparse.Namespace) -> dict[str, Any]:
    return save_recovery_patch(Path(args.worktree), Path(args.output))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--worktree", required=True)
    inspect.add_argument("--branch")
    inspect.set_defaults(handler=cmd_inspect)

    review = sub.add_parser("review")
    review.add_argument("--worktree", required=True)
    review.add_argument("--branch", required=True)
    review.add_argument("--ticket", required=True)
    review.add_argument("--issue-json", required=True)
    review.add_argument("--commit-message")
    review.add_argument("--model", default=os.environ.get("CLAUDE_REVIEW_MODEL", "sonnet-5"))
    review.add_argument("--timeout", type=int, default=1200)
    review.add_argument("--no-push", action="store_true")
    review.set_defaults(handler=cmd_review)

    recover = sub.add_parser("recover")
    recover.add_argument("--worktree", required=True)
    recover.add_argument("--output", required=True)
    recover.set_defaults(handler=cmd_recover)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.handler(args)
    except GateError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
