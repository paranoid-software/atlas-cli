#!/usr/bin/env bash
# Coding-rules gate. In an Atlas that declares the coding-rules plugin, no code is edited in a
# session before the rules have been consulted.
#   PostToolUse (any MCP tool or Read): a call that consults the declared source marks the
#     session as having consulted it.
#   PreToolUse (Edit|Write|MultiEdit|NotebookEdit): an edit outside the Atlas's own files is
#     denied until that mark exists.
# Anything it cannot read (no jq, no settings, no session id) lets the call through, and so
# does ATLAS_CODING_RULES_GATE=off in the environment Claude Code was started with — the human's
# way out when the source can't be reached.
[ "${ATLAS_CODING_RULES_GATE:-}" = "off" ] && exit 0
command -v jq >/dev/null 2>&1 || exit 0
input=$(cat)
event=$(jq -r '.hook_event_name // empty' <<<"$input" 2>/dev/null)
cwd=$(jq -r '.cwd // empty' <<<"$input" 2>/dev/null)
session=$(jq -r '.session_id // empty' <<<"$input" 2>/dev/null)
# The Atlas is the session's project folder; cwd moves when the agent cds into a source.
root=${CLAUDE_PROJECT_DIR:-$cwd}
root=${root%/}
[ -n "$root" ] && [ -n "$session" ] || exit 0

settings="$root/_settings/atlas.toml"
header='^[[:space:]]*\[[[:space:]]*plugins\."?coding-rules"?[[:space:]]*\]'
[ -f "$settings" ] && tr -d '\r' < "$settings" 2>/dev/null | grep -Eq "$header" || exit 0
source=$(tr -d '\r' < "$settings" 2>/dev/null | awk -v h="$header" '
    $0 ~ h { inside = 1; next }
    inside && /^[[:space:]]*\[/ { exit }
    inside && match($0, /^[[:space:]]*source[[:space:]]*=[[:space:]]*["\047][^"\047]*["\047]/) {
        value = substr($0, RSTART, RLENGTH); sub(/^[^"\047]*["\047]/, "", value); sub(/["\047]$/, "", value); print value; exit
    }')
[ -n "$source" ] || exit 0
# Claude Code names MCP tools with the server name's other characters turned into "_".
server=$(printf '%s' "${source#mcp:}" | tr -c 'A-Za-z0-9_-' '_')
rules_file="$root/${source#file:}"
rules_file=${rules_file//\/.\//\/}

marks="${TMPDIR:-/tmp}/atlas-coding-rules"
mark="$marks/$(printf '%s' "$session" | tr -c 'A-Za-z0-9_-' '_')"
tool=$(jq -r '.tool_name // empty' <<<"$input")

if [ "$event" = "PostToolUse" ]; then
    consulted=
    case "$source" in
        mcp:*) case "$tool" in "mcp__${server}__"*) consulted=1 ;; esac ;;
        file:*)
            if [ "$tool" = "Read" ]; then
                read_path=$(jq -r '.tool_input.file_path // empty' <<<"$input")
                read_path=${read_path//\/.\//\/}
                [ "$read_path" = "$rules_file" ] && consulted=1
            fi ;;
    esac
    if [ -n "$consulted" ]; then
        mkdir -p "$marks" 2>/dev/null && : > "$mark" 2>/dev/null
    fi
    exit 0
fi

[ "$event" = "PreToolUse" ] || exit 0
[ -f "$mark" ] && exit 0
path=$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' <<<"$input")
[ -n "$path" ] || exit 0
case "$path" in
    */../*|*/..) ;;
    "$root"/*)
        relative=${path#"$root"/}
        case "$relative" in
            */*) case "${relative%%/*}" in _*|.claude|.vscode) exit 0 ;; esac ;;
            *.md|.gitignore) exit 0 ;;
        esac ;;
esac

case "$source" in
    mcp:*) how="query it through the ${source#mcp:} MCP server's tools (mcp__${server}__…, e.g. its recall or search)" ;;
    file:*) how="read $rules_file" ;;
    *) how="consult it" ;;
esac
reason="CODING RULES GATE — this Atlas declares the coding-rules plugin with source \"$source\", and its rules have not been consulted in this session. Before writing code, $how for the area you are about to change, say which rules apply (by id when the source has ids), follow them, then make this edit again. CODING_RULES_CANDIDATES.md and CODING_RULES_DEVIATIONS.md at the Atlas root are in force too. Do not route around this gate (for instance by writing files through the shell); if the source cannot be reached, stop and tell the human."
jq -n --arg reason "$reason" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$reason}}'
