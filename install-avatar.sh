#!/usr/bin/env bash
# Install Albin's agent setup into ~/.claude/:
#   - be-albin skill        (avatar identity, bundled with the avatar profile)
#   - look-for-work skill   (candidate-finder the avatar relies on)
#   - maybe-do-work skill   (autonomous executor; chains the other two)
#   - CLAUDE.md auto-load pointer so Claude Code sessions pick it all up
#
# Idempotent — safe to re-run. After the first run, ~/.claude/skills/<each>/
# are the canonical homes; staging files in this workspace folder become
# superfluous.
#
# Usage:
#   bash /Users/albin/Documents/Claude/Projects/AlbinAI/install-avatar.sh

set -euo pipefail

STAGING="/Users/albin/Documents/Claude/Projects/AlbinAI"
SKILLS_ROOT="$HOME/.claude/skills"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"
SENTINEL="<!-- albin-avatar:pointer -->"

# Install a single skill: copy listed files into ~/.claude/skills/<name>/,
# init git there if needed, otherwise commit drift. Each skill folder gets its
# own git history — the natural unit.
#
# Usage: install_skill <name> <init-commit-message> <source-file:dest-name> [<source-file:dest-name>...]
install_skill() {
    local name="$1"
    local init_msg="$2"
    shift 2

    local dir="$SKILLS_ROOT/$name"
    echo ""
    echo "==> $name"
    mkdir -p "$dir"

    local -a tracked=()
    for spec in "$@"; do
        local src="${spec%%:*}"
        local dst="${spec##*:}"
        cp "$STAGING/$src" "$dir/$dst"
        echo "  -> $dir/$dst"
        tracked+=("$dst")
    done

    cd "$dir"
    if [ ! -d .git ]; then
        git init -b main >/dev/null
        git add "${tracked[@]}"
        git -c user.name="Albin" -c user.email="albinjon@outlook.com" \
            commit -m "$init_msg" --quiet
        echo "  -> initial commit"
    else
        if ! git diff --quiet || ! git diff --cached --quiet || \
           [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
            git add -A
            git -c user.name="Albin" -c user.email="albinjon@outlook.com" \
                commit -m "update $name" --quiet
            echo "  -> committed updates"
        else
            echo "  -> no changes to commit"
        fi
    fi
}

# --- 1. Clean up any partial .git left in the staging folder by Cowork sandbox ---
if [ -d "$STAGING/.git" ] && ! (cd "$STAGING" && git rev-parse --git-dir >/dev/null 2>&1); then
    echo "Cleaning up partial .git in staging folder ..."
    rm -rf "$STAGING/.git"
fi

# --- 2. Install all three skills ---
install_skill "be-albin" \
    "be-albin v1: skill + bundled avatar profile" \
    "be-albin-skill.md:SKILL.md" \
    "albin-avatar.md:albin-avatar.md"

install_skill "look-for-work" \
    "look-for-work v1: candidate-finder for the avatar's what-should-I-do-now loop" \
    "look-for-work-skill.md:SKILL.md"

install_skill "maybe-do-work" \
    "maybe-do-work v1: autonomous executor chaining /look-for-work + /be-albin" \
    "maybe-do-work-skill.md:SKILL.md"

# --- 3. Append the auto-load pointer to ~/.claude/CLAUDE.md (idempotent) ---
echo ""
echo "==> CLAUDE.md pointer"
mkdir -p "$(dirname "$CLAUDE_MD")"
if [ -f "$CLAUDE_MD" ] && grep -qF "$SENTINEL" "$CLAUDE_MD"; then
    echo "  -> already present, skipping"
else
    cat >>"$CLAUDE_MD" <<'EOF'


<!-- albin-avatar:pointer -->
# Albin avatar

When acting on Albin's behalf in engineering work, read and apply the avatar profile at `~/.claude/skills/be-albin/albin-avatar.md`. It defines the engineering taste (earn-its-keep, no defensive maximalism), execution rules (think-before-coding, surgical-not-bandaid, goal-driven with verify steps), autonomy rules (act on reversible, propose on the rest; never send human-facing messages, never merge to main, never force-push shared history), work bias (unblock others -> small shippable -> tech debt -> hard problems), and output voice (casual, conversational).

Three skills work together:
- `be-albin` — adopts the avatar identity; load before any work delegated from Albin.
- `look-for-work` — scans candidate work (PRs, tickets, threads needing reply) and produces a structured candidate list.
- `maybe-do-work` — runs the full autonomous loop: scan via /look-for-work, adopt via /be-albin, pick the highest-priority reversible item, execute, report. "Did nothing" is a valid outcome when nothing reversible is appropriate.
EOF
    echo "  -> $CLAUDE_MD updated"
fi

echo ""
echo "Done. Wiring:"
echo "  - be-albin           $SKILLS_ROOT/be-albin/        (skill + bundled avatar, git'd)"
echo "  - look-for-work      $SKILLS_ROOT/look-for-work/   (skill, git'd)"
echo "  - maybe-do-work      $SKILLS_ROOT/maybe-do-work/   (skill, git'd)"
echo "  - Auto-load (Code)   $CLAUDE_MD"
echo "  - Auto-load (Cowork) memory files (in place)"
echo ""
echo "Staging files in $STAGING/ are no longer canonical — delete the folder"
echo "or keep it as a Cowork working area, your call."
echo ""
echo "Smoke tests (run each in a fresh Claude Code session):"
echo "  1. 'what should I do now?'         -> avatar consults /look-for-work, recommends"
echo "  2. 'find me something to do'       -> /look-for-work directly, candidate list"
echo "  3. 'go pick something and do it'   -> /maybe-do-work, autonomous loop"
echo ""
echo "For (3), the avatar's hard limits bound the risk:"
echo "  - no human-facing messages get sent (drafts only)"
echo "  - no merges to main/production"
echo "  - no force-pushes to shared branches"
echo "  - no silent architecture-level decisions"
echo "But you should still review the first few runs end-to-end."
