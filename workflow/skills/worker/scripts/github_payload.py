#!/usr/bin/env python3
"""Validate common GitHub MCP lookup payloads before issuing calls."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

SCHEMAS = {
    "list_commits": {"required": {"owner": "string", "repo": "string"}, "optional": {"sha": "string", "page": "integer", "per_page": "integer"}},
    "get_file_contents": {"required": {"owner": "string", "repo": "string", "path": "string"}, "optional": {"branch": "string"}},
    "get_pull_request": {"required": {"owner": "string", "repo": "string", "pull_number": "integer"}, "optional": {}},
    "get_pull_request_files": {"required": {"owner": "string", "repo": "string", "pull_number": "integer"}, "optional": {}},
    "get_pull_request_comments": {"required": {"owner": "string", "repo": "string", "pull_number": "integer"}, "optional": {}},
    "list_diffs": {"required": {}, "optional": {"owner": "string", "repo": "string", "query": "string", "status": "string"}},
}


def _matches(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str) and bool(value.strip())
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool) and value > 0
    return False


def validate_github_payload(tool: str, payload: Any) -> dict[str, Any]:
    schema = SCHEMAS.get(tool)
    if schema is None:
        return {"valid": False, "errors": [{"path": "tool", "code": "unsupported", "message": f"No payload contract is registered for {tool!r}.", "expected": sorted(SCHEMAS)}]}
    if not isinstance(payload, dict):
        return {"valid": False, "errors": [{"path": "$", "code": "type", "message": "GitHub MCP payload must be an object.", "expected": "object"}], "expected": schema}
    errors = []
    allowed = set(schema["required"]) | set(schema["optional"])
    for key in sorted(set(payload) - allowed):
        errors.append({"path": key, "code": "additional_property", "message": f"Unexpected GitHub payload field {key!r}.", "expected": schema})
    for key, expected in schema["required"].items():
        if key not in payload:
            errors.append({"path": key, "code": "required", "message": f"GitHub tool {tool!r} requires {key!r}.", "expected": expected})
        elif not _matches(payload[key], expected):
            errors.append({"path": key, "code": "type", "message": f"GitHub payload field {key!r} has the wrong type or is empty.", "expected": expected, "received": payload[key], "received_type": type(payload[key]).__name__})
    for key, expected in schema["optional"].items():
        if key in payload and not _matches(payload[key], expected):
            errors.append({"path": key, "code": "type", "message": f"GitHub payload field {key!r} has the wrong type.", "expected": expected, "received": payload[key], "received_type": type(payload[key]).__name__})
    return {"valid": not errors, "tool": tool, "errors": errors, "expected": schema}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tool")
    parser.add_argument("payload", nargs="?", help="JSON payload file; omit for stdin")
    args = parser.parse_args()
    try:
        raw = open(args.payload, encoding="utf-8").read() if args.payload else sys.stdin.read()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        result = {"valid": False, "errors": [{"path": "$", "code": "invalid_json", "message": str(exc), "expected": "JSON object"}]}
        print(json.dumps(result, sort_keys=True))
        return 2
    result = validate_github_payload(args.tool, payload)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
