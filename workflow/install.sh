#!/usr/bin/env bash
#
# install.sh — wire workflow skills into ~/.claude/skills and $HERMES_SKILLS_DIR.
#
# The repo's workflow/ folder is the source of truth. This script symlinks
# each skill into both locations so Claude Code (interactive) and Hermes (cron)
# pick them up from the same place. Re-runnable; --dry-run prints actions.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOW_DIR="$SCRIPT_DIR"
SKILLS_SRC="$WORKFLOW_DIR/skills"

CLAUDE_SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
HERMES_SKILLS_DIR="${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}"

DRY_RUN=0
FORCE=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [--dry-run] [--force]

Symlinks every skill in $SKILLS_SRC/* into:
  - \$CLAUDE_SKILLS_DIR  (default: \$HOME/.claude/skills)
  - \$HERMES_SKILLS_DIR  (default: \$HOME/.hermes/skills)

Also symlinks delegation-contract.md, automation-playbook.md, and teams.md into
both locations so they travel with the skills.

Flags:
  --dry-run   Print actions without changing anything.
  --force     Replace real directories at the install target (backs them up as <name>.bak).
              Without --force, existing symlinks are refreshed but real dirs are left alone.
EOF
}

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; usage; exit 2 ;;
  esac
done

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY: $*"
  else
    "$@"
  fi
}

ensure_dir() {
  local dir="$1"
  if [[ ! -d "$dir" ]]; then
    run mkdir -p "$dir"
  fi
}

# Install one source path as a symlink at a target path.
# - If target is missing: link.
# - If target is an existing symlink: refresh it.
# - If target is a real file/dir: back up to <target>.bak (only with --force), then link.
install_link() {
  local src="$1"
  local dst="$2"

  if [[ ! -e "$src" ]]; then
    echo "skip: source missing: $src" >&2
    return
  fi

  if [[ -L "$dst" ]]; then
    # existing symlink — refresh it
    run rm -f "$dst"
  elif [[ -e "$dst" ]]; then
    if [[ "$FORCE" -ne 1 ]]; then
      echo "skip: $dst exists (use --force to back it up and replace)" >&2
      return
    fi
    local backup="$dst.bak"
    if [[ -e "$backup" ]]; then
      # don't clobber an existing backup
      backup="$dst.bak.$(date +%s)"
    fi
    echo "backing up $dst -> $backup"
    run mv "$dst" "$backup"
  fi

  run ln -s "$src" "$dst"
  echo "linked: $dst -> $src"
}

# Targets
ensure_dir "$CLAUDE_SKILLS_DIR"
ensure_dir "$HERMES_SKILLS_DIR"

# Each skill folder
for skill_path in "$SKILLS_SRC"/*/; do
  [[ -d "$skill_path" ]] || continue
  name="$(basename "$skill_path")"
  install_link "${skill_path%/}" "$CLAUDE_SKILLS_DIR/$name"
  install_link "${skill_path%/}" "$HERMES_SKILLS_DIR/$name"
done

# Shared docs
for doc in delegation-contract.md automation-playbook.md teams.md; do
  src="$WORKFLOW_DIR/$doc"
  install_link "$src" "$CLAUDE_SKILLS_DIR/$doc"
  install_link "$src" "$HERMES_SKILLS_DIR/$doc"
done

echo "done."
