---
name: worker
description: Drive one Linear ticket through its full lifecycle autonomously. A Hermes-side loop reads ticket and PR state, asks a delegated reasoner for one next action, applies it, and repeats — until the agent emits stop / request_human, or a max-iteration cap fires. Hermes owns every external mutation (Linear, GitHub, repo, worktrees); the subprocess only reasons.
---

# worker (Hermes-side orchestrator)

Worker reads ticket + PR state, asks a delegated reasoner subprocess for one next action (with full action history each call), applies it, and loops.

## Delegated Claude Code model

All worker subprocesses (reasoner, coder, and tester) follow `../../delegation-contract.md`, which pins the Claude Code model to `sonnet-5`. Do not add a per-action model override in this skill; update the shared contract if the default changes.

## Invocation

Two entry paths reach the same loop:

- **Cron-driven** — `/poller` (see `../poller/SKILL.md`) selects one qualifying ticket per 5-min tick and spawns `/worker <TICKET-KEY>` fire-and-forget.
- **Manual** — `/worker <TICKET-KEY>` typed in an interactive Claude Code session (or fired by another agent / script). Same loop, same pre-checks. No bypass flags. To re-run a ticket in cooldown or with the `Human` label set, clear the state manually first — friction here is intentional.

Argument: a single Linear ticket key (e.g. `TEAM-123`). Pre-checks run on entry regardless of caller — `/poller` filters, but `/worker` re-checks.

## 1. Entry

Before entering the loop:

- **Allowed-team check.** The ticket key's prefix MUST match a row in `../../teams.md`. Any other prefix → exit immediately with `"skipped: ticket <key> is outside allowed teams (see teams.md)"`. No Linear writes, no Discord pings, no comments, nothing. Hermes has the Linear org MCPs connected, and those orgs contain teams beyond the served ones — so reaching a ticket via an MCP query is **not** authorization to act on it. The prefix check is the only authority. Never inline the allowlist here — it lives in `../../teams.md` by design. The team mapping in `../../teams.md` is the single source of truth for repo selection; never pick a repo by filesystem discovery or by inferring from source paths.
- Validate the ticket key exists in Linear. If not, exit with `"ticket <key> not found"`.
- Run universal pre-checks against `~/.hermes/run-table.json` (see § State). Any failure → exit with a one-line reason (`"skipped: Human label is set"`, `"skipped: cooldown active, X minutes remaining"`, `"skipped: another /worker run is in progress"`).
- Acquire the active-run lock for `(ticket, "worker")` — write `active_runs["<ticket>:worker"] = { started_at: now(), expires_at: now() + 6h }` under the locked read-modify-write protocol in § State. Release on every exit path below.
- Initialize per-run state:
  - `action_log = []` — every action emitted this run + result + cost
  - `iteration = 0`

**Hard gate.** After pre-checks pass and state is initialized, enter step 2 immediately — no source reads, no plan-drafting, no thinking-ahead outside the loop. The loop is the only place work gets decided and dispatched.

## 2. Loop

```
while iteration < MAX_ITER:
  iteration += 1

  state = read_full_state(ticket)
  # state = { ticket: {...}, pr: {...} | null, threads: [...], recent_activity: [...] }

  # Pre-iteration termination checks
  if "Human" in state.ticket.labels: exit("human-label")
  if state.ticket.state in {"Done", "Duplicate", "Canceled"}:
    exit("terminal-state:" + state.ticket.state)

  bundle = { kind: "decide", state, action_log, repo_context }
  action = invoke_claude_code(reasoner mode, "./delegated-decide.md", bundle)
  # action = { kind, args, reason }

  if action.kind == "stop":
    exit("stop:" + action.reason)
  if action.kind == "request_human":
    set_human_label(ticket); post_linear_comment(ticket, action.args.comment)
    exit("request_human")

  result = apply(action, ticket)
  action_log.append({ action, result, cost_usd: result.cost_usd })

# Max-iter cap reached
set_human_label(ticket)
post_linear_comment(ticket,
  "Worker hit the iteration cap (" + MAX_ITER + " actions) without resolving. "
  "Handing off for human attention.")
exit("max-iter")
```

