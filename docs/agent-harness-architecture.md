# Agent harness architecture and implementation guide

Status: proposed  
Date: 2026-07-30  
Revision: 2026-07-30 (Hermes-preserving revision)  
Scope: this repository and the Linear → code → pull request workflow it describes

> **Revision note:** the original version of this document proposed making
> Hermes an optional entry point and moving webhook ingress, scheduling, and
> Linear/GitHub mutation into a new application. That is no longer the plan.
> Hermes stays as the agent orchestrator, cron scheduler, MCP gateway, and
> operator interface — it is good at those jobs and replacing them was more
> migration risk than the reliability problem warranted. What changes is that
> a deterministic Python/DBOS kernel now owns durable execution, validation,
> local git operations, recovery, and audit state underneath Hermes, instead
> of that logic living in prose inside `workflow/skills/worker/SKILL.md`.
> Sections below describing webhook ingress, GitHub App/Linear GraphQL
> adapters, and “Hermes optional” framing are superseded by the control-flow
> in this note and should be read as historical exploration, not the current
> design. The locked decisions immediately below are canonical.

## Locked decisions (canonical)

- DBOS with PostgreSQL in production; SQLite only for local development.
- A persistent Python worker process, managed by systemd in production.
- Hermes remains the scheduler (cron), MCP gateway, and operator interface —
  not replaced by webhook ingress or a competing scheduler.
- The DBOS kernel drives Hermes through two channels: Hermes's `/v1/runs` API
  (for model reasoning/decisions/review) and a small local MCP control server
  registered with Hermes (`select_and_enqueue`, `enqueue_ticket`,
  `get_run_status`, `resume_ticket`, `cancel_ticket`, `reconcile_ticket`).
- Linear/GitHub mutations continue to go through Hermes MCP, gated by two
  narrow Hermes profiles (`digital-twin-context` read-only,
  `digital-twin-effect` write-narrow) — not a new direct GraphQL/REST adapter.
- The Python kernel performs inspected git commits and pushes directly
  (not through Hermes/Claude); Hermes still creates/updates the PR and links
  it to Linear.
- The full lifecycle — refinement, routing, implementation, tests, review,
  fixes, and handoff — lives in the DBOS-driven state machine.
- Only typed workflow comments may be published; no generic `post_comment`.
- `Human` is the sole pause/handoff label; `Intervention` (used by the legacy
  `agents/*.md` prompts) is retired — those files are marked legacy in place.
- First production canary: one ZBS ticket, concurrency one throughout.
- Lane priority: `Review Fixes` → `In Progress` verification → `Todo` →
  `Backlog`, oldest eligible ticket first within each lane.
- No merge, force-push, default-branch write, arbitrary comment text, or
  runtime dependency installation, ever.

## Superseded executive decision (kept for context)

The text below was the original framing before the revision above. Build a
small Python control-plane application and make Hermes an optional
entry point, not the workflow runtime.

The recommended stack is:

- **DBOS** for durable workflows, queues, schedules, retries, recovery, and
  workflow idempotency.
- **Pydantic models** for every boundary: configuration, events, decisions,
  effects, and backend results.
- **Direct Linear and GitHub adapters** for control-plane reads and writes.
  MCP remains useful for exploratory agent tools, but it should not be the only
  way the application performs critical state transitions.
- A narrow **`DecisionEngine` port** for planning/routing and a separate
  **`CodingBackend` port** for repository work.
- **Claude Code CLI as the first coding backend**, because the existing setup
  and OAuth authentication already use it successfully. The adapter can later
  be replaced by Claude Agent SDK, Codex, OpenHands, or another backend without
  changing ticket workflow semantics.
- **Git worktrees behind a `Workspace` port** initially. Add a Docker-backed
  workspace when untrusted repositories, broader shell access, or concurrent
  workers make process isolation necessary.
- **OpenTelemetry** for traces and metrics, with a local console/JSON exporter
  first and a hosted backend only when useful.

