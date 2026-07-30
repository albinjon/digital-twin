# Cron Worker Reliability Implementation Plan

> **For Hermes:** Implement this plan task-by-task with fresh verification after each boundary change. Do not enable broad autonomous execution until the canary gates pass.

**Goal:** Make the poller/worker system reliably execute one authorized unit of work per tick, preserve exact failure diagnostics, and never leave Linear state, worker locks, and run history inconsistent.

**Architecture:** Keep `/root/digital-twin/workflow` as the source of truth and symlink it into Hermes. Keep Hermes responsible for scheduling, MCP connections, and runtime state. Move worker execution behind a trusted, narrowly scoped runner boundary rather than relying on arbitrary model-generated terminal commands inside a cron session. The reasoner may propose actions, but a deterministic runtime validates and applies them.

**Tech Stack:** Python 3, Hermes cron/gateway, SQLite worker state, Linear/GitHub MCP, Git worktrees, Claude coder/tester subprocesses, unittest.

---

## Current Baseline and Constraints

Observed during the full review:

- `poller-ZBS` is enabled every 40 minutes; `poller-APPAI` is paused.
- Poller selection and durable dispatch now work through `dispatch_worker.py`.
- `approvals.mode=manual` and `approvals.cron_mode=deny` block worker terminal execution in cron.
- The gateway is healthy but has resident memory around 2.6 GiB and a peak around 3.3 GiB on a 3.7 GiB host.
- ZBS Linear MCP connectivity works, but `list_diffs` still returns `auth_insufficient_scope`.
- GitHub MCP connectivity works, but some worker lookups returned `Not Found` due to malformed or incorrect lookup arguments.
- An expired `ZBS-165` worker lock remains in SQLite and is passively treated as released.
- The digital-twin workflow tests pass, but the helper scripts are not yet guaranteed to be invoked by a central worker runtime.
- Do not include the existing untracked `investigation.md` in implementation commits unless deliberately promoted to documentation.

## Non-goals

- Do not batch-dispatch tickets.
- Do not globally set Hermes approvals to `off`.
- Do not copy workflow files into `~/.hermes`; symlinks remain the source-of-truth mechanism.
- Do not edit worker SQLite state manually.
- Do not silently normalize malformed reasoner actions.
- Do not increase concurrency while memory headroom is limited.

---

## Phase 0: Freeze and establish a clean baseline

### Task 0.1: Separate diagnostic artifacts from implementation

**Files:**
- Inspect: `/root/digital-twin/investigation.md`
- Keep or move deliberately; do not include accidentally in the implementation commit.

**Verification:**

```bash
git -C /root/digital-twin status --short --branch
git -C /root/digital-twin diff --check
make test
```

**Acceptance:** The intended workflow changes are identifiable independently from diagnostic notes.

### Task 0.2: Record the live runtime baseline

Record, without mutating state:

```bash
hermes cron list
hermes cron status
hermes mcp test linear-zbs
hermes mcp test github
free -h
systemctl status hermes-gateway --no-pager
```

Record current job IDs, gateway PID, MCP connectivity, memory, and active locks. This becomes the comparison point for every canary.

---

## Phase 1: Make workflow asset resolution and trust explicit

### Task 1.1: Define one canonical workflow-root resolver

**Files:**
- Modify: `workflow/install.sh`
- Create: `workflow/lib/workflow_paths.py` or an equivalent small resolver module
- Test: `workflow/skills/worker/tests/test_workflow_paths.py`

**Objective:** Resolve `teams.md`, delegated prompts, helper scripts, and skill roots from the installed source location without hard-coded `/root` assumptions.

**Requirements:**

- Resolve paths from `Path(__file__).resolve()` or an explicit `HERMES_WORKFLOW_ROOT` override.
- Verify that resolved files exist and are regular files.
- Return a structured diagnostic naming the requested asset, searched locations, and canonical source.
- Preserve the current symlink layout.

**Acceptance:** The same resolver works when called through:

```text
/root/digital-twin/workflow/...
/root/.hermes/skills/worker/...
/root/.hermes/skills/poller/...
```

### Task 1.2: Make Hermes trust the symlink target without copying skills

**Files:**
- Inspect the installed Hermes trust-check implementation and supported configuration.
- Modify: `workflow/install.sh` or the supported Hermes trust configuration, not duplicated skill files.
- Document: `workflow/README.md` or `workflow/automation-playbook.md`.

**Objective:** Remove repetitive skill security warnings while preserving external source control.

