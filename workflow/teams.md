# Team registry — which Linear teams this automation serves

The single source of truth for the team allowlist and each team's bindings. Every skill
(`/poller`, `/worker`) authorizes work by the ticket key's team prefix,
and reads that allowlist from this file instead of inlining it. Onboarding a team is one row here;
no skill prose changes.

| Prefix  | Team name       | Linear org MCP  | Target GitHub repo              | Workflow |
| ------- | --------------- | --------------- | ------------------------------- | -------- |
| `VER`   | Verkis          | `linear-skry`   | `skry-ab/verkis`                | dev      |
| `LAV`   | Ledger / Lavora | `linear-lavora` | `Lavora-AB/Ledger`              | dev      |
| `ZBS`   | ZBS-Web         | `linear-zbs`    | `Zenbuddhistiska-Samfundet/web` | dev      |
| `APPAI` | Appraisal       | `linear-skry`   | `skry-ab/appraisal`             | dev      |

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
  team. The remaining `<fill>` cells (`LAV` / `ZBS` org MCP names) are informational only — skills
  iterate every connected org MCP and filter by prefix, so they don't select an MCP by name.
- **To add a team:** add a row. **To retire one:** delete its row. Never inline team keys anywhere
  else in the workflow.
