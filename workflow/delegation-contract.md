# Delegation contract — Hermes ↔ claude-code subprocess

The shared invocation pattern used by every workflow skill. Each skill's `SKILL.md` reads input via Hermes' Linear/GitHub/Discord integrations, then hands off the reasoning (or code-writing) to a `claude-code` subprocess per this contract.

Hermes owns all external state. The subprocess only reasons or writes code; it returns structured JSON; Hermes applies the result.

---

## Mode 1 — Reasoner

Used by `refine`, `review`, `router`, and the grouping phase of `fixer`. Read-only inside the subprocess; the subprocess never writes external state.

```
claude -p "$INPUT" \
  --bare \
  --model opus --effort high \
  --output-format json --json-schema "$SCHEMA" \
  --allowedTools Read \
  --max-budget-usd 10 \
  --max-turns 100 \
  --fallback-model haiku
```

- `$INPUT` is the bundled JSON the orchestrator built (the full ticket payload, sibling tickets, PR diff, threads — whatever the skill needs).
- `$SCHEMA` is the skill-specific JSON schema declared in the skill's `delegated.md`.
- `--bare` skips hook/plugin/MCP discovery and CLAUDE.md loading for fast, predictable startup. Requires `ANTHROPIC_API_KEY`.
- `--allowedTools Read` lets the subprocess open repo files for grounding, but blocks Edit/Write/Bash.
- Dual ceiling: `--max-budget-usd 10` caps spend, `--max-turns 100` caps iteration count.

---

## Mode 2 — Coder

Used by `implement` and the fix-applying phase of `fixer`. Operates inside a Hermes-prepared git worktree.

```
claude -p "$TASK_SPEC" \
  --model opus --effort high \
  --output-format json --json-schema "$SCHEMA" \
  --permission-mode auto \
  --add-dir "$WORKTREE" \
  --max-budget-usd 25 \
  --max-turns 100 \
  --fallback-model haiku
```

- `$TASK_SPEC` is the bundled task description + everything the coder needs to ground its work (ticket data, fix plan, branch name, etc.).
- `$WORKTREE` is an absolute path to a worktree Hermes prepared (already checked out on the right branch). The subprocess does all file edits and commits inside this worktree.
- `--permission-mode auto` lets the auto-mode classifier handle approvals so the subprocess can shell out for tests, linters, formatters, etc.
- No `--allowedTools` cap — coder mode needs the full default tool set.
- Dual ceiling: `--max-budget-usd 25` caps spend, `--max-turns 100` caps iteration count.

---

## Mode 3 — Tester

Used by `tester`. Like coder mode but the subprocess can read and shell out, not edit — testers report, they do not fix. Separation of concerns is enforced by the `--allowedTools` whitelist.

```
claude -p "$TASK_SPEC" \
  --bare \
  --model opus --effort high \
  --output-format json --json-schema "$SCHEMA" \
  --permission-mode auto \
  --allowedTools Read,Bash \
  --add-dir "$WORKTREE" \
  --max-budget-usd 10 \
  --fallback-model haiku
```

- `$WORKTREE` is the worktree Hermes prepared on the PR head.
- `Read,Bash` lets the subprocess inspect the repo and run the test suite, but blocks Edit/Write.
- Budget cap matches coder mode — test suites can be slow.
- No `--max-turns`.

---

## Input shape

Hermes always sends a single JSON object on stdin (or as the prompt). The object has:

- `kind` — discriminator: `refine` | `implement` | `review` | `fixer-group` | `fixer-fix` | `router` | `planner` | `tester`
- Skill-specific fields documented in the skill's `delegated.md`

---

## Output shape

The subprocess always returns JSON. The exact schema is skill-specific (see each `delegated.md`), but two universal cases:

- **Success** — schema matches what the skill's `delegated.md` declares; Hermes applies it as-is. **Hermes trusts the subprocess and does not validate the schema** beyond JSON-parseability. The schema is enforced at generation time by `--json-schema`; if `claude -p` returns malformed JSON anyway, treat it as failure.

- **Error** — the subprocess returns `{ "error": string, "reason": string }`. Hermes routes the ticket to Intervention with `reason` as the comment and stops.

---

## Hermes responsibilities around the call

- **Wall-clock timeout** — kill the subprocess after a reasonable cap (e.g. 20 min reasoner, 60 min coder); on timeout, route the ticket to Intervention.
- **One retry on overload** — `--fallback-model haiku` handles transient overload; if the subprocess returns an explicit "overload" error, retry once before bailing.
- **Cost logging** — every invocation's `total_cost_usd` and `subtype` from the result JSON gets logged for budget tuning.
- **Worktree lifecycle (coder mode only)** — `git worktree add` before, `git worktree remove` after success or failure. The subprocess does not manage the worktree.

---

## Tuning

Changing a flag (e.g. raising `--max-budget-usd`) happens here. All skills point at this contract; do not duplicate flags in skill files.