This is intentionally not “one framework does everything.” Durability,
business policy, model reasoning, code execution, external APIs, and workspace
isolation change for different reasons. They should meet at typed boundaries.

## What this system is

Conceptually, the system has five layers:

```text
events       durable workflow       judgment          execution       effects
Linear  ──▶  TicketWorkflow  ──▶  DecisionEngine  ──▶  CodingBackend  ──▶ GitHub
GitHub       DBOS + policy          typed decision     Workspace          Linear
schedule     state + retries        no side effects    tests/gates         git
```

The durable workflow owns the lifecycle. Models advise or edit code; they do
not own scheduling, retries, authorization, locks, or external state.

The core rule is:

> A model may propose an effect. Deterministic code authorizes, executes,
> records, and reconciles that effect.

## Repository assessment

### What is already worth keeping

The repository has good pieces that should survive the migration:

- `SOUL.md` contains clear operating values and irreversible-action limits.
- `workflow/teams.md` establishes an explicit team/repository allowlist.
- `poller_policy.py` is deterministic and side-effect-free.
- The worker-state code has owner-token locks, WAL mode, atomic transactions,
  cooldowns, run history, and review metadata.
- `action_payload.py` rejects malformed action shapes rather than guessing.
- `normalize_reasoner_result.py` treats model envelopes as untrusted input.
- `prepare_worktree.py` and `changeset_gate.py` establish useful workspace and
  semantic-review boundaries.
- Recovery patches and “do not destroy useful edits” are the right operational
  posture.
- The investigation documents distinguish semantic rejection, runtime failure,
  provider failure, and scheduler failure instead of collapsing them together.

Those are the beginnings of a control plane. The migration should promote them
from scripts embedded in a skill directory into normal application modules.

### The main structural problem

There is no executable worker application.

The actual orchestration loop, action dispatch, Linear/GitHub reads, and most
side effects exist as instructions in `workflow/skills/worker/SKILL.md`.
Hermes is expected to interpret that prose correctly on every run. The Python
files implement fragments around the loop, but no checked-in process imports
them and owns a ticket from start to finish.

This causes most of the current failure modes:

- scheduler behavior depends on which tools a cron-session model happens to
  receive;
- “spawn and later resume” is incompatible with one-shot agent sessions;
- external mutations are mediated through prose and MCP calls rather than an
  idempotent client;
- the prompt, helper scripts, and older agent documents can drift separately;
- a process crash can happen before a final run record is created;
- provider-specific CLI flags are mixed into workflow policy;
- capability discovery is described, but not represented as runtime state.

The Hermes cron recursion guard exposed this design issue; it did not create it.

### Concrete drift and reliability findings

1. `workflow/delegation-contract.md` says Hermes trusts subprocess output after
   JSON parsing, while the newer worker skill requires runtime action
   validation. There are now two contracts.
2. `workflow/automation-playbook.md` describes a model-driven poller spawning a
   worker, while the poller skill has since added a CLI dispatcher workaround.
3. The old files under `agents/` still use the retired `Intervention` state and
   describe a different event-driven lifecycle.
4. `install-avatar.sh` contains absolute paths to a previous workspace and
   references source files that no longer exist in this repository.
5. `workflow/install.sh` uses symlinks into two agent homes as its deployment
   mechanism. That is convenient for local editing but not a versioned,
   rollback-safe application deployment.
6. Team configuration is a Markdown table. It is readable, but deterministic
   code cannot safely treat it as its primary configuration without a parser
   and schema.
7. `changeset_gate.py` invokes Claude directly, so changing the review provider
   requires editing git/workspace code.
8. The SQLite `runs` row is created on finalization, not at run start. A crash
   can therefore leave a lock or partial external effect without a durable run
   journal.
9. The current checkout has no `pyproject.toml`, dependency lock, CI workflow,
   type-checking configuration, or application entry point.
