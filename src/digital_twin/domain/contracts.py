"""Typed boundary contracts for the deterministic kernel.

Pure domain module: Pydantic only. No DBOS, HTTP, subprocess, git, or Hermes
imports belong here — see docs/agent-harness-architecture.md Phase 1.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

Lane = Literal["Backlog", "Todo", "In Progress", "Review Fixes"]
TerminalStatus = Literal["Done", "Duplicate", "Canceled"]


class TriggerEvent(BaseModel):
    source: Literal["linear_poll", "manual", "reconcile"]
    ticket_key: str
    trigger_kind: Literal["poll", "manual_enqueue", "resume", "reconcile"]
    event_id: str
    received_at: datetime


class ArtifactRef(BaseModel):
    content_hash: str
    artifact_type: Literal["patch", "raw_result", "log", "envelope"]
    path: str
    size_bytes: int
    retain_until: datetime | None = None


class Capabilities(BaseModel):
    linear_read: bool
    linear_write: bool
    github_read: bool
    github_write: bool
    local_repository: bool
    coding_backend: bool
    test_runtime: bool
    hermes_runs_api: bool


class LifecycleContext(BaseModel):
    ticket_key: str
    lane: Lane
    generation: int
    has_human_label: bool
    pull_request_url: str | None = None
    pull_request_is_draft: bool | None = None
    head_sha: str | None = None
    tested_sha: str | None = None
    capabilities: Capabilities
    prior_decisions: int = 0


# --- Decision variants -------------------------------------------------


class RefineIssue(BaseModel):
    kind: Literal["refine_issue"] = "refine_issue"
    normalized_title: str
    classification: Literal["Feature", "Bug"]
    surface: Literal["FE", "BE"]


class MarkDuplicate(BaseModel):
    kind: Literal["mark_duplicate"] = "mark_duplicate"
    duplicate_of: str


class MoveState(BaseModel):
    kind: Literal["move_state"] = "move_state"
    target_lane: Lane | TerminalStatus


class RequestClarification(BaseModel):
    kind: Literal["request_clarification"] = "request_clarification"
    question: str


class RequestHuman(BaseModel):
    kind: Literal["request_human"] = "request_human"
    reason: Literal[
        "ambiguous_requirements",
        "conflicting_feedback",
        "runtime_missing",
        "closed_unmerged_pr",
        "ready_for_review",
    ]
    summary: str


class StartImplementation(BaseModel):
    kind: Literal["start_implementation"] = "start_implementation"
    branch_name: str
    task_spec: str


class ApplyFixes(BaseModel):
    kind: Literal["apply_fixes"] = "apply_fixes"
    finding_ids: list[str]


class RunTests(BaseModel):
    kind: Literal["run_tests"] = "run_tests"


class ReviewPullRequest(BaseModel):
    kind: Literal["review_pull_request"] = "review_pull_request"
    head_sha: str


class PublishReviewFinding(BaseModel):
    kind: Literal["publish_review_finding"] = "publish_review_finding"
    finding_id: str
    summary: str


class ResolveReviewThread(BaseModel):
    kind: Literal["resolve_review_thread"] = "resolve_review_thread"
    thread_id: str


class Complete(BaseModel):
    kind: Literal["complete"] = "complete"


class Stop(BaseModel):
    kind: Literal["stop"] = "stop"
    reason: str


Decision = Annotated[
    RefineIssue
    | MarkDuplicate
    | MoveState
    | RequestClarification
    | RequestHuman
    | StartImplementation
    | ApplyFixes
    | RunTests
    | ReviewPullRequest
    | PublishReviewFinding
    | ResolveReviewThread
    | Complete
    | Stop,
    Field(discriminator="kind"),
]


# --- Effects -------------------------------------------------------------


class Effect(BaseModel):
    effect_id: str
    ticket_key: str
    decision: Decision


class EffectResult(BaseModel):
    effect_id: str
    status: Literal["applied", "already_applied", "rejected", "ambiguous", "failed"]
    detail: str | None = None


# --- Coding / testing / review round-trips --------------------------------


class CodingRequest(BaseModel):
    mode: Literal["implement", "fix", "semantic_review"]
    ticket_key: str
    branch_name: str
    task_spec: str
    base_sha: str


class CodingResult(BaseModel):
    backend: str
    model: str
    workspace_id: str
    base_sha: str
    changed_paths: list[str]
    summary: str
    terminal_reason: str
    artifact: ArtifactRef


class TestRequest(BaseModel):
    ticket_key: str
    sha: str
    command: str


class TestResult(BaseModel):
    ticket_key: str
    sha: str
    command: str
    passed: bool
    artifact: ArtifactRef


class ReviewRequest(BaseModel):
    ticket_key: str
    pull_request_url: str
    head_sha: str


class ReviewVerdict(BaseModel):
    ticket_key: str
    head_sha: str
    findings: list[str]
    ready_for_human: bool
