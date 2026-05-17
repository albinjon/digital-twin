---
name: look-for-work
description: Find concrete candidate work items for Albin (or an agent acting on his behalf) to pick up next — PRs awaiting review, his own open/stale PRs, assigned tickets, threads needing a drafted reply, implementation candidates. Produces a ranked, grouped list of actionable next-steps with action-type labels and reversibility hints, not a status briefing. Trigger when the user (or an agent) says "what should I do now", "what should I pick up", "find me something to do", "what's next", "give me my next task", "what's on my plate to actually work on", or any variation of "find me work". Always invoke when /be-albin is running its "what should I do now?" loop — look-for-work is the canonical candidate-finder it relies on. Distinct from daily-digest: daily-digest gives situational awareness (meetings, status, what's happening); look-for-work outputs actionable candidates structured for an agent to reason over. When both could fit, prefer look-for-work if the user wants something to *do*, daily-digest if they want to *understand* their situation.
---

# Look-for-work

Produce a ranked list of concrete candidate work items the user (or an agent acting on his behalf) can pick up next. The goal is *candidate generation*, not situational awareness — daily-digest is the right tool when the user wants a status overview. Use this skill when the next step is acting, not informing.

The output is designed to be consumed by both humans and agents. An agent operating under SOUL (via `/be-albin`) consumes it as the first step of the "what should I do now?" loop, then layers on autonomy classification, memory checks, and ranking. A user invoking it directly gets a structured candidate list they can pick from.

## User context — know where things live

Albin has three distinct work contexts. Always keep them visually separated in your output:

- **Skry** — his employer / day job. Slack and Email (Gmail) are Skry-only. Calendar is primarily Skry. Most engineering work lives here.
- **Lavora / MyLedger** — a side project (same thing, two names). Linear is Lavora-only. GitHub has Lavora repos.
- **ZBS (Zenbuddhistiska Samfundet)** — another side project. Only GitHub.
- **GitHub** — spans all three contexts. PRs and issues may belong to Skry, Lavora/MyLedger, or ZBS repos. Group them by repo when surfacing.

Never mix these up. A Slack message is Skry work. A Linear issue is Lavora work. A GitHub PR could be either — check the repo name.

## Step 1: Scan candidate sources in parallel

Launch all queries simultaneously — don't wait on one before starting the next. Each query targets a specific kind of candidate:

### GitHub — review queue, own work, assigned issues

Use the GitHub MCP tools. Get the user's GitHub handle once via `get_me`, then run in parallel:

- **PRs awaiting your review** — `search_pull_requests` with `is:open is:pr review-requested:@me`
  → action type: **review**
- **Your own open PRs** — `search_pull_requests` with `is:open is:pr author:@me`
  → action type: **continue-own-pr** (flag `draft:true` and anything stale >3 days)
- **Issues assigned to you** — `search_issues` with `is:open is:issue assignee:@me`
  → action type: **implement** for feature-flavored issues, **investigate** for bug-flavored

Group results by repo, then map to context (Skry / Lavora / ZBS).

### Linear — Lavora assigned tickets

- Issues assigned to me, in `In Progress` or `Todo` state, ordered by updatedAt
- Limit to 20; flag priority 1 (Urgent) and priority 2 (High)
- → action type: **continue** for In Progress, **implement** for Todo

If the In-Progress query returns empty, the queue might genuinely be clear — but double-check by running without the state filter before reporting "nothing in flight."

### Slack — threads needing a drafted reply (Skry only)

- Direct mentions of me in the last 24–48h: `to:me after:<yesterday>`
- DMs and threads I'm part of where the last message is from someone else and looks like it expects a response
- Filter out: automated/bot messages, social/banter channels, ambient discussion with no question or decision pending
- → action type: **draft-reply**

These are always "propose only" — sending is never automated. Don't draft the reply itself in this skill; the caller (a SOUL-operating agent, or the user) does that separately.

### Gmail — threads needing a drafted reply (Skry only)

- Unread threads in primary inbox: `is:unread in:inbox -in:draft`
- Limit to 10; flag anything from named colleagues or stakeholders, or that looks like it's asking for a decision
- → action type: **draft-reply**

Same constraint as Slack: identification only, no actual drafting in this skill.

## Step 2: Normalize each candidate

For every candidate, capture:

- **Source** — `github-pr` / `github-issue` / `linear` / `slack` / `gmail`
- **Context** — Skry / Lavora / ZBS
- **Action type** — `review` / `continue-own-pr` / `implement` / `investigate` / `continue` / `draft-reply`
- **Title or one-line summary**
- **Identifier** — PR number, issue key, thread link (so the caller can route directly)
- **Age** — how long it's been sitting (helps the caller judge urgency)
- **Who else is involved** — author for PRs, reporter for issues, sender for threads
- **Reversibility hint** — most action types are reversible-leaning (review-as-draft, draft-PR, etc.). `draft-reply` is always propose-only (sending is never automated). `implement` for issues that touch architecture-level concerns (new service, new dep, schema change) leans propose; routine implementation leans reversible. This is a *hint* — the caller (operating under SOUL) makes the final autonomy call.

## Step 3: Order within each context

Within each context, sort by:

1. **Unblock-others first** — PRs where someone is waiting on Albin's review beat everything else. Surface age prominently ("waiting 2 days") so the cost of inaction is visible.
2. **Continue warm context** — own in-progress PRs and Linear issues already In Progress beat starting cold work. Finishing earns more than starting; warm context is expensive to rebuild.
3. **Quick wins** — small, scoped Todo tickets, bug-flavored issues that look like papercuts.
4. **Larger / architectural items last** — anything that looks like more than a half-day, or that touches architecture-level concerns. These are likely "propose" candidates anyway.

Across contexts, present Skry first (day-job, time-sensitive), then Lavora, then ZBS.

## Step 4: Output format

Compact, scannable, grouped by context. For each candidate, one line:

```
[action-type] <identifier> — <title> (<age>, <who else>, <flags>)
```

Flags include things like `DRAFT`, `STALE`, `P1`, or `arch` (for items that look architecture-level and probably need to be proposed rather than acted on unilaterally).

### Example output

```
**Skry — GitHub**
review              skryai/api#412   — "Fix auth redirect on logout"      (2d, @marie)
review              skryai/web#88    — "Add retry on token refresh"       (4h, @marie)
continue-own-pr     skryai/api#398   — "Retry logic on HTTP client"       (DRAFT, stale 6d)

**Skry — Linear**
(none assigned)

**Skry — Slack**
draft-reply         #platform thread — Jonas re: session token rotation   (3h)

**Skry — Gmail**
(3 unread, all automated — skipping)

**Lavora / MyLedger — GitHub**
implement           lavora/myledger#241 — "Credit invoice autofill bug"   (P1, assigned)
review              lavora/myledger#234 — "Add tax-rate per line item"    (1d, @ext-contractor)

**Lavora / MyLedger — Linear**
continue            LAV-288 — "Credit invoice autofill bug"              (In Progress, 2d)
implement           LAV-243 — "Invoice payment terms"                    (Todo, P2)

**ZBS — GitHub**
(queue clear)
```

End with a one-line summary noting the count and where activity is heaviest — useful context for the caller deciding what to recommend:

```
12 candidates total. Skry GitHub is the busiest queue (3 review requests aging 4h–2d).
```

## What this skill deliberately doesn't do

- **No drafting of replies.** It identifies threads where a reply is needed; the caller (a SOUL-operating agent, or the user) drafts in a separate step. This is so the skill stays cheap to run — drafting is expensive and the user might pick a different candidate anyway.
- **No firm reversible/propose classification.** It hints with the `arch` flag and reversibility-hint logic, but the caller (operating under SOUL) makes the final autonomy call — they have access to memory and the broader judgment context.
- **No "top recommendation" pick.** Ranking by work-bias priority and producing a single "do this next" verdict is the SOUL-operating caller's job. Look-for-work surfaces the candidates honestly; the caller adds opinion.
- **No calendar / meetings / status info.** That's daily-digest's job. Look-for-work is action-only.
- **No drafted PRs or executed work.** Generating actions on candidates is for downstream tools (a SOUL-operating agent, or the user choosing manually). Look-for-work observes, doesn't act.

## Edge cases

- **All queues empty.** Say so honestly: "Nothing actionable right now — queues are clear." Don't manufacture work to fill space.
- **One context dominates.** Fine to call out ("Lavora has the most going on today"). Don't artificially balance.
- **An item appears in multiple sources** (e.g., a Linear ticket with a GitHub PR for the same work). Surface once at the most actionable layer (usually GitHub), mention the linkage on that line.
- **Ambient discussion threads with no question.** Skip them — look-for-work is about actionable items. A Slack thread where everyone's just thinking out loud isn't a candidate.
- **MCP unavailable / auth missing.** Report the gap honestly ("Linear MCP not connected — couldn't scan Lavora tickets") rather than silently dropping a context. The caller can decide whether to proceed or fix auth first.

## Why this separation from daily-digest

Daily-digest answers "what's the state of my world?" — meetings, status, ambient activity, decisions in flight. It's a briefing for a human about to start their day.

Look-for-work answers "what's the next concrete thing I (or an agent) could pick up?" — actionable candidates, normalized for downstream consumption, with enough metadata that a SOUL-operating agent can apply autonomy rules and produce a single "do this next" recommendation. It's a feed, not a briefing.

When both might apply: prefer daily-digest when the user wants to *understand* their situation; prefer look-for-work when the user (or an agent) wants something to *do*. They can be invoked back-to-back too — daily-digest for the context, then look-for-work to get unstuck.