10. ~~`make verify` currently runs 37 worker tests and stops with one
    failure...~~ **Fixed 2026-07-30**: the test compared the raw `repo` path
    against the resolved path the implementation uses; the test now resolves
    it too (`workflow/skills/worker/tests/test_action_payload.py`). All 37
    worker/poller/runner tests pass via `make test` on macOS. `make verify`
    still fails on this machine only because `~/.hermes` is not installed
    here (see finding 11) — that is an environment gap, not a code defect.
11. Hermes is not installed on the machine used for this review (a macOS dev
    checkout, not the production host), so live cron, gateway, and MCP state
    from the Linux host could not be re-verified in this session. The
    live-state claims in the existing investigation documents and in
    `docs/plans/2026-07-30-cron-worker-reliability.md` are historical
    evidence, not findings freshly reproduced here. Re-verifying
    `/v1/capabilities`, profile/toolset configuration, cron job state, and
    lock state against the real host is a prerequisite of Phase 2 onward —
    see `docs/plans/2026-07-30-host-execution-plan.md`.
12. The `agents/{router,fixer,implement,refine,review}.md` prompts and
    `install-avatar.sh` are now marked with an explicit legacy banner in the
    files themselves (not just described here), so a reader opening them
    directly sees they are non-canonical and describe the retired
    `Intervention` lifecycle.

### Policy needs to become data

`SOUL.md` says never to send a human-facing message, while the worker workflow
posts issue and PR comments and opens non-draft pull requests. Both can be
reasonable in different operating modes, but a prompt hierarchy is the wrong
place to resolve the conflict.

Represent permissions explicitly:

```yaml
policy:
  open_pull_request: true
  push_agent_branch: true
  write_issue_status: true
  write_issue_comment: false
  write_pull_request_comment: false
  resolve_review_thread: false
  merge_pull_request: false
  force_push: false
  modify_default_branch: false
```

Every effect handler checks this policy. A prompt may be stricter, but it can
never grant a permission that the application policy denies.

## Target architecture

### 1. Ingress

Ingress receives and verifies events, acknowledges quickly, and starts or
signals a durable workflow.

Sources:

- Linear issue and comment webhooks;
- GitHub App pull request, review, and check webhooks;
- a scheduled reconciliation workflow;
- a small admin CLI for manual `start`, `resume`, `cancel`, and `inspect`.

Prefer webhooks over repeated model-driven polling. Linear signs webhook
payloads and supplies a delivery ID; GitHub Apps provide scoped permissions and
webhooks. Store the delivery ID and use it in the workflow ID so redelivery is
safe.

The scheduled reconciler remains important. Webhooks are triggers, not a source
of truth: periodically query active workflows and external state to repair a
missed event.

### 2. Durable workflow

Use one long-lived `TicketWorkflow` per ticket:

```text
workflow id: ticket:{workspace_id}:{ticket_key}
```

DBOS is the recommended runtime because it runs as a Python library, checkpoints
workflow steps in SQLite or PostgreSQL, supports queues and cron schedules, and
resumes after interruption. Use SQLite only for local development. Use
PostgreSQL in production.

The workflow:

1. Loads current ticket, PR, check, and capability state.
2. Applies deterministic termination and authorization rules.
3. Requests one typed decision.
4. Validates the decision.
5. Executes one idempotent effect step.
6. Records the result.
7. Repeats, sleeps, or waits for an external event.

Do not reproduce the current “40 actions in one ephemeral session” model.
Bounded loops are still useful, but a durable workflow can yield between
actions and resume on a webhook, timer, or human signal.

DBOS gives durable execution, not magically exactly-once third-party APIs.
Linear and GitHub effects still need idempotency and reconciliation:

- use deterministic branch names and workflow IDs;
- include a stable operation marker in created artifacts where appropriate;
- read before creating a PR, label, comment, or status transition;
- store an effect receipt with `pending`, `applied`, or `reconciled` state;
- after an ambiguous timeout, query the remote system before retrying.

### 3. Domain policy and state machine

This layer is plain Python. It imports Pydantic, but not DBOS, HTTP clients,
model SDKs, or subprocess code.

It owns:

