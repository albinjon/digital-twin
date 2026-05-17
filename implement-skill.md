---
name: implement
description: Implement a unit of engineering work, tracked by a Linear ticket. The invoker supplies either a Linear ticket (in Todo, no "Human" label) or a clear task description — if no ticket is linked, one is created first so the work is tracked. Classify the type, validate readiness, create a properly-named branch (type prefix + Linear key + slug, or a key-less fallback if a ticket genuinely can't be created), implement, and open a non-draft PR for the review loop. Moves the ticket to In Progress when the PR is ready.
---

# implement

Implement a single unit of engineering work and produce a non-draft PR the review loop can pick up. The invoker supplies either:

- a Linear ticket (in Todo, no `Human` label), or
- a task description without a ticket — in which case `implement` creates one first.

If a supplied ticket has the `Human` label, do nothing and stop.

## Categories

- **Feature** — new capability or change to existing behavior/UI logic (unless clearly fixing broken behavior, then Bug).
- **Bug** — defect or unintended behavior.
- **Chore** — copy-only change, refactor, cleanup, dependency upgrade, tooling change, configuration work, internal maintenance, non-behavioral adjustments.

## Principles

- Prefer simple, maintainable, low-complexity solutions. Every layer or abstraction earns its keep *now*.
- Make deliberate trade-offs when simplicity isn't possible, and document them briefly in the issue.
- Be action-oriented, but don't guess when a missing dependency, access gap, or product ambiguity blocks correct implementation.
- Keep issue updates concise and directly relevant to moving the ticket forward.
- Cut defensive maximalism — no try/except for failures that don't happen, no null checks for impossible nulls, no validation duplicated at every layer.
- Surgical, not band-aid: every changed line traces to the request, and smallest diff isn't always the right diff. If shipping smallness would hide debt, name it.

## Procedure

### 1. Read context, classify, and ensure tracking

**If a ticket was supplied:** read the issue, its parent (if any), and subtickets. Decide whether this issue is the correct execution unit. Classify the type (Feature / Bug / Chore).

**If no ticket was supplied:** classify the work from the request, then create a Linear ticket capturing the goal, the type, and any acceptance intent that's clear from the description. Use the new ticket's key for the rest of the procedure. Untracked work is harder to follow, so this step matters even when the task feels small.

**If ticket creation fails** (no Linear access, wrong project, permission issue, etc.): proceed with a key-less branch (see step 4) and call out the missing tracking in the PR description so it's visible at handoff. Don't loop on this — one honest attempt at ticket creation is enough.

### 2. Resolve open questions

If the issue contains open questions:
- if the correct path is evident from available context, existing patterns, or standard engineering practices, resolve the question and update the issue to reflect the chosen direction (close the open question)
- if it's clearly a product / UX / business / stakeholder decision rather than engineering, route the issue to Intervention with a clear comment and stop

### 3. Validate readiness

Proceed only if implementable with the information and access available.

Stop and route to Intervention with a comment if any of these is missing:
- required tool
- repository access
- credentials or environment access
- unclear acceptance criteria
- missing technical context that can't be safely inferred
- materially unclear parent or subticket boundaries

Don't continue implementation after routing to Intervention.

### 4. Create the branch

Branch names tie work to its Linear ticket. Default format:

```
<type>/<linear-key-lowercased>-<short-slug>
```

Examples (the team prefix is whatever the actual ticket has — not a hardcoded one):

```
feature/skry-1234-add-auth-redirect
bug/lav-288-credit-invoice-autofill
chore/zbs-45-bump-tailwind
```

Rules:
- `<type>` is `feature/`, `bug/`, or `chore/` based on the classification
- `<linear-key>` is the actual team-prefixed key from the ticket (e.g. `SKRY-1234`, `LAV-288`, `ZBS-45`), lowercased
- `<slug>` is short, descriptive, kebab-case
- `feature/` for new features and behavior changes
- `bug/` for bug fixes
- `chore/` for copy-only / refactor / cleanup / dependency / config / internal work

**Fallback — if ticket creation genuinely failed in step 1**, use a key-less name:

```
feature/<short-slug>
bug/<short-slug>
chore/<short-slug>
```

In that case, the PR description should note that no Linear ticket exists and briefly say why — so the review loop doesn't silently lose the tracking signal.

### 5. Implement

Implement the current ticket's scope only. Don't expand to absorb sibling subtickets unless the hierarchy is clearly redundant and the result is one coherent safe implementation unit.

Follow the principles: simple > clever, no defensive maximalism, surgical changes. Every changed line traces to the request. No drive-by refactors of adjacent code.

### 6. Open / update the PR

- open or update the pull request on the implementation branch
- the PR must **not** be a draft — the review loop depends on a non-draft PR to pick it up
- if a draft PR already exists for this work, convert it to ready-for-review before completing this automation
- ensure the linked Linear issue is in `In Progress` when the PR is ready (either via the GitHub integration or by updating directly)

The PR is the handoff into the review loop.

## Hierarchy handling

When the current issue is a **subticket**:
- read the parent for overall goal, shared constraints, scope boundaries, acceptance intent
- use parent + sibling context to understand the larger change
- implement only this subticket's scope
- don't silently absorb sibling subtickets unless the hierarchy is clearly redundant and the change is one coherent safe unit

When the current issue is a **top-level issue with subtickets**:
- inspect the subtickets first
- determine whether the top-level issue contains a distinct implementable slice
- if the subtickets are only supportive notes and the top-level is one coherent unit, continue and use subtickets as context
- if the subtickets are separate execution units or materially distinct work, don't implement the umbrella parent directly — add a concise comment that the work is split across subtickets and route to Intervention

General hierarchy rules:
- don't duplicate or re-implement work already represented by other open subtickets
- don't ignore acceptance criteria, constraints, or edge cases that live in the hierarchy
- treat the current issue as the execution boundary unless the hierarchy is clearly redundant and safe to simplify

## Don't

- Don't create noise.
- Don't proceed when blocked — route to Intervention with a clear comment.
- Don't create a branch, open a PR, or write implementation code until the open-question and readiness checks pass.
- Don't implement umbrella parents when the real work is in subtickets.
- Don't leave the work in a draft PR — the next stage depends on a non-draft PR and `In Progress` status.
