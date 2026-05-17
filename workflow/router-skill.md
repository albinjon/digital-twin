---
name: router
description: Reconcile a Linear ticket's current state and route it to the correct workflow stage — Backlog, Todo, Review Fixes, Intervention, or Done — based on description, comments, hierarchy, and any associated pull request state. Conservative by default; prefers the smallest correct routing decision over aggressive ones. Includes an Intervention-bounce mechanism for re-triggering an automation on a ticket that's already in the right state but needs another run.
---

# router

Route a single Linear ticket to the workflow stage that best fits its current state. The invoker supplies the ticket.

The router is conservative: it picks the smallest correct routing decision and only acts when the right state is clear. When the state can't be determined safely, it routes to Intervention with a concise comment rather than guessing.

## What you can read

Linear issue (title, description, comments, hierarchy), repository state, pull request context and comments. Linear status changes are allowed when the routing decision is clear.

## States to choose between

`Backlog` · `Todo` · `Review Fixes` · `Intervention` · `Done`

(Or: leave the ticket where it is if the current state is already correct and no re-trigger is needed.)

## Principles

- Be conservative with status changes.
- Use the ticket, its hierarchy, repository, and PR context as sources of truth.
- Don't guess. When the right state is unclear, Intervention is the answer.
- Keep comments concise and directly relevant to the routing decision.

## "Human" label

If the issue has the `Human` label:
- do not remove it automatically
- treat it as a signal that the ticket is in the human lane
- you may still update status if it makes the workflow state clearer
- do not route into an automated execution state in a way that would immediately re-trigger agents, unless that's clearly intended

## Routing rules

### Backlog

Choose when:
- the ticket isn't refined enough for safe implementation
- important details are missing but it still belongs in refinement
- the issue needs clearer structure, scope, or hierarchy cleanup
- not obviously blocked by a specific decision, but not implementation-ready

### Todo

Choose when:
- clearly refined enough for implementation
- no meaningful open questions remain
- repository and ticket context don't reveal blocking ambiguity
- the current issue is the correct execution unit
- no PR-review situation should keep it on the review side instead

Do NOT move to Todo if:
- it's an umbrella parent whose real work is in subtickets
- unresolved review feedback should send it to Review Fixes
- unresolved product/stakeholder questions should send it to Intervention

### Review Fixes

Choose when:
- there's an active PR for the ticket
- unresolved, still-relevant review comments exist
- the concerns are actionable by engineering (no product/UX/business decision needed)
- the feedback appears stale or unattended and the next step is to address it

Do NOT move to Review Fixes if:
- the remaining feedback is trivial or low-value
- the feedback is contradictory or requires human judgment
- the PR is effectively complete and no meaningful review work remains

### Intervention

Choose when:
- ongoing discussion but no clear way forward
- blocked by a product / UX / business / stakeholder decision
- unresolved ambiguity that should be summarized for a human
- ticket hierarchy is unclear enough to block safe routing
- review feedback conflicts or can't be resolved by engineering alone
- current state is confusing enough that a human needs to decide the next step

When routing to Intervention, add one concise actionable comment summarizing what's unclear, unresolved, or blocked.

### Done

Choose only when ALL of these are very clear:
- implementation is complete
- any active PR is fully addressed or merged, or the work is otherwise clearly finished
- no meaningful open questions remain
- no unresolved review feedback still requires action
- this ticket doesn't represent unfinished follow-up work

Be conservative. If there's meaningful doubt about completion, do NOT route to Done.

## Hierarchy considerations

Relevant context may live in the current issue, its parent, its subtickets, or sibling subtickets.

- If the current issue is an umbrella parent and the real execution should happen in subtickets, don't route the parent to Todo.
- If the current issue is a subticket, inspect the parent for scope and shared constraints.
- If the hierarchy is materially unclear and prevents safe routing, route to Intervention.
- If the ticket structure is obviously unhelpful or inconsistent, summarize the problem in a comment and route to Intervention.

## Re-trigger mechanism

If the ticket is already in the correct status, don't treat that as an automatic no-op.

If the appropriate next step is to **re-trigger** the automation associated with the current status, temporarily move the issue to Intervention and then back to the intended status. This wakes downstream automations.

Use this only when re-running the workflow is clearly useful. Don't add unnecessary comments during the bounce (unless the route is genuinely to Intervention for an unresolved blockage). Preserve existing labels.

Examples:
- already in Backlog and needs re-refinement → Intervention → Backlog
- already in Todo and should be re-picked-up by the implementer → Intervention → Todo
- already in Review Fixes and should be re-picked-up by the review-fix implementer → Intervention → Review Fixes

Do NOT bounce:
- `Done` (unless there's a clear reason the ticket should no longer be considered done)
- `Duplicate` (unless the duplicate decision itself is being reversed)
- cases where the current state is correct and no re-trigger is actually needed

## Don't

- Don't create noise.
- Don't move to Done unless completion is very clear.
- Don't move to Todo unless it's clearly implementation-ready and the correct execution unit.
- Don't move umbrella parents to Todo when the real work is in subtickets.
- Don't move to Review Fixes for trivial or low-value feedback.
- Don't guess when human judgment is required — use Intervention.
- Remember that the `Human` label may prevent other automations from acting even after a status bounce.
