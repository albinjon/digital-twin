---
name: worker
description: Drive one Linear ticket through its full lifecycle autonomously. A Hermes-side loop reads ticket and PR state, asks a delegated reasoner for one next action, applies it, and repeats — until the agent emits stop / request_human / request_intervention, or a max-iteration cap fires. Hermes owns every external mutation (Linear, GitHub, repo, worktrees); the subprocess only reasons.
---

# worker (Hermes-side orchestrator)

The entire workflow brain, in one skill. Worker reads ticket + PR state, asks a reasoner subprocess for the next action, applies it, and loops.

There is no per-state dispatch table, no `Planned` or `Tests Passed` label gates, no per-skill split. The reasoner sees the full ticket + PR + action history each iteration and decides one next action at a time.

## Invocation

Two entry paths reach the same loop:

- **Cron-driven** — `/poller` (see `../poller/SKILL.md`) selects one qualifying ticket per 5-min tick and spawns `/worker <TICKET-KEY>` fire-and-forget.
- **Manual** — `/worker <TICKET-KEY>` typed in an interactive Claude Code session (or fired by another agent / script). Same loop, same pre-checks. No bypass flags. To re-run a ticket in cooldown or with the `Human` label set, clear the state manually first — friction here is intentional.

Argument: a single Linear ticket key (e.g. `TEAM-123`). If the key doesn't resolve, exit immediately with `"ticket <key> not found"`.

Pre-checks run inside the skill on every invocation, regardless of caller. `/poller` filters tickets before spawning, but `/worker` doesn't trust that — it re-checks on entry.

## 1. Entry

Worker is invoked for a single ticket key. Before entering the loop:

- Validate the ticket key exists in Linear. If not, exit with `"ticket <key> not found"`.
- Run universal pre-checks. Any failure → exit with a one-line reason (`"skipped: Human label is set"`, `"skipped: cooldown active, X minutes remaining"`, `"skipped: another /worker run is in progress"`).
- Acquire the active-run lock for `(ticket, "worker")`. Release on every exit path below.
- Initialize per-run state:
  - `action_log = []` — every action emitted this run + result + cost
  - `iteration = 0`

## 2. Loop

```
while iteration < MAX_ITER:
  iteration += 1

  state = read_full_state(ticket)
  # state = { ticket: {...}, pr: {...} | null, threads: [...], recent_activity: [...] }

  # Pre-iteration termination checks
  if "Human" in state.ticket.labels: exit("human-label")
  if state.ticket.state in {"Done", "Duplicate", "Canceled", "Intervention"}:
    exit("terminal-state:" + state.ticket.state)

  bundle = { kind: "decide", state, action_log, repo_context }
  action = invoke_claude_code(reasoner mode, "./delegated-decide.md", bundle)
  # action = { kind, args, reason }

  if action.kind == "stop":
    exit("stop:" + action.reason)
  if action.kind == "request_human":
    set_human_label(ticket); post_linear_comment(ticket, action.args.comment)
    exit("request_human")
  if action.kind == "request_intervention":
    move_linear_state(ticket, "Intervention", action.args.comment)
    exit("request_intervention")

  result = apply(action, ticket)
  action_log.append({ action, result, cost_usd: result.cost_usd })

# Max-iter cap reached
set_human_label(ticket)
post_linear_comment(ticket,
  "Worker hit the iteration cap (" + MAX_ITER + " actions) without resolving. "
  "Handing off for human attention.")
exit("max-iter")
```

## 3. Action handlers (`apply()`)

Hermes implements one handler per action `kind`. Each handler returns a `result` that goes into `action_log` for the next iteration's bundle.

### `refine_description`
Args: `{ description_update?: string, labels?: string[], comment?: string }`.
- If `description_update`: update the Linear issue description.
- If `labels`: replace the issue's label set with the given list (canonical).
- If `comment`: post the comment on the issue.
- Result: `{ ok: true, applied: ["description"?, "labels"?, "comment"?] }`.

### `move_state`
Args: `{ state: "Backlog" | "Todo" | "In Progress" | "Review Fixes" | "Intervention" | "Done" | "Duplicate" | "Canceled", comment?: string }`.
- Optional comment posted first (so it lands before the state change).
- Set the Linear state.
- Result: `{ ok: true, new_state: <state> }`.
- If the target is `Intervention` / `Done` / `Duplicate` / `Canceled`, the loop exits via the pre-iteration terminal-state check on the next iteration.

### `post_comment`
Args: `{ body: string }`.
- Post the body as a Linear comment.
- Result: `{ ok: true }`.

