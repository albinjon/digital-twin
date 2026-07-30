# Host execution plan — Phases 2 through 8

> **Audience:** whoever has shell access to the production Hermes host. Everything
> in `docs/agent-harness-architecture.md` (design) and Phase 0/1 of the
> Hermes-Orchestrated Durable Coding Harness plan (baseline + Python package) is
> done from a macOS dev checkout and does not require this document. Everything
> below requires the real Linux host, the real Hermes gateway, and real
> credentials, and cannot be executed or verified from a dev machine.

Repo state this plan assumes: `pyproject.toml`, `src/digital_twin/` (contracts,
config, CLI), `config/teams.yaml`, and `make test` all green (44 tests) on the
dev checkout as of this commit. `agents/*.md` and `install-avatar.sh` are
marked legacy in place. None of that has been deployed to the host yet.

## Step 1 — Record the real baseline (do this first, before writing any host code)

On the Hermes host:

```bash
hermes --version
curl -s -H "Authorization: Bearer $HERMES_API_KEY" http://127.0.0.1:8642/v1/capabilities | jq .
hermes cron list
systemctl status hermes-gateway 2>/dev/null || ps aux | grep hermes
free -h
```

Record, verbatim, into this doc or a dated log file:

- exact Hermes version and whether `/v1/runs` (run submission/status/stop/events,
  approval events, session resources, skills/toolset inventory) is present in
  `/v1/capabilities`. If it is missing, **stop** — upgrade Hermes first
  (Phase 3 cannot start without it).
- current cron jobs (`poller-ZBS` cadence, `poller-APPAI` paused state).
- current approvals mode (`approvals.mode`, `approvals.cron_mode`) — Phase 3's
  effect profile depends on this being restrictive by default.