- allowed team and repository mappings;
- ticket lifecycle states;
- effect permissions;
- transition rules;
- retry and repair budgets;
- handoff reasons;
- capability requirements;
- typed decisions and results.

Use a discriminated union instead of `{kind: string, args: object}`:

```python
class Implement(BaseModel):
    kind: Literal["implement"]
    task_spec: str
    branch_name: str


class RunTests(BaseModel):
    kind: Literal["run_tests"]


class WaitForHuman(BaseModel):
    kind: Literal["wait_for_human"]
    reason: str
    requested_input: str


Decision = Annotated[
    Implement | RunTests | WaitForHuman | Complete,
    Field(discriminator="kind"),
]
```

Prefer narrow domain actions. A generic `post_comment(body: str)` gives the
model an unnecessarily broad communication tool. Use effects such as
`PublishTestResult` or `RequestClarification`, each with policy and formatting
owned by code.

### 4. Decision engine

Define one application-facing protocol:

```python
class DecisionEngine(Protocol):
    async def decide(self, context: DecisionContext) -> Decision: ...


class Reviewer(Protocol):
    async def review(self, context: ReviewContext) -> ReviewVerdict: ...
```

Initial implementation:

- `ClaudeCliDecisionEngine`, using the existing structured-output invocation.

Optional later implementation:

- `PydanticAIDecisionEngine`, for provider-neutral model selection, typed
  output, instrumentation, and model/API experimentation.

The decision engine never receives mutation tools. It gets a bounded snapshot
and returns a value. Deterministic code decides what state to fetch and which
effect to execute.

Keep review separate from planning. A review result is evidence consumed by the
workflow, not an action with permission to commit or push.

### 5. Coding backend

Define a backend around a complete coding task, not around vendor-specific
messages:

```python
class CodingBackend(Protocol):
    async def implement(self, request: CodingRequest) -> CodingResult: ...
    async def fix(self, request: FixRequest) -> CodingResult: ...
    async def test(self, request: TestRequest) -> TestResult: ...
```

`CodingResult` includes:

- backend and model identity;
- workspace ID and base SHA;
- changed paths;
- summary;
- commands attempted;
- test results;
- usage/cost when available;
- terminal reason;
- raw-result artifact reference.

Do not let the backend commit, push, open a PR, update Linear, or remove the
workspace. The control plane owns those effects.

Implement `ClaudeCliBackend` first. It is already exercised by the existing
workflow and works with the available Claude OAuth credentials. Feed large
payloads over stdin, keep arguments in an argv list, capture stdout/stderr, and
persist the raw envelope as an artifact.

The Claude Agent SDK is a sensible second backend when API authentication is
available. It exposes Claude Code’s file, shell, session, hook, permission, MCP,
and subagent facilities as a Python/TypeScript library. It is not a transparent
replacement for the current OAuth CLI usage: Anthropic’s documentation says
third-party Agent SDK applications should use API-key authentication rather
than offering `claude.ai` login.

### 6. Workspace

```python
class Workspace(Protocol):
    async def create(self, spec: WorkspaceSpec) -> WorkspaceHandle: ...
    async def snapshot(self, handle: WorkspaceHandle) -> ChangeSet: ...
    async def preserve(self, handle: WorkspaceHandle) -> ArtifactRef: ...
    async def destroy(self, handle: WorkspaceHandle) -> None: ...
```

Implementations:

- `GitWorktreeWorkspace`: first implementation, fast and understandable;
- `DockerWorkspace`: production isolation when required;
- `OpenHandsWorkspace`: optional if remote/sandboxed agent execution becomes a
  product requirement.

Creating a worktree and executing an agent are separate steps. Cleanup happens
only after a clean handoff or after a recovery artifact has been verified.

The deterministic changeset gate should:

1. verify branch and base SHA;
2. inventory all modified, staged, and untracked paths;
3. reject writes outside the workspace and protected paths;
4. run `git diff --check`;
5. run configured format/lint/type/test commands;
6. obtain an independent typed semantic review;
7. preserve a patch on any failure after edits;
8. commit only inspected paths;
9. push through the GitHub credential boundary;
10. create or update exactly one PR.