**Acceptance:** A fresh poller and worker session loads the symlinked skill without a security warning. If Hermes does not support configuring trusted external roots, document that as a runtime limitation and implement a tested, supported fallback rather than weakening the security scanner.

### Task 1.3: Add an installation verification command

**Files:**
- Modify: `workflow/install.sh`
- Create: `workflow/scripts/verify_installation.py`
- Test: `workflow/skills/worker/tests/test_installation_verifier.py`

**Output must include:**

```json
{
  "valid": true,
  "source_root": "...",
  "links": [...],
  "missing": [],
  "mismatched": []
}
```

A mismatch must return the source and target paths and never silently repair them.

---

## Phase 2: Define and enforce the action protocol

### Task 2.1: Promote the payload validator to a shared workflow library

**Files:**
- Move/refactor: `workflow/skills/worker/scripts/action_payload.py`
- Test: `workflow/skills/worker/tests/test_action_payload.py`

**Objective:** Keep one validator implementation used by the worker runtime, CLI diagnostics, and tests.

**Required diagnostic contract:**

```json
{
  "valid": false,
  "errors": [
    {
      "path": "args.task_spec",
      "code": "required|type|enum|additional_property|invalid_json",
      "message": "...",
      "expected": "...",
      "received": "...",
      "received_type": "..."
    }
  ],
  "expected": {
    "kind": "...",
    "args": "...",
    "reason": "string"
  }
}
```

`received` may be omitted only when no value was supplied. Do not silently rename aliases or unwrap nested actions.

### Task 2.2: Generate action-specific JSON Schemas from the validator

**Files:**
- Modify: `workflow/skills/worker/scripts/action_payload.py`
- Create: `workflow/skills/worker/scripts/action_schema.py` if separation improves clarity
- Test: `workflow/skills/worker/tests/test_action_payload.py`

**Objective:** Avoid maintaining one generic `args: object` schema in the reasoner prompt while separately maintaining runtime validation.

**Acceptance:** The same definitions generate:

- `start_implementation` requiring exactly `branch_name` and `task_spec`;
- `apply_fixes` requiring exactly `task_spec`, with optional `resolve_thread_ids`;
- `request_human` requiring exactly `comment`;
- `move_state` requiring exactly `state` from the configured enum;
- all other action shapes with `additionalProperties: false`.

### Task 2.3: Add a deterministic reasoner-result normalizer

**Files:**
- Create: `workflow/skills/worker/scripts/normalize_reasoner_result.py`
- Test: `workflow/skills/worker/tests/test_reasoner_result.py`

**Objective:** Normalize the outer Claude envelope before validation.

Handle only these supported forms:

1. `structured_output` containing an object;
2. `result` containing a JSON object;
3. `result` containing one JSON object inside a single fenced block.

Reject:

- prose plus multiple JSON objects;
- nested action envelopes;
- missing cost metadata when cost is required;
- invalid JSON;
- ambiguous extraction.

Return the exact parse failure, extraction source, and expected envelope shape.

### Task 2.4: Integrate validation into the actual worker loop

**Files:**
- Modify the actual worker orchestrator/runtime implementation once located;
- Keep: `workflow/skills/worker/SKILL.md` and `delegated-decide.md` as documentation of the same contract;
- Test: runtime worker-loop tests.

**Objective:** Make validation a runtime invariant, not merely a prompt instruction.

**Behavior:**

1. Invoke the reasoner.
2. Normalize the outer envelope.
3. Validate the inner action.
4. On failure, append the complete diagnostic to `action_log`.
5. Retry once with the diagnostic and generated action-specific schema.
6. If malformed again, perform deterministic human handoff with the diagnostic.
7. Never apply a mutation before validation passes.

---

## Phase 3: Establish a trusted worker execution boundary

### Task 3.1: Define the worker runner interface

**Files:**
- Create: `workflow/runner/worker_runner.py`
- Create: `workflow/runner/contracts.py`
- Test: `workflow/runner/tests/test_worker_runner.py`

**Objective:** Separate model reasoning from local execution and state mutation.

The runner should expose typed operations:

```text
prepare_worktree
run_coder
run_tester
run_changeset_gate
cleanup_worktree
release_run
```

Each operation must:

- accept a structured input object;
- run through argv-based subprocess calls where possible;
- return `{ok, result/error, diagnostics}`;
- never delete an existing worktree defensively;
- preserve patches before cleanup;
- include command name and exit code, but redact secrets.

### Task 3.2: Replace compound Git setup with the runner

**Files:**
- Refactor: `workflow/skills/worker/scripts/prepare_worktree.py`
- Test: `workflow/skills/worker/tests/test_prepare_worktree.py`

