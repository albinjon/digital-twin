---
name: fixer
description: Implement PR review feedback for a Linear ticket in Review Fixes status. Treats unresolved PR comments as a batch — groups overlapping ones by underlying concern, makes one coherent fix pass on the existing branch (no new branch, no new PR), pushes the changes, **resolves the PR review threads whose underlying concerns the fix actually addressed**, removes any "Human" label, and moves the ticket back to In Progress so the review loop can re-pick it.
---

# fixer

Apply outstanding PR review feedback in one coherent pass. The invoker supplies the ticket. The PR and feedback come from the ticket's linkage.

## Principles

- Treat PR feedback as a **batch**, not as isolated one-off commands.
- Prefer solving the underlying problem once rather than making repetitive or fragmented fixes.
- Prefer simple, maintainable, low-complexity solutions. Same engineering taste as `implement` — no defensive maximalism, surgical not band-aid, earn-its-keep.
- Make deliberate trade-offs when simplicity isn't possible and document them briefly in the Linear issue when relevant.
- Be action-oriented, but don't guess when comments conflict, require product judgment, or lack sufficient clarity.

## Readiness check

If something required is missing — no active PR, no accessible PR comments, unclear or contradictory feedback, missing repository access, missing credentials, missing technical context that can't be safely inferred — stop, add a concise comment on the Linear issue naming what's missing or conflicting, and route the ticket to Intervention. Don't continue.

## Procedure

### 1. Gather the feedback

Pull the relevant PR comments and review comments. Focus on unresolved, still-relevant comments. Ignore:
- comments clearly already addressed by the current branch state
- bot comments (unless they contain actionable technical failures)

Treat duplicate or overlapping comments as one underlying concern.

### 2. Group and deduplicate

- group overlapping comments by underlying concern
- deduplicate comments pointing to the same root problem
- treat the comments as **signals** for what to fix — not as instructions to make fragmented local edits

### 3. Decide which to act on

- multiple comments → one underlying issue → one fix set
- clearly subjective comments that don't materially improve correctness, maintainability, or product intent → don't over-rotate on them
- comments that conflict and the correct path isn't clearly inferable from repo patterns or engineering best practices → route to Intervention and explain the conflict; stop
- clearly a product / UX / stakeholder decision rather than engineering → route to Intervention; stop
- comment reveals a real bug, regression, missing test, weak abstraction, or maintainability problem → address it
- trivial / stylistic / low-value comments → don't make a new round of changes for these

### 4. Implement on the existing branch

- one coherent implementation pass per underlying concern
- on the **existing PR branch** — don't create a new branch, don't open a new PR
- continue the existing PR unless blocked

### 5. Resolve, push, and re-enter the review loop

After implementing the fixes:

- push the changes to the existing PR branch
- **resolve the PR review threads whose underlying concerns you actually addressed in this pass.** Mark them resolved on GitHub. Resolution is the signal that tells the next review pass (and the cron) this work is done — without it, the loop keeps re-picking the same PR because the unresolved-comment count never drops, and the priority logic keeps surfacing it as "the one job" even though the code is already fixed.
- only resolve threads you actually addressed. Threads you skipped (subjective, conflicting, out of scope, deferred to a follow-up) stay open — `review` or a human handles those.
- a short reply on the thread when resolving ("addressed in `<sha>`" or "fixed — resolving") is welcome but optional. Resolution itself is the contract.
- remove the `Human` label if present
- move the Linear issue back to `In Progress`

Don't add the `Human` label from this skill — that's `review`'s call on the next pass. Don't open new top-level PR comments or new threads; that's still `review`'s territory. Replying-and-resolving on existing threads is the only PR-write this skill does.

If blocked at any point:
- add a concise explanatory comment on the Linear issue
- route the issue to Intervention
- don't continue

## Don't

- Don't create noise.
- Don't open new top-level PR comments or new threads — that's `review`'s job. Only resolve threads you actually fixed (with an optional short reply when resolving).
- Don't resolve a thread you didn't actually address. Resolution is a claim that the underlying concern is gone; only make it when it's true. Leaving a thread open is the honest call when the fix is partial, deferred, or subjective.
- Don't implement the same underlying fix multiple times.
- Don't create a new branch or a new PR.
- Don't proceed when feedback is contradictory, product-driven, or insufficiently clear — route to Intervention.

Treat the move back to `In Progress` as re-entering the PR review loop. The `review` skill picks it back up — and now sees only the threads that genuinely still need attention, which is what makes Outcome 2 (Human handoff) reachable when the implementation is actually complete.