### `start_implementation`
Args: `{ branch_name: string, task_spec: string }`.
- Determine the target repo from the ticket (Hermes' configured mapping; if none, error out).
- `git -C <repo> fetch origin main && git -C <repo> worktree add <wt> -b <branch_name> origin/main`.
- Invoke claude-code in **coder mode** with `./delegated-code.md` and `{ mode: "implement", ticket, branch_name, worktree, task_spec, repo_root }`.
- On `{ commit_sha, summary, pr_description, blocked: false }`:
  - `git push -u origin <branch_name>`.
  - Open non-draft PR via GitHub: title = ticket title, body = `pr_description` (Hermes prepends Linear ticket link).
  - Link PR to Linear ticket (verify via integration; otherwise comment with PR URL).
  - `git worktree remove <wt>`.
  - Result: `{ ok: true, commit_sha, pr_url, summary }`.
- On `{ blocked: true, blocked_reason }`: `git worktree remove --force <wt>`. Result: `{ ok: false, blocked_reason }`. (The reasoner sees this and likely emits `request_intervention`.)
- On `{ error, reason }`: `git worktree remove --force <wt>`. Result: `{ ok: false, error_reason: reason }`.

### `apply_fixes`
Args: `{ task_spec: string, resolve_thread_ids?: string[] }`.
- Worktree on the existing PR branch (`git worktree add <wt> origin/<branch>`).
- Invoke claude-code in **coder mode** with `{ mode: "fix", ticket, pr, worktree, task_spec, repo_root }`.
- On success: push commits; for each `thread_id` in `resolve_thread_ids` that the subprocess confirmed it addressed (in `addressed_thread_ids`), mark the GitHub review thread resolved with optional `"addressed in <sha>"` reply; remove `Tests Passed`-style markers if any are still around (cleanup for legacy state — generally a no-op post-Phase-4). Clean up worktree.
- Result includes `{ commit_sha, addressed_thread_ids, summary, unaddressed_thread_ids }`.
- On `blocked` / error: same pattern as `start_implementation`.

### `run_tests`
Args: `{}` (no args needed — Hermes derives the PR head from current state).
- Worktree on PR head.
- Invoke claude-code in **tester mode** with `./delegated-test.md` and `{ ticket, pr, worktree }`.
- Return the subprocess output verbatim as the result: `{ outcome, test_command, tested_sha, failures?, runtime_reason?, summary }`.
- Clean up worktree.

### `post_pr_comment`
Args: `{ body: string, path?: string, line?: integer }`.
- Post a line comment on the PR if `path` + `line` are provided; otherwise a top-level PR comment.
- Result: `{ ok: true, comment_id }`.

### `resolve_pr_thread`
Args: `{ thread_id: string, reply?: string }`.
- If `reply`, post it on the thread first.
- Mark the thread resolved.
- Result: `{ ok: true }`.

### `request_human`
Args: `{ comment: string }`.
- Add the `Human` label to the Linear ticket.
- Post `comment` on the ticket.
- Exits the loop.

### `request_intervention`
Args: `{ comment: string }`.
- Post `comment`.
- Move the ticket to `Intervention`.
- Exits the loop.

### `stop`
Args: `{ reason: string }`.
- Log `reason`. No external mutations.
- Exits the loop.

## 4. Exit

On every exit path:
1. Release the active-run lock for `(ticket, "worker")`.
2. Record the run in Hermes' run table: ticket key, start time, end time, exit reason, full `action_log`, total cost.
3. Set the run-cooldown timestamp for this ticket — cron's pre-check blocks re-entry for 15 min.

## Safety nets

- `MAX_ITER` default: **20** actions per run. On hit: Hermes force-adds the `Human` label + posts a comment. This replaces every form of bouncing detection — simpler and more general.
- Run cooldown: 15 min between worker runs for the same ticket.
- Active-run lock: prevents double-entry. TTL of 6h (refreshed each iteration) handles Hermes crashes.
- Per-subprocess timeouts: 20 min reasoner, 60 min coder, 30 min tester (see `../../delegation-contract.md`). On timeout, Hermes treats it as `request_intervention` with a timeout comment.

## Failure handling

- If a subprocess returns `{ error, reason }`, Hermes records the failed action in `action_log` and continues the loop. The reasoner sees the failure in the next iteration and decides (likely emits `request_intervention`).
- If Hermes itself errors applying an action (e.g. Linear API timeout), record the failure in `action_log` and continue. The reasoner sees it and decides.
- If Hermes crashes mid-run, the active-run lock expires after 6h and the ticket becomes eligible for a fresh worker run.

## Don't

- Don't apply two actions per iteration. The reasoner sees one result at a time.
- Don't second-guess the reasoner's action. If you (the orchestrator) think the action is wrong, the reasoner's behavior is what should be fixed (in `./delegated-decide.md`), not the dispatcher.
- Don't strip the `Human` label from worker. Once set, only a human removes it.
- Don't share worktrees across actions in one run. Each `start_implementation` / `apply_fixes` / `run_tests` prepares its own worktree and cleans it up before returning.