Support two explicit modes:

```text
new branch from origin/main
existing PR branch from origin/<branch>
```

Do not overload one ambiguous mode. Use separate flags and schemas. Fetch the specific ref before creating an existing-PR worktree.

### Task 3.3: Define coder/tester subprocess invocation as files plus argv

**Files:**
- Create: `workflow/runner/subprocess_runner.py`
- Modify: `workflow/skills/worker/delegated-code.md`
- Modify: `workflow/skills/worker/delegated-test.md`
- Test: `workflow/runner/tests/test_subprocess_runner.py`

Requirements:

- Write prompts/bundles to validated temporary files.
- Feed large prompts via stdin.
- Do not use nested shell substitution.
- Do not append large prompts after `--allowedTools`.
- Capture stdout, stderr, exit code, timeout, model envelope, and cost.
- Preserve the exact subprocess result in `action_log`.
- Block synchronously using repeated waits when a background process is required.
- Never report “will resume later” from a one-shot worker.

### Task 3.4: Choose the cron approval policy deliberately

Do not change `approvals.mode` globally.

Preferred order:

1. Make all workflow-owned operations use the trusted runner and safe argv helpers.
2. Test whether the runner can complete a worker without approval gates.
3. If Claude coder/tester execution still requires cron approval, evaluate a narrowly scoped cron execution mode.
4. Only then consider:

```yaml
approvals:
  cron_mode: approve
```

If `cron_mode: approve` is used, document that it is an explicit security boundary and add command allowlist tests. Do not use `approvals.mode: off`.

### Task 3.5: Add an execution capability preflight

Before acquiring a worker lock, verify:

- source assets resolve;
- repository path exists;
- runner commands are available;
- cron execution mode can run required safe commands;
- MCP tools needed for the selected action exist.

Return a structured `runtime_missing` diagnostic before mutating Linear. This prevents the current behavior where Linear receives a `Human` label but no durable worker run is recorded.

---

## Phase 4: Make worker finalization transactional and fail-safe

### Task 4.1: Acquire the lock before any external mutation

**Files:**
- Modify: worker runtime
- Test: worker lifecycle tests

The worker must acquire its owner-token lock before any Linear label/comment/state mutation. If preflight fails, no Linear mutation should happen unless a durable run record exists.

### Task 4.2: Add a run journal before action application

Persist a run-start record containing:

```text
run_id
ticket
role
owner_token
started_at
workflow_version
```

Every action appends a normalized action record before or atomically with the external mutation.

### Task 4.3: Guarantee release on every exit path

Use a single finalization path for:

- stop;
- request_human;
- terminal ticket state;
- malformed payload;
- runtime missing;
- timeout;
- subprocess failure;
- unexpected exception;
- iteration cap.

Finalization must:

1. record the exit reason;
2. release the owner-token lock;
3. persist cooldown and run history;
4. preserve the diagnostic;
5. reconcile final Linear/PR state;
6. verify the lock is gone.

### Task 4.4: Recover the current stale lock safely

Inspect `ZBS-165` using the owner-token-aware helper. Do not edit SQLite manually. Determine whether the expired lock can be reclaimed by the normal helper. Record the recovery result before enabling more worker canaries.

---

## Phase 5: Fix external integration contracts

### Task 5.1: Validate GitHub lookup payloads before MCP calls

**Files:**
- Modify: worker runtime/reasoning bundle contract
- Test: integration argument validation tests

Every GitHub call must carry the expected structure:

```text
owner: string
repo: string
branch/sha/path/pull_number: action-specific required fields
```

When a lookup fails, report:

- exact tool name;
- exact sanitized payload;
- expected payload shape;
- repository mapping source;
- returned MCP error.

Do not collapse `Not Found` into a generic execution failure.

### Task 5.2: Resolve Linear diff authorization

Confirm whether `linear-zbs` has permission to access diffs/reviews. If not:

- treat review capability as unavailable in preflight;
- do not repeatedly retry `list_diffs`;
- route review-required tickets to Human with the exact 403/request ID;
- document the required OAuth scope/workspace authorization.

### Task 5.3: Add capability-aware action selection

The reasoner bundle must state whether the current run can:

```text
read_ticket
read_pr
read_diff
write_linear
write_github
run_local_commands
```

The reasoner must not select `run_tests`, `apply_fixes`, or PR review actions when the required capability is unavailable.

---

## Phase 6: Resource safety and operational controls

### Task 6.1: Keep single-unit dispatch as a hard invariant

Reject poller configurations that attempt batch dispatch. Keep one selected ticket per tick and one active worker per ticket.

