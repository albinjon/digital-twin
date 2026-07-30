"""Read-only Phase 1 CLI: inspect, validate-config, capabilities, doctor.

No mutation happens through this CLI. It exists to prove the kernel can build
typed state and validated configuration without invoking a model or touching
Linear/GitHub/git.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from digital_twin.config import DEFAULT_CONFIG_PATH, DEFAULT_TEAMS_MD_PATH, load_teams, render_teams_md
from digital_twin.domain.contracts import Capabilities


def cmd_validate_config(args: argparse.Namespace) -> int:
    try:
        teams = load_teams(Path(args.config))
    except Exception as exc:  # noqa: BLE001 - user-facing CLI error
        print(f"invalid config: {exc}", file=sys.stderr)
        return 1
    print(f"ok: {len(teams.root)} team(s) configured: {', '.join(teams.root)}")
    return 0


def cmd_generate_teams_doc(args: argparse.Namespace) -> int:
    teams = load_teams(Path(args.config))
    Path(args.out).write_text(render_teams_md(teams))
    print(f"wrote {args.out}")
    return 0


def cmd_capabilities(args: argparse.Namespace) -> int:
    caps = Capabilities(
        linear_read=False,
        linear_write=False,
        github_read=False,
        github_write=False,
        local_repository=Path(".git").exists(),
        coding_backend=shutil.which("claude") is not None,
        test_runtime=True,
        hermes_runs_api=False,
    )
    print(caps.model_dump_json(indent=2))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    teams = load_teams(Path(args.config))
    prefix = args.ticket_key.split("-")[0]
    team = teams.team_for_prefix(prefix)
    if team is None:
        print(f"ticket_key={args.ticket_key} authorized=false (unknown prefix {prefix!r})")
        return 1
    print(f"ticket_key={args.ticket_key} authorized=true team={team.name!r} repo={team.github_repository!r}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    checks = {
        "config/teams.yaml readable": DEFAULT_CONFIG_PATH.exists(),
        "git available": shutil.which("git") is not None,
        "claude CLI available": shutil.which("claude") is not None,
        "psql available": shutil.which("psql") is not None,
        "hermes CLI available": shutil.which("hermes") is not None,
    }
    ok = True
    for label, passed in checks.items():
        print(f"{'OK  ' if passed else 'MISS'}  {label}")
        ok = ok and passed
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="digital-twin")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate-config", help="Validate config/teams.yaml")
    p.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    p.set_defaults(func=cmd_validate_config)

    p = sub.add_parser("generate-teams-doc", help="Regenerate workflow/teams.md from the YAML config")
    p.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    p.add_argument("--out", default=str(DEFAULT_TEAMS_MD_PATH))
    p.set_defaults(func=cmd_generate_teams_doc)

    p = sub.add_parser("capabilities", help="Report locally-observable capabilities")
    p.set_defaults(func=cmd_capabilities)

    p = sub.add_parser("inspect", help="Build read-only authorization context for a ticket key")
    p.add_argument("ticket_key")
    p.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("doctor", help="Check local host prerequisites")
    p.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
