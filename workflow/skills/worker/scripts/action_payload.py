#!/usr/bin/env python3
"""Validate worker reasoner actions and explain malformed payloads.

This is intentionally dependency-free so cron sessions can run it without
execute_code or a project virtualenv. The validator is fail-closed and emits a
stable JSON diagnostic suitable for action_log and human handoff comments.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

STATES = {"Backlog", "Todo", "In Progress", "Review Fixes", "Done", "Duplicate", "Canceled"}
KINDS = {
    "refine_description",
    "move_state",
    "post_comment",
    "start_implementation",
    "apply_fixes",
    "run_tests",
    "post_pr_comment",
    "resolve_pr_thread",
    "request_human",
    "stop",
}

SCHEMAS: dict[str, dict[str, Any]] = {
    "refine_description": {"optional": {"description_update": "string", "labels": "array[string]", "comment": "string"}, "at_least_one": True},
    "move_state": {"required": {"state": "string"}, "optional": {"comment": "string"}, "enum": {"state": sorted(STATES)}},
    "post_comment": {"required": {"body": "string"}},
    "start_implementation": {"required": {"branch_name": "string", "task_spec": "string"}},
    "apply_fixes": {"required": {"task_spec": "string"}, "optional": {"resolve_thread_ids": "array[string]"}},
    "run_tests": {"optional": {}},
    "post_pr_comment": {"required": {"body": "string"}, "optional": {"path": "string", "line": "integer"}},
    "resolve_pr_thread": {"required": {"thread_id": "string"}, "optional": {"reply": "string"}},
    "request_human": {"required": {"comment": "string"}},
    "stop": {"required": {"reason": "string"}},
}


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str) and bool(value.strip())
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "array[string]":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return isinstance(value, dict) if expected == "object" else True


def _error(path: str, code: str, message: str, expected: Any, received: Any = None) -> dict[str, Any]:
    item = {"path": path, "code": code, "message": message, "expected": expected}
    if received is not None:
        item["received"] = received
        item["received_type"] = _type_name(received)
    return item


def validate_action(payload: Any) -> dict[str, Any]:
    expected_top = {"kind": "string enum", "args": "object", "reason": "string"}
    errors: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return {"valid": False, "errors": [_error("$", "type", "Action payload must be a JSON object.", expected_top, payload)], "expected": expected_top}

    allowed_top = {"kind", "args", "reason"}
    for key in sorted(set(payload) - allowed_top):
        errors.append(_error(key, "additional_property", f"Unexpected top-level field {key!r}; remove it.", sorted(allowed_top), payload[key]))
    for key, expected in (("kind", "string"), ("args", "object"), ("reason", "string")):
        if key not in payload:
            errors.append(_error(key, "required", f"Missing required top-level field {key!r}.", expected))
        elif not _matches(payload[key], expected):
            errors.append(_error(key, "type", f"Field {key!r} has the wrong type or is empty.", expected, payload[key]))
    kind = payload.get("kind")
    if isinstance(kind, str) and kind not in KINDS:
        errors.append(_error("kind", "enum", f"Unknown action kind {kind!r}.", sorted(KINDS), kind))

    args = payload.get("args")
    if not isinstance(args, dict):
        return {"valid": not errors, "errors": errors, "expected": expected_top}
    if not isinstance(kind, str) or kind not in SCHEMAS:
        return {"valid": not errors, "errors": errors, "expected": expected_top}

    schema = SCHEMAS[kind]
    required = schema.get("required", {})
    optional = schema.get("optional", {})
    allowed = set(required) | set(optional)
    for key in sorted(set(args) - allowed):
        errors.append(_error(f"args.{key}", "additional_property", f"Unexpected field {key!r} for action {kind!r}. Use the documented args structure; do not rename fields.", {**required, **optional}, args[key]))
    for key, expected in required.items():
        if key not in args:
            errors.append(_error(f"args.{key}", "required", f"Action {kind!r} requires args.{key}.", expected))
        elif not _matches(args[key], expected):
            errors.append(_error(f"args.{key}", "type", f"args.{key} must be a non-empty {expected}.", expected, args[key]))
    for key, expected in optional.items():
        if key in args and not _matches(args[key], expected):
            errors.append(_error(f"args.{key}", "type", f"args.{key} must have type {expected}.", expected, args[key]))
    for key, choices in schema.get("enum", {}).items():
        if key in args and args[key] not in choices:
            errors.append(_error(f"args.{key}", "enum", f"args.{key} must be one of the allowed values.", choices, args[key]))
    if schema.get("at_least_one") and not any(key in args and args[key] not in (None, "", []) for key in allowed):
        errors.append(_error("args", "at_least_one", f"Action {kind!r} requires at least one supported field.", sorted(allowed), args))

    expected = {"kind": sorted(KINDS), "args": {**required, **optional}, "reason": "string"}
    return {"valid": not errors, "errors": errors, "expected": expected}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", nargs="?", help="JSON file; omit to read JSON from stdin")
    args = parser.parse_args()
    try:
        raw = open(args.payload, encoding="utf-8").read() if args.payload else sys.stdin.read()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        result = {"valid": False, "errors": [{"path": "$", "code": "invalid_json", "message": f"Payload is not valid JSON: {exc}", "expected": "one JSON object"}]}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2
    result = validate_action(payload)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
