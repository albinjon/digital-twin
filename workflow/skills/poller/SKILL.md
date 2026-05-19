---
name: poller
description: The cron's per-tick logic. Every 5 minutes, picks at most ONE qualifying ticket in `Todo` (preferred) or `Backlog` from teams VER/LAV/ZBS and fires `/worker` on it. No touch-time window — older tickets are eligible. Fire-and-forget — /poller exits immediately after spawning the worker, so each tick is short and the next tick can start cleanly. Intervention pings live in a separate daily cron (`/intervention-pinger`), not here.
---

# poller (Hermes-side cron entry)

The single source of truth for "what happens each 5-minute tick". Hermes' cron fires `/poller`; `/poller` does exactly one thing per tick: pick at most one qualifying ticket and fire `/worker` on it (fire-and-forget).

`/poller` is pure Hermes orchestration. No delegated subprocess. It's a Linear read pass, a filter against the run-table at `~/.hermes/run-table.json` (read-only — owned by `/worker`; see `../worker/SKILL.md` § State), and one fire-and-forget spawn of `/worker`.

Intervention Discord pings are handled by a separate daily cron, `/intervention-pinger` — see `../intervention-pinger/SKILL.md`.

## 1. Pick one qualifying ticket

### Pull candidates

Hermes has three Linear org MCPs connected. Within those orgs we only act on three teams: `VER` (Verkis), `LAV` (Ledger / Lavora), and `ZBS` (ZBS-Web). The orgs contain other teams too — those are out of scope.

Fetch from each connected Linear MCP: every ticket in `Todo` or `Backlog` state belonging to teams `VER`, `LAV`, or `ZBS`. **No touch-time filter** — a ticket sitting in `Todo` for a week is just as eligible as one moved there this morning. Scope by team and state at the MCP layer when possible; whatever the MCP can't filter, drop in the qualification step below.

(Other non-terminal states — `In Progress`, `Review Fixes`, etc. — are not candidates for `/poller`. Tickets reach those states from inside a `/worker` run; if a run exits early and leaves a ticket there, the next forward motion comes from a human nudge or a follow-up state move, not from `/poller`.)

### Filter to qualifying

A ticket qualifies if **all** are true:

- **Ticket key starts with `VER-`, `LAV-`, or `ZBS-`.** Mandatory prefix check, applied regardless of which org MCP surfaced the ticket. The MCP returning a ticket is not authorization to act on it. Any other prefix → drop silently. Never expand this allowlist inline; it lives in this skill text by design.
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

Spawn `/worker <TICKET-KEY>` as a separate process. **Fire-and-forget** — do not wait for it. `/poller` exits immediately after spawning so the tick stays short. The worker's own pre-checks will run on entry (redundant safety; harmless).

If no ticket qualifies, do nothing for this step.

## 2. Exit

`/poller` finishes the tick. Total runtime per tick is dominated by Linear API calls — should be a few seconds. Heavy work happens inside the `/worker` runs `/poller` spawned (which are independent processes).

## Concurrency

`/poller` itself runs at most one instance at a time (Hermes' cron infrastructure enforces that). Multiple `/worker` runs can be in flight simultaneously — one per ticket, no global cap. The active-run lock prevents two `/worker` runs on the same ticket.

If Hermes wants to cap concurrent worker runs globally (rate-limit / cost-control), that's a Hermes-config concern, not a `/poller` concern. `/poller` just spawns the worker; Hermes decides whether to queue it.

## Don't

- **Don't fetch or spawn for tickets outside `VER` / `LAV` / `ZBS`.** The connected Linear org MCPs contain other teams; those are out of scope. Other team keys must never reach `/worker`.
- Don't fire `/worker` on more than one ticket per tick. The user's constraint: one qualifying ticket per poll.
- Don't wait for `/worker` to complete. The tick must be short.
- Don't write to `~/.hermes/run-table.json`. The run-table is owned by `/worker`; `/poller` only reads it for the filter pass.
- Don't ping anything from `/poller`. Intervention pings are handled by `/intervention-pinger` on a daily cron.
- Don't bypass `/worker`'s pre-checks. `/poller`'s qualification filter is the same set (minus the state-tier rule, which is poller-specific); we don't pass an "approved" flag to skip checking.
- Don't filter by recency. There's no touch-time window — a `Todo` ticket from a month ago is just as eligible as one moved this morning. The 15-min run cooldown is what prevents the same ticket from re-triggering every tick.
- Don't pick a tier-2 (`Backlog`) ticket while a tier-1 (`Todo`) candidate qualifies. Tier order is strict.
- Don't pick tickets in `In Progress`, `Review Fixes`, or any state other than `Todo` / `Backlog`. Those states are reached and left from inside `/worker`; the poller does not re-pick them.
