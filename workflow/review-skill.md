---
name: review
description: Devil's-advocate review of the active PR linked to a Linear ticket in In Progress (no "Human" label). Resolves previously-raised PR comments that are now addressed, leaves substantive new feedback only, adds a summary comment, then routes the ticket to one of three outcomes — Review Fixes (autonomous next pass), Human label (handoff to human review), or Intervention (blocked on a decision).
---

# review

Stress-test the active PR on a Linear ticket and decide what happens next. The invoker supplies the ticket. The PR is found from the ticket linkage.

If the issue has the `Human` label, do nothing and stop. If the ticket isn't in `In Progress`, do nothing and stop.

## Review objective

Devil's-advocate review: identify what could go wrong, what may have been overlooked, what may not hold up under real usage, maintenance, or production conditions.

Also review existing unresolved PR comments and resolve those whose underlying concerns are now clearly addressed by the current code.

## Principles

- Prioritize correctness, regressions, maintainability, simplicity, and real-world robustness.
- Focus on substantive concerns. Don't nitpick style.
- Be skeptical but fair.
- Prefer high-signal over volume.
- Consider repository patterns and surrounding context before raising concerns.
- Don't invent problems not grounded in the code, diff, PR discussion, or repository context.
- Don't continue the autonomous loop for trivial, stylistic, or low-value observations.
- If review feedback is becoming repetitive or low-value, hand off to human review instead of continuing autonomous iteration.

## Readiness check

If something required is missing — no active PR, inaccessible PR context, missing repository access, or missing technical context that can't be safely inferred — stop, add a concise comment naming what's missing, and route the ticket to Intervention. Don't continue.

## Procedure

### 1. Handle existing unresolved comments first

Before raising new concerns:
- review existing unresolved PR comments
- for each, decide whether it's still relevant given the current code
- resolve comments whose underlying concern is clearly addressed
- leave unresolved comments in place if the concern is still valid or only partially addressed
- don't reopen settled discussions unless the code reintroduced the problem
- don't create duplicate comments for concerns already captured by existing unresolved ones

Resolve a comment only when the code now clearly addresses the underlying issue. Don't resolve if the fix is incomplete, ambiguous, or merely adjacent. Prefer correctness over optimism.

### 2. Examine the PR

Pay special attention to:
- correctness and unintended behavior
- edge cases and failure modes
- regressions in existing functionality
- missing validation or error handling
- security, auth, permissions, and data exposure risks
- data integrity, migrations, and backward compatibility
- performance and unnecessary complexity
- observability, logging, and debuggability
- test coverage gaps
- maintainability and alignment with existing architecture
- mismatch between the linked issue and the implemented change

### 3. Leave comments

- one or more PR comments where it improves clarity
- high-signal and directly actionable
- group related concerns together rather than fragmenting unnecessarily
- don't duplicate existing unresolved comments unless there's genuinely new information
- end with a concise summary comment on the PR stating the review outcome

The summary should say:
- whether substantive actionable concerns were identified
- whether previously raised comments were resolved
- whether the issue is being sent to Review Fixes, handed off to human review, or routed to Intervention

### 4. Pick exactly one outcome

#### Outcome 1: Autonomous Review Fixes

Choose when:
- substantive actionable engineering concerns were identified
- the concerns can be addressed without product / UX / business / stakeholder decisions
- the concerns are not contradictory
- they're important enough to justify another autonomous fix cycle

Action: resolve any previously-addressed PR comments, add new PR comments for still-relevant concerns, add the summary comment, **move the issue to `Review Fixes`**.

#### Outcome 2: Human review handoff

Choose when:
- no substantive actionable concerns were identified
- only minor / stylistic / low-value suggestions remain
- the loop is starting to revisit the same class of concerns without new findings
- the PR is ready for human review

Action: resolve any previously-addressed PR comments, add the summary comment, **add the `Human` label**, leave the issue in `In Progress`.

#### Outcome 3: Intervention

Choose when:
- the way forward requires product / UX / business / stakeholder input
- review concerns conflict and the correct path isn't clearly inferable from repo patterns or engineering best practices
- the PR or repository context is too unclear to review safely
- a blocking dependency or access problem prevents meaningful review

Action: add a concise comment explaining the blockage or decision required, **move the issue to `Intervention`**.

## Don't

- Don't create noise.
- Don't perform implementation from this skill — that's `fixer`'s job.
- Don't move to Review Fixes for trivial, stylistic, or low-value observations.
- Don't focus on trivial stylistic preferences.
- Don't continue autonomous iteration when it's no longer producing meaningful value — hand off to human review.
- Don't leave previously-raised comments unresolved when the current code clearly addresses them.

Treat `In Progress` as the review-loop state for any issue with an active non-draft PR, unless it's been explicitly routed to Review Fixes, Intervention, or handed off via the `Human` label.
