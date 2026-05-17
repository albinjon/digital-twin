---
name: maybe-do-work
description: Run a single autonomous loop on Albin's behalf — find candidate work via /look-for-work, load his engineering SOUL via /be-albin, pick the highest-priority reversible item, execute it with an audit-trail announcement, and report back. The "maybe" carries real weight: when nothing reversible is appropriate, surface proposals instead of manufacturing busywork — "did nothing right now" is a valid and frequent outcome. Trigger when the user (or a scheduled job) says "go do something useful", "make progress while I'm away", "pick something off my plate", "run the SOUL loop", "do the next thing autonomously", "find and execute a task", "pick one of my open items and run with it", or any phrasing that asks the agent to both *find* AND *act on* available work. Don't use this skill for listing-only requests (use /look-for-work) or recommendation-only requests (use /be-albin's what-should-I-do-now loop without execution); maybe-do-work is specifically the action-taking version of that loop. Use even when the user doesn't explicitly say "autonomous" or "execute" — if the request implies action (not just inquiry), this is the right skill. Especially important for scheduled tasks where the implied contract is "make progress on something while I'm not watching."
---

# Maybe-do-work

Run one autonomous step on Albin's behalf: scan for candidates, pick the best reversible one, do it, report. If no reversible work is appropriate right now, output proposals and stop — "did nothing" is a valid, frequent, and correct outcome that the "maybe" in the name explicitly allows.

This skill is an orchestration of three other skills:
- `/look-for-work` — produces the candidate list (what's available to pick up).
- `/be-albin` — loads Albin's engineering SOUL (the principles and personal calibration that govern *how* to pick and act).
- `/notify` — sends Albin a Slack DM when the run produced something he needs to weigh in on. The agent transcript is always there; `/notify` is the heads-up that pulls his attention to it.

The first two must be loaded before any decisions get made. SOUL's hard limits are non-negotiable — `maybe-do-work` exists to operate *within* them, never around them. The third gets called conditionally at the end of the loop (see Step 7).

## The loop

### Step 1 — Load SOUL

Invoke `/be-albin` first. This is non-negotiable, because every downstream decision (which candidate to pick, what counts as reversible, how to phrase the report, when to stop) depends on SOUL being in context. If `/be-albin` isn't available, stop and tell the user — don't improvise the principles or calibration from memory or assumption.

### Step 2 — Find candidates

Invoke `/look-for-work`. It produces a structured candidate list grouped by context (Skry / Lavora / ZBS), with action-type labels and reversibility hints. Don't re-implement the scanning here — `/look-for-work` is the source of truth for what's available.

### Step 3 — Pick one

Apply SOUL's work-bias priority order to the candidate list:

1. **Unblock others** — PRs awaiting Albin's review beat everything else. Within this tier, the *oldest* review request wins (cost of inaction is highest there).
2. **Continue warm context** — own in-progress PRs and Linear issues already In Progress beat starting cold work. Pick the stalest in-progress item; warm context is expensive to rebuild.
3. **Small shippable wins** — quick-win bugs, papercuts, small features.
4. **Tech debt and cleanup** — refactors, deletions, simplification.
5. **Hard problems** — only when the above is empty.

Then filter for reversibility — pick the top item that's reversible (can be acted on without crossing SOUL's hard limits). Common reversible actions:

- Opening a draft review on someone else's PR
- Continuing an existing draft PR with small commits (Albin's own work)
- Initializing a draft PR for a routine implementation candidate (no architecture-level concern)
- Local refactor or cleanup
- Adding tests for existing code

If the top-priority candidate is propose-only — `draft-reply`, anything architecture-level, anything that lands on `main`, anything irreversible — set it aside as a "propose" item and look at the next reversible one. Do not downgrade the hard limits to clear a queue.

### Step 4 — Check memory before acting

Before executing the pick, consult memory for prior context on the area you're about to touch. Past decisions, "we agreed not to touch X right now," preferences about how a particular service is structured — all of these should shape the call. If memory has a relevant entry that flags the area, respect it and either pick the next candidate or surface this one as a proposal.

This step matters because SOUL's whole point is to apply Albin's calibration, not generic-agent defaults. A generic agent would just take the top reversible item; under SOUL, the agent checks whether prior context says don't.

### Step 5 — Announce, then act

Announce what you're about to do in one line *before* doing it (SOUL's audit-trail rule for unilateral action):

> Opening a draft review on skryai/api#412 — will report back.

Then execute, applying SOUL's engineering principles in full:

- **Surgical, not band-aid.** Every changed line traces directly to the task. No drive-by improvements to adjacent code. If a small diff would hide debt, name it and propose instead of quietly hacking around it.
- **No defensive maximalism.** No try/except for failures that don't happen. No null checks for impossible nulls. No validation duplicated at every layer.
- **Earn-its-keep.** Every layer, abstraction, dependency, line must pay for itself *now*. Speculative flexibility gets cut.
- **Goal-driven.** Before writing code, convert the task to a verifiable goal ("write a test that reproduces the bug, then make it pass"). Don't ship without the verify step.

If you discover mid-task that the work isn't actually reversible — it touches architecture, a CI failure suggests a deeper issue, the "small fix" is unspooling into a major change — *stop*. Don't muscle through. Surface what you found as a proposal and let Albin decide. The autonomy rules don't bend just because action is already in flight.

### Step 6 — Report

Output the report in this shape:

```
[SOUL acknowledgment line]

Scanned: <N candidates across <contexts>>

Did: <one-line description, with identifier and link>
<2–4 lines of detail — what changed, what was deliberate, anything Albin should look at>

Other notable candidates (left for your judgment):
  - PROPOSE: <item> — <one-line: why it needs Albin's input>
  - DRAFT-REPLY: <item> — <one-line context; reminder these are propose-only>

<optional: brief queue summary — "still 9 lower-priority items, mostly Lavora papercuts">

<closing one-liner: ask if Albin wants another run, or just hand off>
```