### 7. Integrations

Create typed adapters:

```python
class IssueTracker(Protocol): ...
class CodeHost(Protocol): ...
class RepoRegistry(Protocol): ...
```

Use the Linear GraphQL API and GitHub App API for control-plane operations.
Benefits over model-issued MCP mutations:

- exact request and response types;
- explicit authentication and least privilege;
- normal retry and timeout behavior;
- idempotency/reconciliation in code;
- integration tests without a model;
- no dependency on a session-specific tool inventory.

MCP is still valuable when an agent needs to explore many tools or read
context dynamically. Treat it as an agent capability, not as the durable
workflow transport.

### 8. Observability and artifacts

Create one trace per ticket workflow and one span per decision, activity,
subprocess, API call, gate, and reconciliation.

Record:

- workflow, ticket, team, repository, action, attempt, and backend;
- base and tested SHA;
- duration and terminal reason;
- token/cost usage when available;
- subprocess exit code and timeout;
- changed path count;
- test counts;
- effect receipt ID;
- recovery artifact reference.

Do not put full prompts, diffs, secrets, or raw tool output into span
attributes. Store large artifacts on disk or object storage with content hashes
and retention rules. Logs should reference them.

## Proposed source tree

```text
digital-twin/
├── pyproject.toml
├── uv.lock
├── config/
│   ├── teams.yaml
│   └── profiles/
│       ├── shadow.yaml
│       └── autonomous-pr.yaml
├── prompts/
│   ├── decide.md
│   ├── implement.md
│   ├── fix.md
│   └── review.md
├── src/digital_twin/
│   ├── app.py
│   ├── cli.py
│   ├── config.py
│   ├── domain/
│   │   ├── decisions.py
│   │   ├── effects.py
│   │   ├── policy.py
│   │   └── state.py
│   ├── workflows/
│   │   ├── ticket.py
│   │   └── reconcile.py
│   ├── activities/
│   │   ├── context.py
│   │   ├── coding.py
│   │   ├── effects.py
│   │   └── review.py
│   ├── ports/
│   │   ├── coding.py
│   │   ├── decision.py
│   │   ├── integrations.py
│   │   └── workspace.py
│   ├── adapters/
│   │   ├── claude_cli.py
│   │   ├── github_app.py
│   │   ├── linear_graphql.py
│   │   └── git_worktree.py
│   ├── ingress/
│   │   ├── api.py
│   │   ├── github_webhook.py
│   │   └── linear_webhook.py
│   └── observability.py
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   └── scenarios/
└── legacy/
    └── hermes/          # moved only after cutover; kept for rollback
```

Do not create an interface for every function. The ports above correspond to
real replacement boundaries already present in the problem: model, coding
agent, workspace, issue tracker, and code host.

## Configuration

Move machine-readable data out of Markdown:

```yaml
teams:
  ZBS:
    linear_team_id: "..."
    github_repository: "Zenbuddhistiska-Samfundet/web"
    local_repository: "/srv/repos/zbs-web"
    profile: autonomous-pr

backends:
  decision: claude-cli
  coding: claude-cli
  review: claude-cli

limits:
  worker_concurrency: 1
  repo_concurrency: 1
  decision_repairs: 1
  semantic_repairs: 2
  coder_timeout_seconds: 3600
  tester_timeout_seconds: 1800
```

Validate this with `pydantic-settings`. Keep secrets exclusively in environment
variables or a secret store. Generate `workflow/teams.md` from the YAML if a
human-readable registry is still useful; never maintain both manually.

Profiles contain effect permissions and limits. Backend selection is
configuration. Prompt versions and application version are recorded on every
run.

## Tool choices

### Recommended now

