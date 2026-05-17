# Automation playbook — 5-minute cron dispatch

A reference for the orchestrator that scans available GitHub repos and Linear tickets every 5 minutes and decides which skill (if any) to fire for each detected state. This sits between _observation_ and _action_ — the cron observes, the playbook decides, the skills act.

---

## Universal pre-checks

Before firing any skill on a ticket, run these checks. If any fails, skip and try again next tick.

1. **`Human` label** — if the ticket has it, skip _all_ automated execution. The ticket is in the human lane; nothing fires until the label is removed.
2. **Cooldown** — if any skill has run on this ticket in the last 15 minutes, skip. Prevents loop thrash.
3. **Active automation lock** — if a skill is currently running on this ticket from a previous tick, skip. Pick up on the next tick.

---

## Main dispatch — Linear ticket state

For each ticket touched in the last poll window:

| Linear state                      | Additional condition                                                            | Fire           | Reason                                                             |
| --------------------------------- | ------------------------------------------------------------------------------- | -------------- | ------------------------------------------------------------------ |
| New issue (just created)          | —                                                                               | `/refine`      | Fresh intake. Refine clarifies and routes to Todo or Intervention. |
| `Backlog`                         | Just-moved-to-Backlog event                                                     | `/refine`      | Re-refine after manual demotion.                                   |
| `Backlog`                         | Sitting in Backlog, no recent activity                                          | leave          | Already refined; no reason to redo.                                |
| `Todo`                            | no Human label                                                                  | `/implement`   | Start the work — branch + non-draft PR + In Progress.              |
| `In Progress`                     | active non-draft PR, recent PR activity (open / ready-for-review / new commits) | `/review`      | Devil's-advocate pass.                                             |
| `In Progress`                     | active non-draft PR, no recent activity                                         | leave          | Nothing to do.                                                     |
| `In Progress`                     | no active PR after >30 min                                                      | `/router`      | Likely stale; let router reconcile.                                |
| `Review Fixes`                    | —                                                                               | `/fixer`       | Apply feedback on the existing branch.                             |
| `Intervention`                    | not notified recently                                                           | `/notify` only | Human attention needed. Don't auto-execute.                        |
| `Intervention`                    | already notified within the last 24h                                            | leave          | Don't spam.                                                        |
| `Done` / `Duplicate` / `Canceled` | —                                                                               | leave          | Terminal.                                                          |

---

## GitHub-driven triggers

When the trigger comes from a GitHub event (not a Linear state change), find the linked ticket and apply these:

| GitHub event                                                               | Linked-ticket state | Fire                                                                       |
| -------------------------------------------------------------------------- | ------------------- | -------------------------------------------------------------------------- |
| PR opened, linked to a ticket in Todo                                      | `Todo`              | `/router` — likely should be `In Progress` (the linked PR moved past Todo) |
| PR converted draft → ready-for-review                                      | `In Progress`       | `/review` next tick                                                        |
| New commits pushed to PR                                                   | `In Progress`       | `/review` next tick                                                        |
| PR has unresolved review comments, ticket sitting in `In Progress` for >2h | `In Progress`       | `/router` — likely should be `Review Fixes`                                |
| PR closed / merged                                                         | any active state    | `/router` — reconcile to `Done` if appropriate                             |

The cron's job is to _detect_ the event; the dispatched skill does the actual work. If `/review` was already triggered in the cooldown window, the universal pre-check skips this tick — that's fine, the PR isn't going anywhere.

---

## Per-tick flow

```
1. Pull Linear tickets touched in the last 10 min (slightly wider than the 5-min interval to avoid edge misses).
2. Pull PRs touched in the last 10 min from configured repos.
3. For each ticket:
     a. Apply universal pre-checks. Skip if any fail.
     b. Look up the Linear-state row in the dispatch table.
     c. Fire the indicated skill, or leave alone.
     d. Record (ticket-id, skill, timestamp) for cooldown.
4. For each PR:
     a. Find the linked ticket. If none, leave alone (cron is ticket-driven).
     b. Apply GitHub-driven trigger rules.
5. For each ticket in Intervention without a notify in the last 24h:
     a. Fire /notify with a one-line summary of what's blocked.
     b. Mark as notified so the next 24h is quiet.
```

---

## Tuning levers

| Lever                                  | Default                    | When to change                                                                                                                                      |
| -------------------------------------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cron interval                          | 5 min                      | Lengthen if seeing API rate-limit pressure; shorten only if responsiveness is a real complaint.                                                     |
| Cooldown per ticket                    | 15 min                     | Lengthen if seeing repeat fires on the same ticket within a single workflow loop; shorten if real signal is being suppressed.                       |
| Poll window                            | 10 min (cron interval × 2) | Keep it slightly wider than the cron interval. Catches events that land between ticks.                                                              |
| Notify cadence on Intervention         | once per 24h per ticket    | Tighten only if Intervention items are slipping.                                                                                                    |
| "PR ready for ≥2 min before `/review`" | 2 min                      | Race-condition buffer between `/implement` setting In Progress and `/review` looking at the PR. Raise if you see review firing on half-pushed work. |

---

## Failure modes worth watching

**Bouncing.** A ticket cycling In Progress → Review Fixes → In Progress repeatedly without making real progress. The fix lives in `/review`: after N consecutive autonomous fix cycles on the same class of comments, hand off via the `Human` label instead of routing to Review Fixes again. The cron itself shouldn't need to know about this — the skill enforces.

**Race between `/implement` and `/review`.** `/implement` opens a non-draft PR and moves the ticket to In Progress. If `/review` fires on the same tick, it might catch the PR before the linkage is settled. Buffer: only fire `/review` if the PR has been ready-for-review for ≥2 min (see tuning levers).

**Silent half-finished work.** A skill fails partway through and leaves the ticket in an ambiguous state (e.g. branch created but no PR opened). Each skill should route to Intervention with an explanatory comment if it bails mid-execution, never silently. The cron can detect this by spotting tickets stuck in non-terminal states for unusually long without activity and firing `/router` to reconcile.

**Stale PRs vs. stale tickets.** A PR may sit ready-for-review for days with no new commits; that's the human's problem, not the cron's. Don't re-fire `/review` past the cooldown window unless there's new activity. Conversely, a ticket in `Review Fixes` with no recent action might mean `/fixer` failed or was blocked; `/router` is the safety net.

**Human label leaks.** If a skill adds the `Human` label as part of its handoff (e.g. `/review` does for Outcome 2), the cron's universal pre-check immediately picks that up next tick and stops firing. That's the intended behavior; just be aware the human now owns the ticket until they remove the label.

---

## Quick reference — flat decision tree

```
Has Human label?                                                                → skip
Cooldown active for this ticket?                                                → skip
Ticket just created OR just moved to Backlog?                                   → /refine
Ticket in Todo?                                                                 → /implement
Ticket in In Progress AND PR open + ready ≥2min + recent activity?              → /review
Ticket in In Progress AND no PR for >30 min?                                    → /router
Ticket in Review Fixes?                                                         → /fixer
Ticket in Intervention AND no notify in last 24h?                               → /notify
Anything else?                                                                  → leave
```

When in doubt, do nothing. The cron leans cautious by design — better to miss a tick than to spam state changes.
