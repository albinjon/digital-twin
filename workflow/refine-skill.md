---
name: refine
description: Refine a Linear backlog issue — improve the description for clarity, deduplicate within the same project, classify by type and apply labels, then route the ticket either to Todo (if implementation-ready) or Intervention (if blocked on a decision). Operates on one issue per invocation. Skips entirely if the issue has the "Human" label.
---

# refine

Refine a single Linear backlog issue so it becomes clear, non-duplicative, and ready either for implementation or for human intervention. The invoker supplies the issue.

If the issue has the `Human` label, do nothing and stop — that label signals the issue is in the human lane.

## Categories

- **Feature** — new capability, or change to existing feature/behavior/copy.
- **Bug** — defect or unintended behavior.
- **Chore** — copy-only change, refactor, dependency upgrade, internal maintenance, non-behavioral cleanup.

## Principles

- Preserve intended meaning. Refinement clarifies, it doesn't rewrite.
- Prefer concise, structured descriptions over verbose ones.
- Use repository context to infer likely scope or technical detail when the issue is brief.
- Don't guess when the issue can't be safely refined — route to Intervention instead.

## Procedure

### 1. Read context

Read the issue title, description, comments, parent (if any), and subtickets (if any). Decide whether the current issue is the correct execution unit, or whether real execution happens in subtickets.

### 2. Check for duplicates — same project only

Search the same project for similar tickets. **Cross-project deduplication is forbidden.** If a similar ticket exists in another project, don't merge them; you can comment with a reference if useful.

If the issue duplicates an older active ticket in the same project:
- prefer the oldest active (non-closed, non-archived) ticket as canonical
- extract any new info from this issue and add it to the canonical
- comment on this issue referencing the canonical
- move this issue to `Duplicate`
- stop here — no further refinement

### 3. Refine the description

Improve where useful:
- clarify the problem or requested change
- make the request more specific
- separate background, expected behavior, and implementation-relevant detail
- fold useful info from comments and hierarchy into the description
- correct obvious ambiguity or inconsistency

If the issue is very brief, investigate the repository to determine whether there's an unambiguous way forward; update accordingly.

### 4. Resolve open questions

If open questions remain after the description refresh:
- check whether comments or hierarchy already resolve them — if so, fold the answer in and close the question
- if open questions still remain that need human input, the ticket does NOT move to Todo

### 5. Classify and label

| Type | Labels |
|------|--------|
| Feature | `Feature` + `FE` / `BE` / both |
| Bug | `Bug` + `FE` / `BE` / both |
| Copy-only / chore / refactor | `FE` / `BE` / both (no `Feature` or `Bug` unless clearly applicable) |

Area rules: `FE` for frontend / UI / client-side / user-visible copy. `BE` for backend / APIs / jobs / integrations / persistence / auth / server-side. Both if it genuinely spans.

### 6. Route

Move to **Todo** only when ALL of these hold:
- not a duplicate
- description is sufficiently clear
- no open questions remain
- the current issue is the correct execution unit (not an umbrella parent whose work belongs in subtickets)

Move to **Intervention** when:
- ambiguity remains that needs human input
- repository context doesn't give a confident implementation path
- ticket hierarchy is materially unclear and can't be safely simplified
- open questions need product / UX / business / stakeholder input

When routing to Intervention, leave one concise actionable comment naming what's unclear or what decision is needed. Don't comment vaguely.

## Hierarchy handling

When the current issue is **top-level with subtickets**:
- if the work is one coherent implementation unit, consolidate essential info into the top-level and simplify the hierarchy where possible
- if the work is genuinely multiple distinct execution units, keep the top-level concise (summary, scope, shared constraints, acceptance intent); refine subtickets individually as the real execution units
- don't duplicate full implementation detail across parent and subtickets
- don't route an umbrella parent to Todo when the real work is in subtickets

When the current issue is a **subticket**:
- read the parent for context, shared constraints, scope boundaries
- refine the subticket so it's independently implementable without copying parent detail wholesale

If subtickets exist but add no planning value, collapse the unnecessary complexity.

## Don't

- Don't create noise — no unnecessary edits or commentary.
- Don't deduplicate across projects.
- Don't move unclear tickets to Todo to push them forward.
- Don't treat umbrella parents and execution subtickets as interchangeable.