| Tool | Role | Why |
| --- | --- | --- |
| DBOS | Durable workflow runtime | Small Python deployment; durable steps, queues, schedules, recovery, and workflow IDs; SQLite locally and PostgreSQL in production |
| Pydantic | Boundary contracts | Already present; discriminated unions replace hand-maintained action validators |
| Claude Code CLI | First coding backend | Existing workflow and OAuth setup already use it; easy to contain behind argv/stdin adapter |
| Linear GraphQL API | Ticket control plane | Deterministic reads/writes and webhook-driven triggers |
| GitHub App API | Repository control plane | Least-privilege installation tokens, webhooks, explicit permissions |
| Git worktrees | First workspace | Low migration cost and existing recovery/gate code |
| OpenTelemetry | Observability | Vendor-neutral traces across workflow, HTTP, model, and subprocess boundaries |

### Worth evaluating later

| Tool | Use it when | Do not adopt it merely because |
| --- | --- | --- |
| Claude Agent SDK | You want Claude Code’s loop, tools, sessions, hooks, and permissions in-process and have API-key auth | It shares a vendor with the current CLI |
| Pydantic AI | You want provider-neutral structured decision/review agents and typed instrumentation | The coding backend also needs to use it |
| Pydantic AI Harness | A specific capability such as filesystem, shell, repo context, persistence, or skills beats the local implementation | It is currently a separate 0.x package with intentionally faster-breaking releases |
| OpenHands SDK | You need a composable coding-agent SDK with local/Docker/remote workspaces and agent-server deployment | You only need one local coding worker |
| OpenAI Agents SDK | OpenAI models, built-in tracing, guardrails, MCP, sessions, or sandbox agents are a strong fit for a backend | It should own ticket durability or business policy |
| Temporal | You outgrow one application/database, need a mature separate workflow service, multi-region durability, or an existing Temporal platform | “More robust” automatically means “more infrastructure” |
| LangGraph | The domain truly becomes a dynamic graph with checkpointed graph state and interrupts | A ticket state machine needs a graph framework |

### Not recommended as the target

- More Hermes prompt engineering around cron dispatch.
- A second SQLite lock protocol beside the durable workflow runtime.
- Giving a single coding agent Linear, GitHub, git push, and shell mutation
  tools and relying on its prompt to preserve boundaries.
- Building a bespoke multi-agent graph before the single-worker lifecycle is
  reliable.
- Replacing Claude with another coding agent while leaving orchestration in
  prose. That changes the model but not the architecture.

## Implementation plan

### Phase 0 — establish a truthful baseline

1. Fix the macOS canonical-path test.
2. Make `make verify` complete on macOS and the Linux host.
3. Add CI for Python 3.12 on Linux and macOS.
4. Archive or clearly label the old `agents/` workflow and `install-avatar.sh`.
5. Record one current Hermes canary from the real host, including scheduler
   job, lock, run row, subprocess result, PR/ticket state, and memory.
6. Add this architecture as an ADR decision and list explicit non-goals.

Acceptance:

- clean checkout, locked dependencies, and one green verification command;
- no document claims a runtime behavior that only exists in prose;
- the live Hermes baseline and local-development baseline are separate.

### Phase 1 — extract a real application without changing behavior

1. Add `pyproject.toml`, `src/` layout, `uv.lock`, Ruff, and a type checker.
2. Move state, action, worktree, subprocess, and gate logic into importable
   packages. Leave compatibility CLI wrappers at the old paths.
3. Replace the hand-written action validator with Pydantic discriminated
   unions.
4. Add `DecisionEngine`, `CodingBackend`, and `Workspace` ports.
5. Implement Claude CLI and git-worktree adapters by moving existing behavior,
   not rewriting it.
6. Add a `digital-twin inspect <ticket>` read-only command that builds the
   complete typed context without invoking a model.

Acceptance:

- the old helper CLIs and new modules pass the same contract tests;
- provider flags occur only in `adapters/claude_cli.py`;
- git subprocess calls occur only in workspace/repository adapters;
- domain modules have no subprocess, HTTP, MCP, or DBOS imports.

### Phase 2 — add durable execution in shadow mode

1. Add DBOS with SQLite for development.
2. Implement `TicketWorkflow` and effect receipts.
3. Start the run journal before the first external mutation.
4. Convert cooldowns to durable sleep/debounce and duplicate locks to workflow
   IDs/queue constraints.