### Bundle shape

The bundle sent to the decide subprocess each iteration:

```
{
  kind: "decide",
  state: <full Linear/GitHub state read via MCPs>,
  action_log: <list of prior iterations' { action, result, cost_usd }>,
  repo_context: {
    repo_path: string,            // absolute path to the repo on disk
    agents_md_text?: string,      // contents of AGENTS.md or CLAUDE.md at repo root, if present
    top_level_files?: string[]    // `ls` of the repo root
  }
}
```

**`repo_context` is metadata only** — `AGENTS.md` / `CLAUDE.md` text plus a top-level `ls`, nothing more. If the subprocess needs to ground its decision in source, it reads files itself via `--allowedTools Read`.

## 3. Action handlers (`apply()`)

Hermes implements one handler per action `kind`. Each handler returns a `result` that goes into `action_log` for the next iteration's bundle.

**Block on delegated subprocess invocations — never background-and-stop.** The coder/tester/reasoner subprocesses invoked below can run up to 60/30/20 minutes respectively (see § Safety nets), which exceeds the single foreground `terminal()` command cap (600s). That means they must be launched via `terminal(background=True)` — but you MUST then block on the result with repeated `process(action="wait", timeout=...)` calls (looping across multiple `wait` calls if needed) **until the subprocess actually completes, within this same run**, before doing anything else. Do NOT background the invocation, report a "still running, will resume when notified" status, and end your turn. A one-shot `/worker` cron run (`repeat=1`) gets exactly one turn — once that turn ends, there is no second turn for the job to resume into. `notify_on_complete` fires into a session that has already exited; the finished result (commit, PR description, test output) is stranded with nobody to push the branch, open the PR, or continue the loop. If this happens anyway, the recovery is manual: read the subprocess's result file, verify the worktree/commit are still intact, then perform the remaining `apply()` steps (push, PR, Linear link, worktree cleanup) and the § Exit run-table writes by hand.

### `refine_description`
Args: `{ description_update?: string, labels?: string[], comment?: string }`.
- If `description_update`: update the Linear issue description.
- If `labels`: replace the issue's label set with the given list (canonical).
- If `comment`: post the comment on the issue.
- Result: `{ ok: true, applied: ["description"?, "labels"?, "comment"?] }`.

### `move_state`
Args: `{ state: "Backlog" | "Todo" | "In Progress" | "Review Fixes" | "Done" | "Duplicate" | "Canceled", comment?: string }`.
- Optional comment posted first (so it lands before the state change).
- Set the Linear state.
- Result: `{ ok: true, new_state: <state> }`.
- If the target is `Done` / `Duplicate` / `Canceled`, the loop exits via the pre-iteration terminal-state check on the next iteration.

### `post_comment`
Args: `{ body: string }`.
- Post the body as a Linear comment.
- Result: `{ ok: true }`.

### `start_implementation`
Args: `{ branch_name: string, task_spec: string }`.
- Determine the target repo from the ticket's team row in `../../teams.md` (the `Target GitHub repo` column); if the team has no repo configured, error out.
- `git -C <repo> fetch origin main && git -C <repo> worktree add <wt> -b <branch_name> origin/main`.
- Invoke claude-code in **coder mode** with `./delegated-code.md` and `{ mode: "implement", ticket, branch_name, worktree, task_spec, repo_root }`. The coder edits and tests only; it must not commit, push, or create a PR.
- Run the changeset gate from `./scripts/changeset_gate.py` in the prepared worktree. The gate performs deterministic worktree validation, captures the diff, invokes a read-only semantic reviewer with the issue payload, generates the PR title/body, and commits/pushes only when the reviewer returns `verdict: ready`.
- On gate `{ status: "committed", commit: { commit_sha, ... }, review: { pr_title, pr_description } }`:
  - Open non-draft PR via GitHub MCP: title = `review.pr_title`, body = `review.pr_description` (Hermes prepends the Linear ticket link).
  - Link PR to Linear ticket (verify via integration; otherwise comment with PR URL).
  - `git worktree remove <wt>`.
  - Result: `{ ok: true, commit_sha, pr_url, pr_title, pr_description, summary }`.
