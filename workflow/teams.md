# Team registry — which Linear teams this automation serves

The single source of truth for the team allowlist and each team's bindings. Every skill
(`/poller`, `/worker`, `/intervention-pinger`) authorizes work by the ticket key's team prefix,
and reads that allowlist from this file instead of inlining it. Onboarding a team is one row here;
no skill prose changes.

| Prefix  | Team name       | Linear org MCP | Target GitHub repo | Workflow |
| ------- | --------------- | -------------- | ------------------ | -------- |
| `VER`   | Verkis          | verkis         | `<fill>`           | dev      |
| `LAV`   | Ledger / Lavora | `<fill>`       | `<fill>`           | dev      |
| `ZBS`   | ZBS-Web         | `<fill>`       | `<fill>`           | dev      |
| `APPAI` | Appraisal       | verkis         | `<fill>`           | dev      |

## Rules

- **The `Prefix` column is the authorization list.** A ticket surfaced by any connected Linear org
  MCP is actionable only if its key prefix matches a row above. Reaching a ticket via an MCP query is
  **not** authorization — the org MCPs contain teams beyond the ones listed here, and those are out of
  scope. Every skill re-checks the prefix against this file independently (defense in depth); this
  file is the only place the list lives.
- **`APPAI` shares the `verkis` org MCP with `VER`** — it's a separate team in the same Linear
  workspace, so no new MCP connection is required to reach it.
- **`Workflow = dev`** means the full code lifecycle (Backlog → Todo → implement → PR → tests →
  review → Done) driven by `skills/worker/SKILL.md`.
- **`Target GitHub repo`** is where `/worker`'s `start_implementation` opens branches/PRs for that
  team. Fill each `<fill>` from Hermes' configured mapping. `verkis` for VER/APPAI is confirmed;
  the remaining `Linear org MCP` names are informational only — skills iterate every connected org
  MCP and filter by prefix, so they don't select an MCP by name.
- **To add a team:** add a row. **To retire one:** delete its row. Never inline team keys anywhere
  else in the workflow.