5. Keep all external mutations disabled in the `shadow` profile.
6. Feed recorded ticket/PR fixtures through complete workflows.
7. Crash the worker process after each step boundary and verify recovery.

Acceptance:

- replay never repeats a completed model call or completed coding step;
- duplicate event delivery starts one ticket workflow;
- ambiguous external effects enter reconciliation, not blind retry;
- the workflow can stop and restart between any two actions.

### Phase 3 — deterministic integrations and events

1. Create a least-privilege GitHub App.
2. Implement GitHub API operations and verify webhook signatures.
3. Implement Linear GraphQL operations and verify Linear webhook HMAC and
   timestamp.
4. Add webhook delivery deduplication.
5. Add scheduled reconciliation for active workflows.
6. Keep the existing MCP integrations available only to explicitly configured
   read-only agent contexts.

Acceptance:

- contract tests cover exact sanitized request payloads and error responses;
- repeated webhook deliveries do not duplicate effects;
- a missed webhook is repaired by reconciliation;
- capability state is measured by adapters and passed to the decision engine.

### Phase 4 — coding lifecycle

1. Implement `implement`, `fix`, and `test` through `CodingBackend`.
2. Split worktree creation, coding, inspection, testing, review, commit, push,
   and PR creation into durable steps.
3. Make every step return a small typed result plus artifact references.
4. Add recovery-patch verification before cleanup.
5. Add repository and global concurrency limits.
6. Add a hard deny for merge, force-push, default-branch writes, and secret
   paths.

Acceptance:

- killing the process during coding preserves the workspace;
- killing it after push but before PR creation reconciles and opens one PR;
- semantic review can reject at most the configured number of repair cycles;
- tester reports the exact SHA and command;
- no backend can directly mutate Linear or GitHub.

### Phase 5 — controlled cutover

1. Deploy PostgreSQL and the application service.
2. Run one team in shadow mode beside Hermes.
3. Compare selected action, fetched state, and terminal classification for at
   least ten representative tickets.
4. Enable external effects for one repository with concurrency one.
5. Disable its Hermes poller only after the first complete canary succeeds.
6. Observe scheduled reconciliation and several real workflow resumptions.
7. Move the old Hermes workflow under `legacy/hermes/` only after rollback has
   been tested.

Acceptance:

- three consecutive end-to-end workflows finish with truthful run state,
  released workspaces, exact tested SHAs, and no duplicated remote effects;
- rollback is “stop new ingress, disable DBOS worker, re-enable Hermes job,”
  with no database edits;
- remaining teams are onboarded through configuration only.

### Phase 6 — backend experiments

Only after the control plane is reliable:

1. Add a backend conformance suite.
2. Implement one alternative backend.
3. Replay the same coding fixtures in disposable repositories.
4. Compare success, diff quality, tests, wall time, cost, intervention rate,
   and recovery behavior.
5. Change the default only with measured evidence.

The conformance suite is more important than a universal model abstraction. It
should assert what the application needs rather than trying to normalize every
vendor feature.

## Verification strategy

### Unit tests

- transition and policy tables;
- discriminated decision validation;
- team/repository authorization;
- effect permission checks;
- retry and repair budgets;
- webhook signature and replay-window logic;
- idempotency-key construction.

### Contract tests

- recorded Linear GraphQL responses;
- recorded GitHub REST/GraphQL responses and permission errors;
- Claude CLI success, malformed output, timeout, quota, and partial-edit
  envelopes;
- coding-backend conformance;
- workspace path and symlink containment on Linux and macOS.

### Scenario tests

Use local bare git remotes and fake Linear/GitHub servers:

- Todo ticket → implementation → tests → PR;
- duplicate webhook delivery;
- crash after external request but before receipt update;
- coder times out after editing files;
- semantic review repeats the same blocker;
- PR already exists;
- branch was updated by a human;
- ticket gains `Human` during a run;
- provider quota exhaustion;
- repository mapping revoked;
- process restart while waiting for human input.