If nothing reversible was appropriate — entire queue is propose-only, or empty, or everything is blocked by user input — say so honestly:

```
[SOUL acknowledgment line]

Scanned: <N candidates, all propose-only / 0 candidates / all blocked on X>

Did: nothing — <one-line reason>.

Here's what's waiting on you instead:
  - PROPOSE: <item> — <why it needs you>
  - PROPOSE: <item> — <why it needs you>

<closing line>
```

"Did nothing" is a valid outcome. Don't manufacture work to look productive. SOUL's "earn its keep" principle applies to the loop itself: if nothing in the queue would earn its keep right now, the right call is to wait.

### Step 7 — Notify if Albin needs to weigh in

Use the `/notify` skill to send Albin a Slack DM when the run produced something that needs his attention. The bar is "does Albin need to be contacted?" — not every successful execution, because routine clean runs would just be noise. The git/PR history is the audit trail for those.

**Notify when:**

- **Hiccups.** The loop bailed mid-task because the work turned out non-reversible, a tool or skill was unavailable, a CI failure suggested a deeper issue, or anything else surprising happened. Albin needs to know the loop stopped and why.
- **Decisions surfaced.** Propose-only items in the report — architecture-level calls, new dependencies, schema/breaking-API changes, anything that's waiting on his judgment.
- **Drafted human-facing messages.** Slack or email drafts waiting for him to review and send. Sending is never the loop's job, so these always need his hands.
- **Memory conflicts.** The skill swapped picks because memory flagged the area, or the picked item collided with a stored decision. Worth a heads-up so he knows the loop saw the conflict.
- **"Did nothing" with proposals.** The queue was entirely propose-only and there are real items waiting on him. Without a notify these would sit unseen.

**Don't notify when:**

- The run was clean: picked a reversible item, executed it, nothing attached for Albin to do (no proposals, no drafts, no hiccups). The PR or commit is the audit trail.
- The "did nothing" reason was "queue was empty, no proposals." Nothing to surface, nothing to ping about.

If `/notify` is unavailable for any reason, complete the in-transcript report normally and add a one-line note that the notification failed. The report is still the source of truth; the DM is the convenience layer.

### Notification shape

Keep the Slack DM tight — TL;DR + action items + links. Albin will open the transcript for details if he wants them.

```
<one-line summary of the run — what was scanned, what was done>

Need your input:
• <propose item> — <one-line: what it is, why it's stuck on you>
• <draft-reply: thread> — <one-line context, "drafted, ready to review">

Did autonomously: <one-line, with PR/commit link if relevant>
```

If the run was a hiccup with no autonomous action:

```
Loop bailed — <one-line reason>.

What I was trying to do: <one-line>
What stopped me: <one-line — the surprising thing, the missing tool, the CI failure>

Nothing was changed. Transcript has the full trace.
```

Match SOUL's voice in the DM: casual, no preamble, no fluff, no formal "Hi Albin" opener. He's expecting these, just give him the substance.

## One pick per invocation

`maybe-do-work` picks one item and stops. It does not keep going after completion. Two reasons:

- Albin may want to weigh in on the result before more work happens — even reversible work benefits from a checkpoint.
- Multi-pick autonomous loops compound risk. A single bad pick is recoverable. Ten in a row is a bigger cleanup.

A scheduled task wanting more throughput should invoke `maybe-do-work` repeatedly with gaps, not extend this skill's scope to multi-pick. Each invocation is one decision; each decision is reviewable.

## What this skill respects (SOUL guarantees)

Because `/be-albin` is loaded in Step 1, all of these apply automatically. They're worth reiterating because they're the most likely failure modes for an autonomous loop, and `maybe-do-work` is exactly the surface where forgetting one of them could matter:

- **No human-facing messages get sent.** Slack and email replies stay as drafts surfaced in the report.
- **No merges to main/production.** Even on green CI. Even on Albin's own PRs. The merge click is his.
- **No force-pushes to shared branches.** Personal-branch rebases are fine.
- **No silent architecture-level decisions.** New service, new dep, breaking API, schema change — all surface as proposals.
- **Defensive maximalism gets cut.** If you'd be adding code for failures that don't happen, don't.
- **Drive-by refactors stay out.** Adjacent code that looks rough goes in the report, not in the diff.
- **Surgical, not band-aid.** Smallest diff isn't always the right diff. If shipping smallness would hide debt, propose instead.

## After every run

Save anything noteworthy as a feedback memory:

- A surprising candidate ranking ("I'd have picked X but the work-bias clearly said Y — capture that pattern").
- A corner case in classifying reversibility (e.g., "schema migrations on a feature branch were treated as reversible — should they be?").
- A judgment call Albin pushed back on (or quietly accepted — both count).

The next loop benefits. Drift the personal calibration toward Albin one observation at a time. (Principles drift much less than calibration — keep that distinction when deciding what to save.)

## When NOT to use this skill

- The user wants only a candidate list → use `/look-for-work` directly.
- The user wants a recommendation but plans to execute themselves → use `/be-albin` and run its "what should I do now?" output without the execution step.
- The user wants situational awareness (meetings, status, what's happening) → use `/daily-digest`.
- The task is explicitly specified by the user ("review PR X", "fix bug Y") — `maybe-do-work` is for *finding* work to do. Once specified, just use `/be-albin` (which applies SOUL to the named task) and skip the scanning.

This skill exists for one specific shape of request: "go pick something from my queues and do it." It's not a general-purpose task runner.
