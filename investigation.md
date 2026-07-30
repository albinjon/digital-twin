# ZBS Poller Review-Gate Investigation

Date of investigation: 2026-07-22
Scope: ZBS poller and worker outputs from 2026-07-20 through 2026-07-22 UTC

## Executive conclusion

The repeated ZBS failures are not one defect. They fall into four classes:

1. Actionable semantic review rejection.
2. Non-convergent semantic review rejection caused by unclear evidence or requirements.
3. Reviewer/process failure, including reviewer exits without usable output and outer worker tool-limit exhaustion.
4. Test-runtime/provider failure after the semantic gate has already passed.

The Claude Code upgrade should primarily affect class 3/4 failures involving the Bash safety classifier. It will not, by itself, resolve semantic requirements conflicts such as ZBS-122 or non-convergent evidence requests such as ZBS-128.

## Evidence from the last three days

The worker-state ledger contained 15 ZBS worker runs in the period. Among implementation actions:

- 10 `start_implementation` actions were recorded.
- 6 passed and produced a commit/PR handoff.
- 4 returned `needs_changes`.
- ZBS-128 additionally had 2 `apply_fixes` actions that returned `needs_changes`.
- 6 test actions ended as `runtime_missing`.
- The dominant runtime reason was Bash safety-classifier blocking of npm/Node dependency bootstrap or test execution.
- One run reached the delegated weekly usage limit.

Successful gate examples:

- ZBS-129: three concrete review corrections, including migration visibility/tracking, then PR #71.
- ZBS-123: initial semantic rejection, then corrected changeset and PR #80.
- ZBS-130: PR #72.
- ZBS-107: PR #75.
- ZBS-127: PR #79.

Semantic/non-convergent examples:

- ZBS-128: the audit found no additional image usages, but the reviewer continued to request explicit codebase-wide coverage evidence. Repeated audit passes did not change the source and the gate remained blocked.
- ZBS-122: the reviewer continued to request persistent database storage, real user provisioning, real email delivery, and complete role/filial wiring. These requirements conflicted with the repository's `AGENTS.md`, which prohibits introducing a real database, ORM, external auth provider, or storage backend unless specifically requested.
- ZBS-119: the semantic reviewer exited with code 1 twice without returning review output. The worker then hit the outer tool-call limit before final run-state release.

## Current runtime state at investigation time

- Claude Code reports version `2.1.217`.
- The shared delegation contract still pins `sonnet-5` and uses `auto` permission mode for coder/tester calls.
- ZBS-127 is currently `Todo`, has no `Human` label, and has an existing PR #79 attachment.
- ZBS-127's previous run handed off because tests could not run; it did not indicate a semantic-gate rejection.
- An active SQLite worker lock remains for ZBS-119 until `2026-07-22T12:39:40Z`. Do not start another ZBS-119 worker while that lock exists. Use owner-token-aware helpers for recovery; do not edit SQLite manually.

## Recommended steps forward

### 1. Canary the upgraded Claude runtime

Run one controlled worker and verify all relevant modes, not just `claude --version`:

- structured reasoner output;
- coder file edits and Bash execution;
- tester npm/Node execution;
- semantic reviewer output;
- owner-token lock release and cooldown persistence.

ZBS-127 is a suitable canary because it already has PR #79 and was previously blocked primarily at test execution rather than implementation review.

### 2. Re-test existing review-passed PRs before resuming broad polling

Prefer testing existing PR heads rather than regenerating code:

- PR #71 / ZBS-129
- PR #72 / ZBS-130
- PR #75 / ZBS-107
- PR #79 / ZBS-127
- PR #80 / ZBS-123

A successful result should include the exact tested SHA and the actual test command/output. `runtime_missing` is not a test result.

### 3. Bound semantic repair loops

- Allow at most two concrete semantic repair cycles.
- Preserve exact reviewer feedback in the next bundle.
- If the same blocker returns, classify it as non-convergent and hand off.
- If the reviewer asks for evidence, produce the evidence once.
- If the evidence is already present or the reviewer does not name an acceptable artifact, stop retrying.

### 4. Strengthen the semantic-review contract

Every `needs_changes` result should name:

- the concrete blocker;
- the affected path or missing artifact;
- why the requirement follows from the ticket;
- the minimal acceptable resolution.

The review bundle should include the ticket acceptance criteria, `AGENTS.md` constraints, changed-file list, coverage searches/commands, diff, and test status. Generic reviewers must not demand integrations explicitly prohibited by repository guidance unless the ticket authorizes them.

### 5. Separate failure telemetry

Record distinct categories for semantic rejection, reviewer process failure, coder blocked-after-edits, tester runtime missing, provider quota, outer tool-limit exhaustion, and lock-release failure. Converting all of these to `request_human` hides the actual failure source.

