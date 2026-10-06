#!/usr/bin/env bash
# SessionStart hook: orient the agent to the current workspace/project so a new
# session never starts cold. Generic — gated on a CLAUDE.md or STATUS.md in cwd,
# and injects STATUS.md (the living "current state") directly when present.
[ -f CLAUDE.md ] || [ -f STATUS.md ] || exit 0

ctx="SESSION START — Orient before doing substantive work: read CLAUDE.md in full; skim any SPEC_*.md / BACKLOG.md at the workspace root; and consult the Atlas framework for the method/conventions (run \`bash ~/.claude/atlas-fetch.sh llms.txt\` for the index, then fetch the piece you need). Do NOT start from zero or make the user re-explain the workspace, repos, or what the project is.

CADENCE — follow the Atlas cadence (method/05-discipline.md): bounded SPEC -> its branch from develop -> step by step, the how approved per the SPEC's working mode -> findings beside the SPEC -> independent review -> the human commits and closes. If you see a drift signal (code requested with no SPEC in STATUS Active; two SPECs in progress and not paused in one repo; work outside the SPEC branch or on main; in paired mode, a step coded without its how approved; a close without independent review or commit), say so ONCE, then follow the human's call. The human runs every git command; give them the exact command. Sessions are disposable: write a decision where it belongs (CLAUDE.md, the SPEC, its findings or the backlog) the moment it is taken — except the how, whose record is the code; one fresh session per SPEC (or per large block of it), and before stopping rewrite its Active block as the handoff. WORKING MODE — read the active SPEC's mode: line (or the Atlas default in CLAUDE.md). paired: propose the how of each step and wait for the human's approval. delegated: as the workbench, execute end to end and stop only on a real blocker or a decision the SPEC doesn't cover; as the principal, hand over a precise, self-contained prompt and review the result. ENVIRONMENT — look at where you stand and what is available, and follow that environment's own rules; where there are none, propose carefully and ask the human before installing or changing anything — never install tooling to match a prompt."

settings=_settings/atlas.toml
header='^[[:space:]]*\[[[:space:]]*plugins\."?coding-rules"?[[:space:]]*\]'
if [ -f "$settings" ] && tr -d '\r' < "$settings" | grep -Eq "$header"; then
    source=$(tr -d '\r' < "$settings" | awk -v h="$header" '
        $0 ~ h { inside = 1; next }
        inside && /^[[:space:]]*\[/ { exit }
        inside && match($0, /^[[:space:]]*source[[:space:]]*=[[:space:]]*["\047][^"\047]*["\047]/) {
            value = substr($0, RSTART, RLENGTH); sub(/^[^"\047]*["\047]/, "", value); sub(/["\047]$/, "", value); print value; exit
        }')
    [ -n "$source" ] || source="(unreadable — check [plugins.coding-rules] in _settings/atlas.toml)"
    ctx="$ctx"$'\n\n'"CODING RULES — this Atlas declares the coding-rules plugin with source \"$source\" (an mcp:<server> source is queried through that MCP server's tools; a file:<path> source is read from the Atlas). Recall the rules for the area from it before writing code, and follow them. A candidate rule goes to CODING_RULES_CANDIDATES.md and is promoted to the source only in a dedicated session with the human's approval — never written to the source mid-task. A deliberate divergence goes to CODING_RULES_DEVIATIONS.md."
    if [ -f CODING_RULES_DEVIATIONS.md ]; then
        ctx="$ctx"$'\n\n'"=== CODING_RULES_DEVIATIONS.md — deviations in force ==="$'\n'"$(cat CODING_RULES_DEVIATIONS.md)"
    fi
fi

if [ -f "$settings" ] && command -v atlas >/dev/null 2>&1; then
    state=$(atlas status 2>/dev/null)
    if [ -n "$state" ]; then
        ctx="$ctx"$'\n\n'"=== atlas status — where the Atlas and its sources stand ==="$'\n'"$state"
    fi
fi

if [ -f STATUS.md ]; then
    ctx="$ctx"$'\n\n'"=== STATUS.md — current state & next steps (read this first) ==="$'\n'"$(cat STATUS.md)"
fi

jq -n --arg ctx "$ctx" \
  '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$ctx}}'