### Task 6.2: Add resource telemetry

Record per worker:

- peak process RSS if available;
- duration;
- subprocess count;
- MCP call count;
- whether swap was used;
- exit reason.

Add a watchdog threshold for low available memory, but make it alert-only first.

### Task 6.3: Define concurrency limits

Do not raise concurrency above one worker per poller until the gateway remains below a tested memory threshold during a complete implementation canary.

### Task 6.4: Refresh the gateway service unit

During a controlled maintenance window, run:

```bash
sudo hermes gateway restart --system
```

Then verify:

```bash
hermes cron status
systemctl status hermes-gateway --no-pager
journalctl -u hermes-gateway --since '5 minutes ago' --no-pager
```

Do not combine this restart with workflow changes or a worker canary.

---

## Phase 7: Verification ladder

### Gate 1: Pure workflow tests

```bash
cd /root/digital-twin
make test
make compile
git diff --check
```

Expected: all tests pass, no syntax errors, no whitespace errors.

### Gate 2: Installation and symlink verification

```bash
bash workflow/install.sh --dry-run
python3 workflow/scripts/verify_installation.py
```

Expected: all links resolve to `/root/digital-twin/workflow` and no assets are missing.

### Gate 3: MCP capability tests

```bash
hermes mcp test linear-zbs
hermes mcp test github
```

Expected: connected tools are listed. Diff authorization must be explicitly recorded as available or unavailable.

### Gate 4: Dispatcher-only canary

Use a synthetic valid ticket key only if the scheduler supports a no-op validation mode. Otherwise use one real eligible ticket after verifying its Linear state, Human label, cooldown, and lock status.

Verify:

- dispatcher returns `ok: true` and a job ID;
- job appears in scheduler state;
- no duplicate job is created;
- one-shot job disappears only after execution.

### Gate 5: Worker preflight canary

Use a real eligible ticket and verify:

- lock acquired;
- all workflow assets resolve;
- repository mapping resolves;
- no Linear mutation occurs before run journaling;
- capability failures produce structured diagnostics;
- lock release and run history are present.

### Gate 6: Worktree-only canary

Run `prepare_worktree` against a disposable local repository. Verify:

- fetch and add use separate argv calls;
- existing paths are refused;
- no approval prompt occurs;
- cleanup preserves changes.

### Gate 7: Coder/tester canary

Use a small controlled ticket or an existing PR head. Verify:

- exact subprocess SHA;
- exact test command;
- structured result envelope;
- no orphaned subprocess;
- no stranded worktree;
- action cost is recorded.

### Gate 8: End-to-end implementation canary

Only after Gates 1–7 pass:

1. select one real Todo ticket;
2. dispatch one worker;
3. let it run without manual intervention;
4. verify the PR/Linear state;
5. verify worker SQLite finalization;
6. verify no pending approval occurred;
7. inspect memory and journal output.

Do not re-enable broader polling until this gate passes.

---

## Phase 8: Commit and rollout strategy

### Commit boundaries

Use separate commits:

1. `docs: record cron worker reliability plan`
2. `feat: centralize workflow path and installation verification`
3. `feat: enforce structured reasoner action contracts`
4. `feat: add trusted worker execution boundary`
5. `fix: make worker finalization fail-safe`
6. `fix: harden GitHub and Linear capability handling`
7. `chore: add resource telemetry and canary checks`

Do not commit runtime databases, cron outputs, session transcripts, credentials, or `investigation.md` unless explicitly intended.

### Rollout order

1. Keep APPAI paused.
2. Keep ZBS poller on one ticket per 40-minute tick.
3. Deploy source changes through the symlink installer.
4. Restart Hermes only during a controlled window if required.
5. Run the gates in order.
6. Run one ZBS end-to-end canary.
7. Observe at least three scheduled ticks before changing cadence.
8. Only then consider enabling another team.

## Final success criteria

The system is green only when all of these are true:

- no repeated skill trust warnings;
- poller dispatches exactly one durable worker job per selected ticket;
- worker preflight fails without Linear side effects when runtime capabilities are missing;
- every reasoner payload is validated before mutation;
- malformed payloads return exact correction diagnostics and expected structure;
- worktree/coder/tester operations run without interactive approval deadlocks;
- every worker exit has a durable run record, released lock, cooldown, and truthful exit reason;
- GitHub/Linear lookup errors include exact sanitized payload diagnostics;
- diff/review authorization is known and handled explicitly;
- gateway memory remains below the tested safety threshold;
- three consecutive scheduled canaries complete without scheduler, approval, lock, or finalization anomalies.
