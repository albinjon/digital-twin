#!/usr/bin/env python3
"""Normalize Claude reasoner envelopes before worker action validation."""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

FENCE_RE = re.compile(r"^```(?:json)?\s*\n(?P<body>.*?)\n```\s*$", re.DOTALL | re.IGNORECASE)
EXPECTED = {
    "outer": {"structured_output": "object (preferred)", "result": "JSON object or one fenced JSON object", "total_cost_usd": "number (optional)"},
    "action": {"kind": "string", "args": "object", "reason": "string"},
}


def _parse_json(value: Any, path: str) -> tuple[Any | None, dict[str, Any] | None]:
    if isinstance(value, dict):
        return value, None
    if not isinstance(value, str):
        return None, {"path": path, "code": "type", "message": "Expected an object or JSON string.", "expected": "object or JSON string", "received_type": type(value).__name__}
    text = value.strip()
    try:
        return json.loads(text), None
    except json.JSONDecodeError as direct_error:
        match = FENCE_RE.fullmatch(text)
        if not match:
            return None, {"path": path, "code": "invalid_json", "message": f"Expected direct JSON or one fenced JSON object: {direct_error}", "expected": EXPECTED["outer"]["result"]}
        try:
            return json.loads(match.group("body")), None
        except json.JSONDecodeError as fence_error:
            return None, {"path": path, "code": "invalid_json", "message": f"Fenced result is not valid JSON: {fence_error}", "expected": EXPECTED["action"]}


def normalize_envelope(envelope: Any) -> dict[str, Any]:
    if not isinstance(envelope, dict):
        return {"valid": False, "action": None, "errors": [{"path": "$", "code": "type", "message": "Reasoner envelope must be a JSON object.", "expected": EXPECTED["outer"], "received_type": type(envelope).__name__}], "expected": EXPECTED}
    errors: list[dict[str, Any]] = []
    candidate = None
    source = None
    if "structured_output" in envelope and envelope["structured_output"] is not None:
        candidate, error = _parse_json(envelope["structured_output"], "structured_output")
        source = "structured_output"
        if error:
            errors.append(error)
    elif "result" in envelope:
        candidate, error = _parse_json(envelope["result"], "result")
        source = "result"
        if error:
            errors.append(error)
    else:
        errors.append({"path": "$", "code": "required", "message": "Reasoner envelope must contain structured_output or result.", "expected": EXPECTED["outer"]})
    if candidate is not None and not isinstance(candidate, dict):
        errors.append({"path": source or "$", "code": "type", "message": "Normalized reasoner result must be one action object.", "expected": EXPECTED["action"], "received_type": type(candidate).__name__})
        candidate = None
    if candidate is not None:
        unknown = sorted(set(candidate) - {"kind", "args", "reason"})
        if unknown:
            errors.append({"path": "$", "code": "additional_property", "message": f"Remove unexpected action fields: {', '.join(unknown)}.", "expected": ["kind", "args", "reason"], "received": unknown})
    result = {"valid": not errors, "action": candidate, "source": source, "errors": errors, "expected": EXPECTED}
    if "total_cost_usd" in envelope:
        result["total_cost_usd"] = envelope["total_cost_usd"]
    if "subtype" in envelope:
        result["subtype"] = envelope["subtype"]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", nargs="?", help="Envelope JSON file; omit to read stdin")
    args = parser.parse_args()
    try:
        raw = open(args.payload, encoding="utf-8").read() if args.payload else sys.stdin.read()
        envelope = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        result = {"valid": False, "action": None, "errors": [{"path": "$", "code": "invalid_json", "message": f"Envelope is not valid JSON: {exc}", "expected": EXPECTED["outer"]}], "expected": EXPECTED}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2
    result = normalize_envelope(envelope)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
