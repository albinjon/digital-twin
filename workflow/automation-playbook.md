# Automation playbook — overview

The Linear-driven automation has two entry points, both packaged as skills under `skills/`:

- **`/poller`** — Hermes' cron fires this every 5 minutes. It picks at most one qualifying touched ticket and spawns `/worker` on it (fire-and-forget). It also scans `Intervention` tickets and sends Discord pings for any not pinged in 24h. See `skills/poller/SKILL.md`.

- **`/worker`** — drives one ticket through its full lifecycle in a single autonomous run. Reads ticket + PR state, asks a reasoner subprocess for one structured action at a time, applies it via Hermes' integrations (Linear / GitHub / Discord / git), loops. Heavy actions (`start_implementation`, `apply_fixes`, `run_tests`) spawn `claude-code` subprocesses in coder/tester mode. Terminates on `request_human`, `request_intervention`, terminal Linear state, or a 20-action max-iter cap. See `skills/worker/SKILL.md`.

`/worker` can also be invoked manually as `/worker <TICKET-KEY>` from an interactive Claude Code session — same loop, same pre-checks.

The delegation contract (`delegation-contract.md`) defines the three subprocess invocation modes (reasoner / coder / tester). Hermes owns every external state mutation; subprocesses only reason or write code inside a Hermes-prepared worktree.

---

## Universal pre-checks (run inside `/worker`)

Every `/worker` invocation runs these on entry, regardless of caller. Any failure → exit with a one-line reason.

1. **`Human` label** — ticket is in the human lane; never auto-execute.
2. **Run cooldown** — `/worker` ran on this ticket in the last 15 min.
3. **Active-run lock** — a `/worker` run is currently in progress on this ticket.

`/poller` applies the same filter when selecting a candidate, plus an additional one: the ticket must not be in a terminal state (`Done` / `Duplicate` / `Canceled` / `Intervention`). `Intervention` tickets are handled separately by `/poller`'s Discord ping scan.

---

## Tuning levers

| Lever                              | Default     |
| ---------------------------------- | ----------- |
| Cron interval                      | 5 min       |
| Poll window                        | 10 min      |
| Run cooldown per ticket            | 15 min      |
| Max actions per `/worker` run      | 20          |
| Discord ping on `Intervention`     | once / 24h  |
| Reasoner subprocess timeout        | 20 min      |
| Coder subprocess timeout           | 60 min      |
| Tester subprocess timeout          | 30 min      |
| `/tester` per-command wall-clock   | 5 min       |

Subprocess budget caps and invocation flags live in `delegation-contract.md`. Per-tick selection logic lives in `skills/poller/SKILL.md`. Per-ticket loop logic and action handlers live in `skills/worker/SKILL.md`.