- On gate `{ status: "needs_changes" }`: keep the worktree, return the review feedback to the reasoner, and let the next action send the feedback back to the coder. Do not commit, push, or add the Human label yet.
- On coder `{ blocked: true }` or gate/tooling failure: first run `changeset_gate.py recover --worktree <wt> --output /tmp/<ticket>-<run-id>.patch` when the worktree has changes. Keep the worktree or recovery patch available; never force-remove useful edits before recording them. Result includes `{ ok: false, recoverable: true, blocked_reason, recovery_patch }`.

### `apply_fixes`
Args: `{ task_spec: string, resolve_thread_ids?: string[] }`.
- Worktree on the existing PR branch (`git worktree add <wt> origin/<branch>`).
- Invoke claude-code in **coder mode** with `./delegated-code.md` and `{ mode: "fix", ticket, pr, worktree, task_spec, repo_root }`. The coder edits/tests only.
- Run the same changeset gate, passing the PR issue payload and review context. On a ready result, Hermes commits/pushes; for each `thread_id` in `resolve_thread_ids` that the reviewer/coder confirmed it addressed, mark the GitHub review thread resolved with optional `"addressed in <sha>"` reply. Clean up worktree only after successful handoff.
- Result includes `{ commit_sha, addressed_thread_ids, summary, pr_description }`.
- On `needs_changes`, return the exact reviewer feedback to the next coder iteration. On blocked/error, preserve the diff using the recovery path described above.

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
- This is the sole human-handoff mechanism: whether the ticket needs a decision, a review, or is otherwise stuck, it lands in the `Human` lane. There is no separate Linear state for handoff.

### `stop`
Args: `{ reason: string }`.
- Log `reason`. No external mutations.
- Exits the loop.

## 4. Exit

On every exit path, perform all three mutations to `~/.hermes/run-table.json` inside a single locked read-modify-write (see § State):
1. Release the active-run lock — delete `active_runs["<ticket>:worker"]`.
2. Append a record to `runs[]`: `{ ticket, started_at, ended_at: now(), exit_reason, action_log, total_cost_usd }`. Trim oldest entries if `runs.length > 500`.
3. Set `cooldowns[<ticket>] = now()` — pre-check blocks re-entry for 15 min.

## Safety nets

- `MAX_ITER` default: **40** actions per run. On hit: Hermes force-adds the `Human` label + posts a comment.
- Run cooldown: 15 min between worker runs for the same ticket.
- Active-run lock: prevents double-entry. TTL of 6h, refreshed at the top of each loop iteration; expired entries are treated as released (see § State).
- Per-subprocess timeouts: 20 min reasoner, 60 min coder, 30 min tester (see `../../delegation-contract.md`). On timeout, Hermes treats it as `request_human` with a timeout comment.
- Delegated reasoner max_iterations: **100**.

## Failure handling

- If a subprocess returns `{ error, reason }`, Hermes records the failed action in `action_log` and continues the loop. The reasoner sees the failure in the next iteration and decides (likely emits `request_human`).
- If Hermes itself errors applying an action (e.g. Linear API timeout), record the failure in `action_log` and continue. The reasoner sees it and decides.
- If Hermes crashes mid-run, the active-run lock expires after 6h and the ticket becomes eligible for a fresh worker run.

## State

`/worker` owns one canonical state file. Both `/worker` and `/poller` operate over fresh Claude Code sessions each invocation — the run-table is the only continuity between them. Pin both the path and the protocol.

**File**: `~/.hermes/run-table.json`
**Lockfile**: `~/.hermes/run-table.lock` (for `flock`)