- resident/peak memory (this host was observed near 2.6–3.3 GiB on a 3.7 GiB
  box previously — DBOS + PostgreSQL add real headroom pressure; check before
  assuming there's room).
- any lock rows in the existing SQLite state DB, especially stale ones.

Do not proceed past this step on assumption; the plan's canary and rollback
gates depend on these numbers being current, not historical.

## Step 2 — PostgreSQL (Phase 2 prerequisite)

```bash
sudo apt-get install -y postgresql
sudo -u postgres psql -c "CREATE ROLE digital_twin_worker LOGIN PASSWORD '<generate, store in secret manager>';"
sudo -u postgres psql -c "CREATE DATABASE digital_twin OWNER digital_twin_worker;"
```

- Least privilege: `digital_twin_worker` should own only the `digital_twin`
  database, not superuser.
- Put the connection string in an environment file readable only by the
  service user (Step 6), never in a repo file.
- No separate DBOS-vs-application database split is needed at this scale —
  one database, DBOS's own tables plus the application tables below.

## Step 3 — Application tables and DBOS wiring (Phase 2)

Add to the `digital_twin` package (not yet present in this checkout — this is
the next local-repo increment, doable before host deploy):

```
src/digital_twin/
  workflows/ticket_lifecycle.py   # @DBOS.workflow, placeholder typed steps
  storage/migrations/             # ingress_events, generations, action_journal,
                                   # effect_receipts, artifact_metadata,
                                   # review_targets, hermes_run_correlation
  storage/generation.py           # allocate_generation() — one active
                                   # generation per ticket, in a transaction
```

Generation allocation is the one piece of business logic that must be correct
before anything else: `workflow_id = ticket:{ticket_key}:g{generation}`, and a
duplicate poll result for the same ticket must coalesce into the active
generation rather than starting a second one. Write this as a pure function
first (`allocate_generation(conn, ticket_key) -> int`), unit-test it against a
local SQLite/Postgres fixture, then wrap it in a DBOS step.

Recovery gate to prove locally before touching the host (can be done on a dev
Postgres instance, e.g. `brew services start postgresql` or a container):

- kill the worker process after every step boundary in a placeholder
  workflow; on restart, no completed step re-executes and no ticket ends up
  with two active generations.
- run this as an actual test (`kill -9` the process, not a mocked crash) —
  DBOS's recovery guarantee is only real if you've triggered it for real once.

Only after that passes locally does shadow mode on the host make sense:
DBOS running, all external effects explicitly disabled (a single `EFFECTS_ENABLED=false`
env var gate in the effect-execution step, checked before every mutation).

## Step 4 — Hermes API and profiles (Phase 3)

1. Enable the Hermes API server bound to `127.0.0.1:8642` only, with a bearer
   key stored the same way as the Postgres password (env file, service-user-only
   readable). Confirm with `curl` from *another* host that port 8642 is not
   reachable — this must never be internet- or LAN-facing.
2. Configure two Hermes profiles:
   - `digital-twin-context`: read-only Linear + GitHub MCP tools only. No
     terminal, file-write, messaging, cron-creation tool.
   - `digital-twin-effect`: only the specific Linear/GitHub write tools needed
     (issue status transition, label add/remove, typed comment post, PR
     comment/resolve-thread). Same exclusions as above.
3. Verify tool separation from the host, not by reading config:
   `curl .../v1/toolsets?profile=digital-twin-context` and confirm no write
   tool appears; same for `digital-twin-effect` and confirm no terminal/browser
   tool appears.
4. Implement the Runs API adapter (`src/digital_twin/adapters/hermes_runs.py`)
   against the *real* `/v1/runs` responses from this host, not assumed shapes —
   capability discovery, submit, poll/SSE, stop, session correlation, approval
   detection. Contract-test it against a few real recorded responses saved
   from this host (redact tokens before committing fixtures).
5. Register the local control MCP server (`select_and_enqueue`,
   `enqueue_ticket`, `get_run_status`, `resume_ticket`, `cancel_ticket`,
   `reconcile_ticket`) with Hermes and confirm the poller skill can reach it
   (`hermes mcp list` or equivalent) before rewriting the poller skill to call
   it instead of `hermes cron create`.

Gate before Phase 4: kill the Hermes gateway process mid-run (context call,
decision call, and effect call, three separate trials) and confirm each
produces a classified, recoverable outcome rather than a silent hang or a
duplicated effect on retry.

## Step 5 — systemd service (Phase 6, but set up early so Steps 3–4 run under it)

```ini
# /etc/systemd/system/digital-twin-worker.service
[Unit]
Description=Digital Twin DBOS kernel worker
After=postgresql.service network-online.target
Wants=network-online.target

[Service]
Type=simple
User=digital-twin
Group=digital-twin
EnvironmentFile=/etc/digital-twin/worker.env
WorkingDirectory=/srv/digital-twin
ExecStart=/srv/digital-twin/.venv/bin/digital-twin-worker
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/srv/digital-twin/artifacts /srv/repos

[Install]
WantedBy=multi-user.target
```

- Dedicated `digital-twin` OS user, access only to configured repositories
  under `/srv/repos`, the artifact directory, PostgreSQL, Claude CLI
  credentials, and `127.0.0.1:8642`. Not root, not the same user Hermes itself
  runs as (unless that's already the least-privilege choice on this host —
  check before assuming).
- `systemctl daemon-reload && systemctl enable --now digital-twin-worker`.
- Confirm reboot ordering: `sudo reboot`, then check PostgreSQL → worker came
  up in that order and the worker reconnected.

## Step 6 — Lifecycle lanes, one at a time (Phase 4)

Implement and gate lane-by-lane against **recorded fixtures from this host's
real ZBS tickets** (export a handful of representative Backlog/Todo/In
Progress/Review Fixes/Human/merged tickets via the existing MCP tools before
writing the state machine, so the fixtures aren't invented):

1. Backlog refinement → Todo/Human.
2. Todo readiness → implementation request.
3. In Progress verify/review → Review Fixes or Human.
4. Review Fixes → back to In Progress.
5. Terminal reconciliation (merged/closed-unmerged/Human-removed).

Update the poller skill to fetch all four nonterminal lanes and call
`select_and_enqueue`, replacing the current single-lane dispatch.

## Step 7 — Coding backend and workspace (Phase 5)

This is the part with the most existing code to reuse
(`workflow/skills/worker/scripts/{prepare_worktree,changeset_gate,...}.py`).
Move it into `src/digital_twin/adapters/claude_cli.py` and
`src/digital_twin/adapters/git_worktree.py` behind the `CodingBackend` /
`Workspace` ports in `docs/agent-harness-architecture.md`, preserving current
behavior — do not rewrite the gate logic from scratch. Split into durable
steps (prepare, code, inspect, test, review, commit, push, PR effect,
cleanup) only after the move compiles and the existing 37
`workflow/skills/worker/tests` still pass unchanged against the moved code.

Artifact storage: service-owned directory (e.g. `/srv/digital-twin/artifacts`,
owner-only permissions), 30-day raw-artifact retention — a cron/systemd-timer
`find ... -mtime +30 -delete` is sufficient; do not build a retention service
for this.

## Step 8 — Shadow comparison and ZBS canary (Phase 7)

1. Drain/pause (not delete) the current `poller-ZBS` cron job before enabling
   the new lifecycle for ZBS.
2. Shadow mode ≥10 representative ZBS tickets, all effects disabled, compare
   selected lane/decision/capability/intended-effect/terminal-result against
   what the current Hermes-only workflow actually did for those tickets.
3. Enable effects for exactly one explicitly chosen ZBS Todo ticket.
   Independently verify (not from worker logs — from the actual systems):
   workflow/generation ID, Hermes run IDs, action/effect receipts, branch,
   commit, PR, Linear state, exact tested SHA, cost/duration, no forbidden
   operation (merge/force-push/default-branch write).
4. Watch three scheduled poll cycles and one reconciliation cycle before
   calling the canary done.

**Rollback** (must not require touching the database by hand):

```bash
# disable new enqueue path
systemctl stop digital-twin-worker
# resume the old poller
hermes cron resume poller-ZBS
```

Cancel or explicitly let finish the one active workflow; never edit DBOS or
SQLite state manually.

## Step 9 — Full ZBS, then APPAI (Phase 8)

- All ZBS lanes, concurrency 1, at least one clean workflow per lane observed.
- Raise repo concurrency only with memory/cost/workspace evidence from Step 1's
  baseline vs. now.
- APPAI stays paused until ZBS completes three clean end-to-end workflows.

## What NOT to do on the host

- Do not skip Step 1. Every later gate in this plan assumes host-measured
  numbers, not the historical figures in
  `docs/plans/2026-07-30-cron-worker-reliability.md`.
- Do not enable the effect profile before the context profile's tool list has
  been verified empty of writes.
- Do not raise concurrency above 1 anywhere before the ZBS canary (Step 8)
  finishes.
- Do not hand-edit SQLite or PostgreSQL rows to "fix" a stuck workflow —
  cancel/reconcile through the CLI, or roll back.
