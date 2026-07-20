#!/usr/bin/env python3
"""CLI for the PR review ledger in worker-state.db."""
from __future__ import annotations

import argparse
import json

from reviews import (
    get_review_target,
    list_review_candidates,
    list_unresolved_findings,
    record_review,
    replace_review_findings,
    review_needed,
    upsert_review_target,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help="override SQLite path")
    sub = parser.add_subparsers(dest="command", required=True)

    request = sub.add_parser("request")
    request.add_argument("--ticket", required=True)
    request.add_argument("--repo", required=True)
    request.add_argument("--pr-number", required=True, type=int)
    request.add_argument("--sha")
    request.add_argument("--status", default="requested")

    needs = sub.add_parser("needs-review")
    needs.add_argument("--repo", required=True)
    needs.add_argument("--pr-number", required=True, type=int)
    needs.add_argument("--sha", required=True)

    record = sub.add_parser("record")
    record.add_argument("--repo", required=True)
    record.add_argument("--pr-number", required=True, type=int)
    record.add_argument("--sha", required=True)
    record.add_argument("--status", required=True, choices=["approved", "changes_requested", "commented"])
    record.add_argument("--blocking", type=int, default=0)
    record.add_argument("--non-blocking", type=int, default=0)
    record.add_argument("--unresolved", type=int, default=0)
    record.add_argument("--review-id")
    record.add_argument("--payload-url")

    show = sub.add_parser("show")
    show.add_argument("--repo", required=True)
    show.add_argument("--pr-number", required=True, type=int)

    queue = sub.add_parser("queue")
    queue.add_argument("--limit", type=int, default=50)

    findings = sub.add_parser("findings")
    findings.add_argument("--target-id", required=True, type=int)
    findings.add_argument("--findings-json", required=True, help="JSON array of finding objects")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "request":
        target_id = upsert_review_target(ticket=args.ticket, repo=args.repo, pr_number=args.pr_number, current_sha=args.sha, review_status=args.status, path=args.db)
        print(json.dumps({"id": target_id}, sort_keys=True))
    elif args.command == "needs-review":
        print(json.dumps({"needs_review": review_needed(args.repo, args.pr_number, args.sha, path=args.db)}))
    elif args.command == "record":
        record_review(repo=args.repo, pr_number=args.pr_number, reviewed_sha=args.sha, status=args.status, blocking_findings=args.blocking, non_blocking_findings=args.non_blocking, unresolved_findings=args.unresolved, github_review_id=args.review_id, payload_url=args.payload_url, path=args.db)
        print(json.dumps({"recorded": True}))
    elif args.command == "queue":
        print(json.dumps(list_review_candidates(limit=args.limit, path=args.db), sort_keys=True))
    elif args.command == "findings":
        replace_review_findings(args.target_id, json.loads(args.findings_json), path=args.db)
        print(json.dumps({"findings": list_unresolved_findings(args.target_id, path=args.db)}, sort_keys=True))
    else:
        print(json.dumps(get_review_target(args.repo, args.pr_number, path=args.db), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
