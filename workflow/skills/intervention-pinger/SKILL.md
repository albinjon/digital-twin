---
name: intervention-pinger
description: The daily Intervention reminder. Fired once per day by Hermes' cron. Fetches every Linear ticket currently in `Intervention` state and sends one Discord ping per ticket. No state, no dedupe logic — the daily cadence is the dedupe. Independent of `/poller` and `/worker`.
---

# intervention-pinger (Hermes-side daily cron entry)

A separate cron from `/poller`. Hermes fires `/intervention-pinger` once per day; the skill pings every Intervention ticket exactly once per fire.

There is no on-disk state. The cron schedule is the dedupe: one fire per day = at most one ping per ticket per day. If a ticket entered `Intervention` 23h59 ago and we ping it now, that's fine — the next fire is 24h away.

## Body

Hermes has three Linear org MCPs connected. Within those orgs we only act on three teams: `VER` (Verkis), `LAV` (Ledger / Lavora), and `ZBS` (ZBS-Web). The orgs contain other teams — those are out of scope and must never be pinged.

1. For each connected Linear MCP, fetch tickets currently in `Intervention` state belonging to teams `VER`, `LAV`, or `ZBS`. Scope by team at the MCP layer when possible.
2. Re-check each result's key prefix: skip any ticket whose key doesn't start with `VER-`, `LAV-`, or `ZBS-`. The MCP returning a ticket is not authorization to ping it.
3. For each surviving ticket, send a Discord message to the user with:
   - ticket key + title
   - a one-line summary of what's blocked (pulled from the most recent automation-authored comment, typically `## Open questions` or an intervention reason)
   - a link to the ticket
4. Exit.

That's it. No filtering by recency, no per-ticket lookups against a state file, no run table.

## Concurrency

Hermes' cron infrastructure ensures only one `/intervention-pinger` instance runs at a time. `/poller` and `/worker` are independent crons; they may be running simultaneously and that's fine — `/intervention-pinger` doesn't read or write the run-table at `~/.hermes/run-table.json`.

## Don't

- **Don't ping tickets outside `VER` / `LAV` / `ZBS`.** The three connected Linear org MCPs contain other teams; a Discord ping on a foreign team's ticket would surface work the user has no intent to touch from this Hermes instance.
- Don't filter by ticket recency. Every Intervention ticket (in the allowed teams) gets pinged on every fire.
- Don't deduplicate within a run. If the same ticket appears twice in the fetch, that's a Linear-side anomaly; ping both.
- Don't read or write any state file. The daily cron schedule is the only dedupe mechanism.
- Don't fire `/worker` or any subprocess. This skill is read-Linear + write-Discord only.
- Don't ping tickets in any state other than `Intervention`. `/poller` handles the workflow for everything else.