### Live canary invariants

For every canary, verify independently:

- ingress delivery ID;
- workflow ID and version;
- current and terminal workflow status;
- external effect receipts;
- branch, commit, PR, and ticket state;
- exact tested SHA;
- retained or cleaned workspace;
- total cost and duration;
- no forbidden effect;
- successful scheduled reconciliation.

## Security model

- Run the worker as a dedicated OS user.
- Keep provider, Linear, and GitHub credentials out of coding workspaces.
- Prefer short-lived GitHub App installation tokens.
- Scope each GitHub App installation to selected repositories.
- Verify webhook signatures before parsing into trusted events.
- Resolve symlinks before path authorization.
- Mount or mark `.git`, `.env`, SSH keys, provider credentials, and agent
  configuration read-only where practical.
- Deny outbound network by default in a container workspace; allow dependency
  registries per repository profile when needed.
- Treat repository instructions and issue text as untrusted input. They may
  influence code changes but cannot expand application permissions.
- Store raw prompts/diffs only with explicit retention and access controls.

## Operational model

Start with:

- one application process;
- one PostgreSQL database;
- one worker queue;
- concurrency one globally;
- webhook ingress plus a five- or ten-minute reconciler;
- local artifact storage with a retention job;
- JSON logs and OTLP traces;
- a systemd service or one small container deployment.

Scale only when evidence demands it:

- per-repository queues when independent repos block each other;
- Docker workspaces when isolation is needed;
- object storage when artifacts outgrow local disk;
- Temporal when workflow-service independence or multi-region operation earns
  its infrastructure cost;
- OpenHands/managed sandboxes when remote workspace operations become a
  product rather than an internal worker detail.

## Research basis

Primary sources consulted:

- [DBOS Python workflows](https://docs.dbos.dev/python/tutorials/workflow-tutorial)
  — durable steps, workflow IDs, recovery, deterministic workflow rules, and
  guarantees.
- [DBOS workflow and schedule reference](https://docs.dbos.dev/python/reference/decorators)
  — retries, recovery limits, queues, and scheduled workflows.
- [Pydantic AI’s DBOS integration](https://pydantic.dev/docs/ai/capabilities/durable_execution/dbos/)
  — in-process DBOS architecture, SQLite/PostgreSQL support, durable model/MCP
  calls, and OpenTelemetry integration.
- [Claude Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)
  — Claude Code’s loop, tools, hooks, sessions, permissions, MCP, skills, and
  authentication constraint.
- [Pydantic AI Harness](https://pydantic.dev/docs/ai/harness/)
  — composable filesystem, shell, repo-context, persistence, memory, skill,
  subagent, and guardrail capabilities, plus its current 0.x version policy.
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
  — agents, tools, handoffs, guardrails, sessions, tracing, MCP, and sandbox
  agents.
- [OpenHands SDK architecture](https://docs.openhands.dev/sdk/arch/overview)
  — separation between core agent, tools, workspace, and agent server, with
  local and remote workspace modes.
- [Temporal documentation](https://docs.temporal.io/)
  — crash-resistant workflow execution and the heavier-duty alternative.
- [Linear webhook documentation](https://linear.app/developers/webhooks) —
  delivery IDs, retry behavior, signatures, timestamps, and supported events.
- [GitHub App permission guidance](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app)
  — least-privilege permissions, API access, webhooks, and Git access.

## Final recommendation

Do not spend the next iteration repairing Hermes until it behaves like a
workflow engine. Keep the useful Python logic and Claude coding path, put them
behind typed ports, and make a durable Python application the owner of ticket
state and effects.

The first milestone is not “replace Hermes.” It is:

> A checked-in Python process can take one recorded ticket from event to
> terminal result, survive a restart at every step boundary, and prove that it
> never duplicated or exceeded an authorized external effect.

Once that is true, changing models, coding backends, workspaces, schedulers, or
observability systems becomes a contained engineering choice instead of another
rewrite of the workflow.
