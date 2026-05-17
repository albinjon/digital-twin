#!/usr/bin/env bash
# Install Albin's agent setup into ~/.claude/:
#   - be-albin skill        (loads engineering SOUL; bundled with SOUL.md)
#   - look-for-work skill   (candidate-finder, SOUL-aware downstream consumers)
#   - maybe-do-work skill   (autonomous executor; chains look-for-work + be-albin + notify)
#   - refine skill          (Linear backlog refinement; routes to Todo or Intervention)
#   - router skill          (Linear ticket state reconciliation)
#   - implement skill       (Linear Todo -> branch + non-draft PR + In Progress)
#   - review skill          (devil's-advocate PR review on In Progress tickets)
#   - fixer skill           (Review Fixes -> coherent fix pass on existing PR -> In Progress)
#   - CLAUDE.md auto-load pointer so Claude Code sessions pick it all up
#
# Idempotent — safe to re-run. After the first run, ~/.claude/skills/<each>/
# are the canonical homes; staging files in this workspace folder become
# superfluous. On re-install, any orphan albin-avatar.md from a previous
# install gets cleaned up.
#
# Usage:
#   bash /Users/albin/digital-albin/claude-desktop/Documents/Claude/Projects/AlbinAI/install-avatar.sh

set -euo pipefail

STAGING="/Users/albin/digital-albin/claude-desktop/Documents/Claude/Projects/AlbinAI"
SKILLS_ROOT="$HOME/.claude/skills"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"
SENTINEL="<!-- albin-soul:pointer -->"
OLD_SENTINEL="<!-- albin-avatar:pointer -->"

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

# --- 2. Migrate: remove orphan albin-avatar.md from a prior install ---
ORPHAN="$SKILLS_ROOT/be-albin/albin-avatar.md"
if [ -f "$ORPHAN" ]; then
    echo "Removing orphan albin-avatar.md (superseded by SOUL.md) ..."
    rm "$ORPHAN"
fi

# --- 3. Install all three skills ---
install_skill "be-albin" \
    "be-albin v2: load engineering SOUL (principles + personal calibration)" \
    "be-albin-skill.md:SKILL.md" \
    "SOUL.md:SOUL.md"

install_skill "look-for-work" \
    "look-for-work v1: candidate-finder for the SOUL-driven what-should-I-do-now loop" \
    "look-for-work-skill.md:SKILL.md"

install_skill "maybe-do-work" \
    "maybe-do-work v1: autonomous executor chaining /look-for-work + /be-albin + /notify" \
    "maybe-do-work-skill.md:SKILL.md"

# Linear ticket lifecycle automations (invoked explicitly from workflows)
install_skill "refine" \
    "refine v1: Linear backlog refinement (clarify, deduplicate, label, route to Todo or Intervention)" \
    "refine-skill.md:SKILL.md"

install_skill "router" \
    "router v1: reconcile a Linear ticket's workflow state (Backlog/Todo/Review Fixes/Intervention/Done)" \
    "router-skill.md:SKILL.md"

install_skill "implement" \
    "implement v1: Linear Todo -> branch + non-draft PR + In Progress (with hierarchy/readiness checks)" \
    "implement-skill.md:SKILL.md"

install_skill "review" \
    "review v1: devil's-advocate PR review for In Progress tickets; routes to Review Fixes / Human / Intervention" \
    "review-skill.md:SKILL.md"

install_skill "fixer" \
    "fixer v1: implement PR feedback in one coherent pass on the existing branch; back to In Progress" \
    "fixer-skill.md:SKILL.md"

# --- 4. Append the auto-load pointer to ~/.claude/CLAUDE.md (idempotent) ---
echo ""
echo "==> CLAUDE.md pointer"
mkdir -p "$(dirname "$CLAUDE_MD")"

# If an old (avatar-flavored) pointer is present, leave a note for Albin to
# remove it; we don't auto-rewrite his CLAUDE.md, that's his to edit.
if [ -f "$CLAUDE_MD" ] && grep -qF "$OLD_SENTINEL" "$CLAUDE_MD"; then
    echo "  -> NOTE: previous '$OLD_SENTINEL' block detected in $CLAUDE_MD"
    echo "          You'll want to delete the old block manually; the new"
    echo "          SOUL pointer below replaces it (different sentinel)."
