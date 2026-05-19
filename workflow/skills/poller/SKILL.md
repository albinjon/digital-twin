---
name: poller
description: The cron's per-tick logic. Polls Linear every 5 minutes for recently touched tickets, picks at most ONE qualifying ticket (most recently touched), and fires `/worker` on it. Also scans Intervention tickets and sends Discord pings for any that haven't been pinged in the last 24h. Fire-and-forget — /poller exits immediately after spawning the worker, so each tick is short and the next tick can start cleanly.
---

# poller (Hermes-side cron entry)

The single source of truth for "what happens each 5-minute tick". Hermes' cron fires `/poller`; `/poller` does exactly two things per tick:

1. Pick at most one qualifying ticket and fire `/worker` on it (fire-and-forget).
2. Scan `Intervention` tickets and send Discord pings for any that haven't been pinged in 24h.

`/poller` is pure Hermes orchestration. No delegated subprocess. It's all Linear/Discord reads and writes plus one fire-and-forget spawn of `/worker`.

## 1. Pick one qualifying ticket

### Pull candidates

Fetch from Linear: every ticket touched in the last 10 minutes. "Touched" = any state change, label change, comment, or description edit. The poll window is 2× the cron interval to catch events that land between ticks.

### Filter to qualifying

A ticket qualifies if **all** are true:

- **Not in a terminal Linear state.** Excludes `Done`, `Duplicate`, `Canceled`, `Intervention`. (Intervention tickets get the Discord ping scan below, not a worker run.)
- **No `Human` label.** Human-lane tickets are off-limits to automation.
- **No active-run lock for `/worker` on this ticket.** A previous tick's worker is still running; let it finish.
- **Run cooldown elapsed.** Default 15 min since the last `/worker` exit on this ticket.

Tickets failing any check are skipped (not logged loudly — this is the common case for most ticks).

### Pick one

Among qualifying candidates, sort by `last_updated_at` descending and pick the **first** (most recently touched). The others wait for the next tick; if they're still qualifying then, the next tick picks the most recently touched of that pool. Recently-touched tickets always have priority.

### Fire `/worker`

Spawn `/worker <TICKET-KEY>` as a separate process. **Fire-and-forget** — do not wait for it. `/poller` exits immediately after spawning so the tick stays short. The worker's own pre-checks will run on entry (redundant safety; harmless).

If no ticket qualifies, do nothing for this step.

## 2. Intervention Discord ping scan

This runs every tick regardless of step 1. It's independent of worker activity.

### Pull Intervention tickets

Fetch every Linear ticket currently in `Intervention` state.

### Filter to eligible

A ticket is eligible for a ping if **no** Discord ping has been recorded for it in the last 24 hours. (Hermes tracks ping timestamps in its run table — same store as cooldowns.)

### Ping each eligible ticket

For each eligible ticket, send a Discord message to the user with:
- ticket key + title
- a one-line summary of what's blocked (pulled from the most recent automation-authored comment, typically `## Open questions` or an intervention reason)
- a link to the ticket

Record the ping timestamp so the same ticket isn't pinged again for 24h.

This is bulk — every eligible Intervention ticket gets pinged once per tick maximum. (One Intervention ticket can only generate one ping per 24h regardless of how many ticks elapse.)

## 3. Exit

`/poller` finishes the tick. Total runtime per tick is dominated by Linear API calls — should be a few seconds. Heavy work happens inside the `/worker` runs `/poller` spawned (which are independent processes).

## Concurrency

`/poller` itself runs at most one instance at a time (Hermes' cron infrastructure enforces that). Multiple `/worker` runs can be in flight simultaneously — one per ticket, no global cap. The active-run lock prevents two `/worker` runs on the same ticket.

If Hermes wants to cap concurrent worker runs globally (rate-limit / cost-control), that's a Hermes-config concern, not a `/poller` concern. `/poller` just spawns the worker; Hermes decides whether to queue it.

## Don't

- Don't fire `/worker` on more than one ticket per tick. The user's constraint: one qualifying ticket per poll.
- Don't wait for `/worker` to complete. The tick must be short.
- Don't ping the same Intervention ticket more than once per 24h. Honor the recorded timestamp.
- Don't bypass `/worker`'s pre-checks. `/poller`'s qualification filter is the same set; we don't pass an "approved" flag to skip checking.
- Don't pick a ticket older than the poll window. Touched-in-last-10-min is the candidate pool; don't reach further back (otherwise stale tickets would re-trigger forever).