### 6. Recover ZBS-119 separately

After confirming the worker is no longer active, inspect the preserved worktree and release the lock using the owner-token-aware helper. Do not use a fresh worker to compete with the existing lock.

## Canary record

The ZBS-127 canary was requested after this investigation was written. Its scheduler job ID, execution result, exact tested SHA, test command, and lock/cooldown verification should be appended below after execution is independently verified.

### Canary result

Verified execution completed 2026-07-22 07:52:52–08:01:27 UTC.

- Scheduler job: `fac2ce6f8aba` (`canary-worker-ZBS-127`).
- Note: the direct scheduler trigger initially reported `execution_success: false`, but the execution ledger and worker-state database later showed a completed worker run. Scheduler acknowledgement and worker execution must therefore be verified independently.
- Prechecks passed; ZBS authorization and repository mapping were correct.
- Existing PR #79 was detected; no duplicate implementation or new changeset was created.
- PR #79 was already merged during the run, merge commit `f91025216bf62fdaca525f851f0b64b62a91f8db`.
- Tester successfully ran `npm test`: **42 passed, 0 failed**.
- Tested head SHA: `5f362c3a446a81d79d5124a773d6b108d7c96b4f`.
- The ticket moved `Todo → In Progress → Done` and received no `Human` label.
- The semantic changeset gate was not exercised because implementation already existed in the attached PR.
- The first reasoner invocation failed with `error_max_structured_output_retries` after five structured-output attempts; the retry succeeded and subsequent reasoner/tester calls returned valid structured output.
- Successful subprocess envelopes reported the Haiku fallback model.
- Total delegated cost: `$0.3526134`.
- Final exit reason: `terminal-state:Done`.
- Owner-token lock release and cooldown persistence were verified. Run ID: `4669d452-dc20-4ed4-82c7-5d91132f8b9e`.

## Canary interpretation

The Claude upgrade appears to have resolved the previously observed npm/Bash test-execution blocker for this canary: `npm test` ran successfully and passed all 42 tests. It did not provide a clean end-to-end reasoner path because the first structured-output attempt still failed and required retry/fallback. It also did not test the semantic changeset reviewer because ZBS-127 already had a merged PR.

Next canary should target a ticket/worktree that exercises semantic review, while preserving the same independent verification of subprocess output, exact SHA, lock release, and cooldown.

## Poller dispatch failure investigation (2026-07-22 12:13 UTC)

A direct run of the existing `poller-ZBS` job reproduced the dispatch failure:

- Poller execution itself succeeded and selected `ZBS-124` correctly.
- The worker was not created.
- The poller response reported: `required cronjob tool is unavailable in this environment`.
- No new worker lock or worker run was written.
- The cron job nevertheless recorded `last_status: ok`.

### Root cause

The installed Hermes Agent implementation intentionally disables the `cronjob` toolset in every cron-run agent session. This is enforced in `/usr/local/lib/hermes-agent/cron/scheduler.py` by `_resolve_cron_disabled_toolsets()`, which always includes `cronjob`, `messaging`, and `clarify`, and passes that denylist to `AIAgent` when `platform="cron"`.

The installed Hermes documentation states the same recursion guard: cron-run sessions cannot create new cron jobs. Therefore this is not fixed by adding `cronjob` to the job's `enabled_toolsets`; the scheduler strips it regardless. The current `poller` skill is incompatible with the current Hermes runtime because it explicitly requires a cron-run agent to call `cronjob(action="create")` to spawn `/worker`.

The current `poller-ZBS` job has an explicit toolset list containing `terminal`, `file`, `web`, `browser`, `mcp-linear-zbs`, and `mcp-github`, but not `cronjob`. That omission is real but secondary: even if added, the scheduler's hard denylist would still remove it.

### Correct architectural fixes

1. Move worker dispatch out of the cron-run LLM session and into scheduler-owned code or a dedicated external dispatcher. The poller should return a structured selection, and trusted scheduler code should create the one-shot worker job.
2. Alternatively replace the LLM poller with a script-only poller that performs selection and invokes a scheduler/dispatcher API outside the cron-agent recursion guard. Do not use `terminal(background=True)` from a cron session; that produces phantom processes and no durable worker run.
3. Update the poller skill so it no longer claims that `cronjob(action="create")` is callable from a cron-run agent. It should fail explicitly when dispatch is unavailable rather than returning a normal-looking `ok` result.
4. Add a dispatch-success invariant to poller telemetry: a selected ticket is not success unless a worker job ID is returned and appears in scheduler state.

The Claude upgrade fixed the independent npm/Bash test path in the ZBS-127 canary, but it cannot fix this scheduler recursion guard. This is now the primary blocker for automatic ZBS poller progress.