fi

if [ -f "$CLAUDE_MD" ] && grep -qF "$SENTINEL" "$CLAUDE_MD"; then
    echo "  -> SOUL pointer already present, skipping append"
else
    cat >>"$CLAUDE_MD" <<'EOF'


<!-- albin-soul:pointer -->
# Albin's engineering SOUL

When acting on Albin's behalf in engineering work, read and apply the SOUL doc at `~/.claude/skills/be-albin/SOUL.md`. It has two layers: universalizable engineering principles (earn-its-keep, surgical-not-bandaid, no defensive maximalism, goal-driven, etc.) and Albin's personal calibration (hard limits — never send human-facing messages, never merge to main, never force-push shared history; work-bias priority — unblock others -> small shippable -> tech debt -> hard problems; voice — casual, conversational).

The agent doesn't pretend to be Albin; it operates under the values he's codified.

Three skills work together:
- `be-albin` — loads SOUL. Use before any work delegated from Albin.
- `look-for-work` — scans candidate work (PRs, tickets, threads needing reply) and produces a structured candidate list for a SOUL-operating agent to reason over.
- `maybe-do-work` — runs the full autonomous loop: scan via /look-for-work, load SOUL via /be-albin, pick the highest-priority reversible item, execute, report (and notify Albin via /notify if he needs to weigh in). "Did nothing" is a valid outcome when nothing reversible is appropriate.
EOF
    echo "  -> $CLAUDE_MD updated"
fi

echo ""
echo "Done. Wiring:"
echo "  Identity + autonomous loop:"
echo "    - be-albin         $SKILLS_ROOT/be-albin/        (skill + bundled SOUL, git'd)"
echo "    - look-for-work    $SKILLS_ROOT/look-for-work/   (skill, git'd)"
echo "    - maybe-do-work    $SKILLS_ROOT/maybe-do-work/   (skill, git'd)"
echo "  Linear ticket lifecycle:"
echo "    - refine           $SKILLS_ROOT/refine/          (skill, git'd)"
echo "    - router           $SKILLS_ROOT/router/          (skill, git'd)"
echo "    - implement        $SKILLS_ROOT/implement/       (skill, git'd)"
echo "    - review           $SKILLS_ROOT/review/          (skill, git'd)"
echo "    - fixer            $SKILLS_ROOT/fixer/           (skill, git'd)"
echo "  Auto-load:"
echo "    - Code             $CLAUDE_MD"
echo "    - Cowork           memory files (in place)"
echo ""
echo "Staging files in $STAGING/ are no longer canonical — delete the folder"
echo "or keep it as a Cowork working area, your call."
echo ""
echo "Smoke tests (run each in a fresh Claude Code session):"
echo "  1. 'what should I do now?'         -> SOUL consults /look-for-work, recommends"
echo "  2. 'find me something to do'       -> /look-for-work directly, candidate list"
echo "  3. 'go pick something and do it'   -> /maybe-do-work, autonomous loop"
echo ""
echo "Linear lifecycle skills (invoke explicitly from a workflow):"
echo "  - /refine <issue>     fresh backlog ticket -> Todo or Intervention"
echo "  - /router <issue>     reconcile current state -> right workflow stage"
echo "  - /implement <issue>  Todo -> branch + non-draft PR + In Progress"
echo "  - /review <issue>     In Progress PR -> Review Fixes / Human / Intervention"
echo "  - /fixer <issue>      Review Fixes -> apply feedback -> In Progress"
echo ""
echo "SOUL's hard limits bound the autonomous-loop risk:"
echo "  - no human-facing messages get sent (drafts only)"
echo "  - no merges to main/production"
echo "  - no force-pushes to shared branches"
echo "  - no silent architecture-level decisions"
echo "Review the first few /maybe-do-work runs end-to-end."
