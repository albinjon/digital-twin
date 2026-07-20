# Automation playbook — overview

> **Allowed Linear teams are defined in [`teams.md`](teams.md)** (currently `VER`, `LAV`, `ZBS`, `APPAI`). Hermes has the Linear org MCPs connected, and each of those orgs contains teams *beyond* the ones we want to touch — so "the MCP returned a ticket" is **not** sufficient authorization to act on it. Every skill in this playbook — `/poller`, `/worker` — must drop, skip, or refuse any ticket whose key prefix is not listed in `teams.md`, regardless of which org MCP surfaced it. Each skill re-checks the prefix against `teams.md` independently; the registry is the single source of the list, but enforcement is duplicated by design.

The Linear-driven automation has two entry points, both packaged as skills under `skills/`:

- **`/poller`** — Hermes' cron invokes this according to each job's configured interval. It picks at most one qualifying ticket in `Todo` and spawns `/worker` on it (fire-and-forget). Older tickets are eligible; there's no touch-time window. See `skills/poller/SKILL.md`.

- **`/worker`** — drives one ticket through its full lifecycle in a single autonomous run. Reads ticket + PR state, asks a reasoner subprocess for one structured action at a time, applies it via Hermes' integrations (Linear / GitHub / Discord / git), loops. Heavy actions (`start_implementation`, `apply_fixes`, `run_tests`) spawn `claude-code` subprocesses in coder/tester mode. Terminates on `request_human`, terminal Linear state, or a 40-action max-iter cap. See `skills/worker/SKILL.md`.

When a ticket needs a person — a decision, a review, or it's otherwise stuck — `/worker` adds the `Human` label and leaves the loop. That label is the single human-handoff signal; there is no separate Linear state for it. `/poller` skips labeled tickets, so a human-flagged ticket stays out of automation until someone clears the label. (Getting *notified* that a label was set is handled out-of-band, not by these skills.)

`/worker` can also be invoked manually as `/worker <TICKET-KEY>` from an interactive Claude Code session — same loop, same pre-checks.

The delegation contract (`delegation-contract.md`) defines the three subprocess invocation modes (reasoner / coder / tester). Hermes owns every external state mutation; subprocesses only reason or write code inside a Hermes-prepared worktree.

---

## Universal pre-checks (run inside `/worker`)

Every `/worker` invocation runs these on entry, regardless of caller. Any failure → exit with a one-line reason.

1. **Allowed team** — ticket key prefix matches a row in `teams.md`. Otherwise exit silently: no Linear writes, no Discord pings, nothing.
2. **`Human` label** — ticket is in the human lane; never auto-execute.
3. **Run cooldown** — `/worker` ran on this ticket in the last 15 min.
4. **Active-run lock** — a `/worker` run is currently in progress on this ticket.

The poller candidate states are `Todo` only. Tickets in `Backlog`, `In Progress`, `Review Fixes`, or any other state are not picked by `/poller`.

---

## Tuning levers

| Lever                              | Default     |
| ---------------------------------- | ----------- |
| Cron interval                      | Configured per cron job (currently ZBS 30 min; APPAI 60 min) |
| Poller candidate states            | `Todo` only; LIFO by `created_at` (newest first) |
| Run cooldown per ticket            | 15 min      |
| Max actions per `/worker` run      | 40          |
| Reasoner subprocess timeout        | 20 min      |
| Coder subprocess timeout           | 60 min      |
| Tester subprocess timeout          | 30 min      |
| `/tester` per-command wall-clock   | 5 min       |

The served-team allowlist and per-team bindings (org MCP, target repo) live in `teams.md`. Subprocess budget caps and invocation flags live in `delegation-contract.md`. Per-tick selection logic lives in `skills/poller/SKILL.md`. Per-ticket loop logic and action handlers live in `skills/worker/SKILL.md`.

Durable state for cooldowns, active-run locks, review targets, findings, and run history lives at `~/.hermes/worker-state.db`, owned by `/worker`. `/poller` reads it for its filter pass. Lock ownership tokens are required for refresh/release, preventing an expired worker from deleting a replacement lock. See `skills/worker/SKILL.md` § State.
