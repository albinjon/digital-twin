---
name: poller
description: The cron's per-tick logic. Every 5 minutes, picks at most ONE qualifying ticket in `Todo` (preferred) or `Backlog` from the teams listed in `../../teams.md` and fires `/worker` on it. Accepts an optional prefix-scope argument (e.g. `VER` or `VER,APPAI`) to restrict a given cron to one or a subset of those teams; no argument means all of them. No touch-time window — older tickets are eligible. Fire-and-forget — /poller exits immediately after spawning the worker, so each tick is short and the next tick can start cleanly. Intervention pings live in a separate daily cron (`/intervention-pinger`), not here.
---

# poller (Hermes-side cron entry)

The single source of truth for "what happens each 5-minute tick". Hermes' cron fires `/poller`; `/poller` does exactly one thing per tick: pick at most one qualifying ticket and fire `/worker` on it (fire-and-forget).

`/poller` is pure Hermes orchestration. No delegated subprocess. It's a Linear read pass, a filter against the run-table at `~/.hermes/run-table.json` (read-only — owned by `/worker`; see `../worker/SKILL.md` § State), and one fire-and-forget spawn of `/worker`.

Intervention Discord pings are handled by a separate daily cron, `/intervention-pinger` — see `../intervention-pinger/SKILL.md`.

## 0. Resolve the scope argument

`/poller` accepts an **optional** prefix-scope argument via its prompt:

- **No argument** (empty prompt) — serve every team listed in `../../teams.md`. This is the default and the original behavior.
- **A single prefix** (e.g. `VER`) — serve only that team this tick.
- **A comma-separated list** (e.g. `VER,APPAI`) — serve only that subset.

The argument is a **filter, not an authorization grant**. It can only narrow the `../../teams.md` allowlist, never widen it. Parse it into an uppercase set of prefixes; intersect that set with the prefixes present in `../../teams.md`. Any argument prefix not found in `../../teams.md` is dropped silently (a scoped cron for a retired/unknown team simply does nothing). If the argument is empty, the scope set is the full `../../teams.md` list.

Call the result the **scope set**. Every candidate below is filtered against it in addition to the existing prefix check — the `../../teams.md` authorization check still runs independently and is never bypassed.

## 1. Pick one qualifying ticket

### Pull candidates

Hermes has the Linear org MCPs connected. Within those orgs we only act on the teams listed in `../../teams.md`, further narrowed to the **scope set** from step 0. The orgs contain other teams too — those are out of scope.

Fetch from each connected Linear MCP: every ticket in `Todo` or `Backlog` state belonging to a team in the scope set. **No touch-time filter** — a ticket sitting in `Todo` for a week is just as eligible as one moved there this morning. Scope by team and state at the MCP layer when possible; whatever the MCP can't filter, drop in the qualification step below.

(Other non-terminal states — `In Progress`, `Review Fixes`, etc. — are not candidates for `/poller`. Tickets reach those states from inside a `/worker` run; if a run exits early and leaves a ticket there, the next forward motion comes from a human nudge or a follow-up state move, not from `/poller`.)

### Filter to qualifying

A ticket qualifies if **all** are true:

- **Ticket key prefix matches a row in `../../teams.md` AND is in the scope set.** Mandatory prefix check, applied regardless of which org MCP surfaced the ticket. The MCP returning a ticket is not authorization to act on it. A prefix outside `../../teams.md` → drop silently (unauthorized). A prefix inside `../../teams.md` but outside this cron's scope set → drop silently (out of this cron's scope). Never inline an allowlist here; it lives in `../../teams.md` by design.
- **State is `Todo` or `Backlog`.** Re-check after fetch; defense in depth in case the MCP's state filter is loose.
- **No `Human` label.** Human-lane tickets are off-limits to automation.
- **No active-run lock for `/worker` on this ticket.** A previous tick's worker is still running; let it finish. Source: `active_runs["<ticket>:worker"]` in `~/.hermes/run-table.json` (entries with `expires_at` in the past are treated as released; see worker skill § State).
- **Run cooldown elapsed.** Default 15 min since the last `/worker` exit on this ticket. Source: `cooldowns[ticket]` in `~/.hermes/run-table.json`.

Tickets failing any check are skipped (not logged loudly — this is the common case for most ticks).

### Pick one

Two-tier priority:

1. **Tier 1 — `Todo`.** Among qualifying `Todo` tickets, pick the one with the **latest `created_at`** (LIFO — the most recently created Todo wins).
2. **Tier 2 — `Backlog`.** Only consulted if tier 1 is empty. Same LIFO rule: latest `created_at` wins.

A `Todo` ticket always beats every `Backlog` ticket, even if the `Backlog` ticket is newer.

If neither tier has a qualifying candidate, the tick does nothing for this step.

### Fire `/worker`

Spawn `/worker <TICKET-KEY>` as a one-shot cron job. Fire-and-forget — `/poller` exits immediately after creating the job.

**Exact spawn call:**
```python
cronjob(action="create", name="worker-<TICKET-KEY>", skills=["worker"], prompt="<TICKET-KEY>", schedule="5m", repeat=1, deliver="origin")
```

Do **not** use `terminal()` to spawn — background processes from inside a cron session exit silently without running. The `cronjob` approach is the only working pattern.

If no ticket qualifies, do nothing.

## 2. Exit

`/poller` finishes the tick. Total runtime per tick is dominated by Linear API calls — should be a few seconds. Heavy work happens inside the `/worker` runs `/poller` spawned (which are independent processes).

## Concurrency

`/poller` itself runs at most one instance at a time (Hermes' cron infrastructure enforces that). Multiple `/worker` runs can be in flight simultaneously — one per ticket, no global cap. The active-run lock prevents two `/worker` runs on the same ticket.

If Hermes wants to cap concurrent worker runs globally (rate-limit / cost-control), that's a Hermes-config concern, not a `/poller` concern. `/poller` just spawns the worker; Hermes decides whether to queue it.

## Don't

- **Don't fetch or spawn for tickets whose prefix isn't in `../../teams.md`.** The connected Linear org MCPs contain other teams; those are out of scope. Other team keys must never reach `/worker`.
- **Don't let the scope argument reach a team that isn't in `../../teams.md`.** The argument only narrows the allowlist; it can never authorize a prefix `../../teams.md` doesn't already list.
- Don't fire `/worker` on more than one ticket per tick. The user's constraint: one qualifying ticket per poll.
- Don't wait for `/worker` to complete. The tick must be short.
- Don't write to `~/.hermes/run-table.json`. The run-table is owned by `/worker`; `/poller` only reads it for the filter pass.
- Don't ping anything from `/poller`. Intervention pings are handled by `/intervention-pinger` on a daily cron.
- Don't bypass `/worker`'s pre-checks. `/poller`'s qualification filter is the same set (minus the state-tier rule, which is poller-specific); we don't pass an "approved" flag to skip checking.
- Don't filter by recency. There's no touch-time window — a `Todo` ticket from a month ago is just as eligible as one moved this morning. The 15-min run cooldown is what prevents the same ticket from re-triggering every tick.
- Don't pick a tier-2 (`Backlog`) ticket while a tier-1 (`Todo`) candidate qualifies. Tier order is strict.
- Don't pick tickets in `In Progress`, `Review Fixes`, or any state other than `Todo` / `Backlog`. Those states are reached and left from inside `/worker`; the poller does not re-pick them.
