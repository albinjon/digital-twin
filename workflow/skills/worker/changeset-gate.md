# Worker changeset gate

`changeset_gate.py` is the Hermes-side boundary between a coder worktree and a PR.

The Claude coder edits and tests only. It does not stage, commit, push, or write the PR body.
Hermes invokes the gate after the coder returns.

## Commands

Inspect a worktree without mutation:

```bash
python3 /path/to/changeset_gate.py inspect \
  --worktree /path/to/worktree \
  --branch feature/example
```

Run the read-only semantic review, generate the PR writeup, commit, and push only when ready:

```bash
python3 /path/to/changeset_gate.py review \
  --worktree /path/to/worktree \
  --branch feature/example \
  --ticket TEAM-123 \
  --issue-json /tmp/TEAM-123-issue.json
```

Preserve a blocked or failed worktree before cleanup:

```bash
python3 /path/to/changeset_gate.py recover \
  --worktree /path/to/worktree \
  --output /tmp/TEAM-123-recovery.patch
```

## Gate rules

- Detached worktrees are rejected.
- An expected branch must match exactly.
- Empty changesets are rejected.
- `git diff --check` must pass before review and again before commit.
- The reviewer must return `verdict: ready`.
- The reviewer’s changed-file list must match the inspected worktree.
- A ready review must include a PR title and description.
- Hermes creates the GitHub PR and updates Linear through MCP after the helper returns a commit.
- A `needs_changes`, classifier failure, or reviewer failure preserves the worktree/diff; it is not an automatic destructive cleanup path.

The helper uses argv-based git commands and does not use `bash -c`, heredocs, shell pipelines, recursive deletion, or GitHub CLI calls.
