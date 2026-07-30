"""Validated team configuration, loaded from config/teams.yaml.

workflow/teams.md remains the human-readable registry but is generated from
this file (see generate_teams_doc) rather than hand-maintained.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, RootModel

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "teams.yaml"
DEFAULT_TEAMS_MD_PATH = REPO_ROOT / "workflow" / "teams.md"


class TeamConfig(BaseModel):
    name: str
    linear_org_mcp: str
    github_repository: str
    workflow: Literal["dev"]


class TeamsConfig(RootModel[dict[str, TeamConfig]]):
    def team_for_prefix(self, prefix: str) -> TeamConfig | None:
        return self.root.get(prefix)


def load_teams(path: Path = DEFAULT_CONFIG_PATH) -> TeamsConfig:
    raw = yaml.safe_load(path.read_text())
    return TeamsConfig.model_validate(raw["teams"])


RULES_SECTION = """
## Rules

- **The `Prefix` column is the authorization list.** A ticket surfaced by any connected Linear org
  MCP is actionable only if its key prefix matches a row above. Reaching a ticket via an MCP query is
  **not** authorization — the org MCPs contain teams beyond the ones listed here, and those are out of
  scope. Every skill re-checks the prefix against this file independently (defense in depth); this
  file is the only place the list lives.
- **`VER` and `APPAI` share the `linear-skry` org MCP** — they're separate teams in the same Linear
  workspace, so no new MCP connection is required to reach `APPAI`.
- **`Workflow = dev`** means the full code lifecycle (Backlog → Todo → implement → PR → tests →
  review → Done) driven by `skills/worker/SKILL.md`.
- **`Target GitHub repo`** is where `/worker`'s `start_implementation` opens branches/PRs for that
  team.
- **To add a team:** add a row to `config/teams.yaml` and regenerate this file. **To retire one:**
  delete its entry there. Never inline team keys anywhere else in the workflow.
"""


def render_teams_md(teams: TeamsConfig) -> str:
    header = (
        "# Team registry — which Linear teams this automation serves\n\n"
        "The single source of truth is `config/teams.yaml`; this file is generated from it by "
        "`digital-twin generate-teams-doc` and should not be hand-edited.\n\n"
        "| Prefix  | Team name       | Linear org MCP  | Target GitHub repo              | Workflow |\n"
        "| ------- | --------------- | --------------- | -------------------------------- | -------- |\n"
    )
    rows = [
        f"| `{prefix}` | {team.name} | `{team.linear_org_mcp}` | `{team.github_repository}` | {team.workflow} |"
        for prefix, team in teams.root.items()
    ]
    return header + "\n".join(rows) + "\n" + RULES_SECTION


def generate_teams_doc(
    config_path: Path = DEFAULT_CONFIG_PATH, out_path: Path = DEFAULT_TEAMS_MD_PATH
) -> None:
    teams = load_teams(config_path)
    out_path.write_text(render_teams_md(teams))
