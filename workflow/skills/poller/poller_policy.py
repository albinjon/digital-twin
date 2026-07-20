#!/usr/bin/env python3
"""Typed, deterministic, side-effect-free poller candidate selection."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

DEFAULT_COOLDOWN_MINUTES = 15


class Label(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str


class Candidate(BaseModel):
    """Normalized Linear candidate consumed by policy rules."""

    model_config = ConfigDict(extra="allow")

    identifier: str
    state: str
    labels: list[str | Label] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def accept_linear_key_alias(cls, value: Any) -> Any:
        if isinstance(value, Mapping) and "identifier" not in value and "key" in value:
            value = dict(value)
            value["identifier"] = value["key"]
        return value

    @property
    def label_names(self) -> set[str]:
        return {
            label if isinstance(label, str) else label.name
            for label in self.labels
        }


class PolicyInput(BaseModel):
    """JSON contract between the poller skill and the executable helper."""

    model_config = ConfigDict(extra="ignore")

    candidates: list[Candidate] = Field(default_factory=list)
    allowed_prefixes: list[str] = Field(default_factory=list)
    scope: str | None = None
    active_locks: dict[str, Any] = Field(default_factory=dict)
    cooldowns: dict[str, datetime] = Field(default_factory=dict)
    now: datetime | None = None
    cooldown_minutes: int = Field(default=DEFAULT_COOLDOWN_MINUTES, ge=0)


class PolicyResult(BaseModel):
    selected: Candidate | None
    scope: list[str]
    now: datetime
    skipped: dict[str, str]


@dataclass(frozen=True)
class PolicyContext:
    allowed_prefixes: frozenset[str]
    scope: frozenset[str]
    active_locks: Mapping[str, Any]
    cooldowns: Mapping[str, datetime]
    now: datetime
    cooldown_minutes: int


Rule = Callable[[Candidate, PolicyContext], str | None]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_scope(scope_arg: str | None, allowed_prefixes: Iterable[str]) -> set[str]:
    """Return the requested scope intersected with authorized prefixes."""
    allowed = {prefix.strip().upper() for prefix in allowed_prefixes if prefix.strip()}
    if not scope_arg or not scope_arg.strip():
        return allowed
    requested = {prefix.strip().upper() for prefix in scope_arg.split(",") if prefix.strip()}
    return requested & allowed


def _prefix(ticket: str) -> str:
    return ticket.split("-", 1)[0].upper() if "-" in ticket else ""


def _lock_expiry(active_locks: Mapping[str, Any], ticket: str) -> datetime | None:
    value = active_locks.get(f"{ticket}:worker", active_locks.get(ticket))
    if isinstance(value, Mapping):
        value = value.get("expires_at")
    if not value:
        return None
    if isinstance(value, datetime):
        return _utc(value)
    normalized = str(value).strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return _utc(datetime.fromisoformat(normalized))


def rule_authorized_prefix(candidate: Candidate, context: PolicyContext) -> str | None:
    prefix = _prefix(candidate.identifier)
    return None if prefix in context.allowed_prefixes else "unauthorized-prefix"


def rule_in_scope(candidate: Candidate, context: PolicyContext) -> str | None:
    prefix = _prefix(candidate.identifier)
    return None if prefix in context.scope else "outside-scope"


def rule_todo_state(candidate: Candidate, context: PolicyContext) -> str | None:
    return None if candidate.state == "Todo" else "not-todo"


def rule_no_human_label(candidate: Candidate, context: PolicyContext) -> str | None:
    return None if not any(name.casefold() == "human" for name in candidate.label_names) else "human-label"


def rule_no_active_lock(candidate: Candidate, context: PolicyContext) -> str | None:
    try:
        expiry = _lock_expiry(context.active_locks, candidate.identifier)
    except ValueError:
        return "invalid-lock-expiry"
    if expiry and expiry > context.now:
        return "active-lock"
    return None


def rule_cooldown_elapsed(candidate: Candidate, context: PolicyContext) -> str | None:
    last_exit = context.cooldowns.get(candidate.identifier)
    if last_exit and (context.now - _utc(last_exit)).total_seconds() / 60 < context.cooldown_minutes:
        return "cooldown"
    return None


DEFAULT_RULES: tuple[Rule, ...] = (
    rule_authorized_prefix,
    rule_in_scope,
    rule_todo_state,
    rule_no_human_label,
    rule_no_active_lock,
    rule_cooldown_elapsed,
)


def _first_rejection(candidate: Candidate, context: PolicyContext, rules: Sequence[Rule]) -> str | None:
    for rule in rules:
        reason = rule(candidate, context)
        if reason:
            return reason
    return None


def select_candidate(
    candidates: Sequence[Candidate | Mapping[str, Any]],
    *,
    allowed_prefixes: Sequence[str],
    scope_arg: str | None = None,
    active_locks: Mapping[str, Any] | None = None,
    cooldowns: Mapping[str, Any] | None = None,
    now: datetime | str | None = None,
    cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
    rules: Sequence[Rule] = DEFAULT_RULES,
) -> PolicyResult:
    """Validate, filter, and deterministically select at most one candidate."""
    payload = PolicyInput(
        candidates=candidates,
        allowed_prefixes=list(allowed_prefixes),
        scope=scope_arg,
        active_locks=dict(active_locks or {}),
        cooldowns=dict(cooldowns or {}),
        now=now,
        cooldown_minutes=cooldown_minutes,
    )
    allowed = frozenset(prefix.strip().upper() for prefix in payload.allowed_prefixes if prefix.strip())
    scope = frozenset(parse_scope(payload.scope, allowed))
    current = _utc(payload.now or datetime.now(timezone.utc))
    context = PolicyContext(allowed, scope, payload.active_locks, payload.cooldowns, current, payload.cooldown_minutes)

    eligible: list[Candidate] = []
    skipped: dict[str, str] = {}
    for candidate in payload.candidates:
        reason = _first_rejection(candidate, context, rules)
        if reason:
            skipped[candidate.identifier or "<missing>"] = reason
        else:
            eligible.append(candidate)

    eligible.sort(key=lambda candidate: (-candidate.created_at.timestamp(), candidate.identifier))
    return PolicyResult(selected=eligible[0] if eligible else None, scope=sorted(scope), now=current, skipped=skipped)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="JSON policy input document")
    args = parser.parse_args()
    try:
        payload = PolicyInput.model_validate_json(args.input.read_text(encoding="utf-8"))
        result = select_candidate(
            payload.candidates,
            allowed_prefixes=payload.allowed_prefixes,
            scope_arg=payload.scope,
            active_locks=payload.active_locks,
            cooldowns=payload.cooldowns,
            now=payload.now,
            cooldown_minutes=payload.cooldown_minutes,
        )
    except (OSError, ValidationError, ValueError) as error:
        parser.error(f"invalid policy input: {error}")
    print(result.model_dump_json(indent=None, by_alias=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