If the file is missing, empty, or fails to parse, treat the loaded state as `{}` (and log once — don't error out). The first write creates it.

### Schema

```json
{
  "cooldowns": {
    "TEAM-123": "2026-05-20T22:01:00Z"
  },
  "active_runs": {
    "TEAM-123:worker": {
      "started_at": "2026-05-20T22:00:00Z",
      "expires_at": "2026-05-21T04:00:00Z"
    }
  },
  "runs": [
    {
      "ticket": "TEAM-123",
      "started_at": "2026-05-20T22:00:00Z",
      "ended_at": "2026-05-20T22:01:13Z",
      "exit_reason": "stop:done",
      "action_log": [],
      "total_cost_usd": 0.42
    }
  ]
}
```

- `cooldowns[<ticket>]` — ISO-8601 UTC timestamp of the last `/worker` exit on that ticket. The 15-min cooldown pre-check reads this; the exit path writes it.
- `active_runs["<ticket>:<role>"]` — current in-flight run for that (ticket, role) pair. `expires_at = started_at + 6h` on initial acquire; refreshed to `now() + 6h` at the top of each loop iteration so a live worker never trips its own TTL. Entries with `expires_at` in the past are treated as **released** (passive stale-lock recovery — no explicit janitor needed). The active-run pre-check reads this; entry/exit/refresh writes it.
- `runs` — append-only run history. On exit, append one record. Trim from the front once length exceeds 500 to keep the file size bounded.

All timestamps are ISO-8601 with `Z` suffix (UTC).

### Read-modify-write protocol

Every write to `run-table.json` MUST follow this sequence:

1. `flock -x ~/.hermes/run-table.lock` with a 10-second timeout. If the lock can't be acquired, abort the write and log; do not proceed without the lock.
2. Read `run-table.json`. Missing/empty/corrupt → `{}` (log once).
3. Mutate the in-memory dict.
4. Write to `run-table.json.tmp`, then `mv` (atomic POSIX rename) to `run-table.json`.
5. Release the lock.

Pure reads (the poller's filter pass; this skill's pre-checks) use a shared lock (`flock -s`) and follow the same load-then-decide pattern. The shared lock blocks while a writer holds the exclusive lock; that's intentional — readers must not see a half-written file.

Coalesce mutations: all three exit-path writes (active-lock release, runs append, cooldown set) happen inside a single locked sequence, not three separate ones.

## Don't

- **Don't touch tickets whose prefix isn't in `../../teams.md`.** The connected Linear org MCPs contain teams beyond the served ones; the MCP surfacing a ticket does not authorize action on it. The allowed-team check in § Entry blocks this; do not bypass it, do not "just take a look," do not comment on the foreign ticket to explain the skip. Exit silently.
- **Don't decide.** Your job is read state → bundle → invoke the decide subprocess → apply the result. If something feels like a decision — "should I refine this?", "is this implementable?", "are these review concerns substantive?", "is this ticket trivial enough to skip the subprocess?" — that's the subprocess's job. The rubric lives in `./delegated-decide.md`.
- **Don't read source files in the target repo.** Opening a source file is reasoning, which is deciding, which is out of role. The subprocess reads source files itself via `--allowedTools Read` when its decision needs them.
- Don't implement anything directly. You are the orchestrator. Creating branches, pushing code, and all GitHub/Linear mutations must flow through the loop's `apply()` handlers. If the ticket looks trivial, that's irrelevant — trivial tickets go through the loop too.
- Don't apply two actions per iteration. The reasoner sees one result at a time.
- Don't second-guess the reasoner's action. If you (the orchestrator) think the action is wrong, the reasoner's behavior is what should be fixed (in `./delegated-decide.md`), not the dispatcher.
- Don't strip the `Human` label from worker. Once set, only a human removes it.
- Don't share worktrees across actions in one run. Each `start_implementation` / `apply_fixes` / `run_tests` prepares its own worktree and cleans it up before returning.
