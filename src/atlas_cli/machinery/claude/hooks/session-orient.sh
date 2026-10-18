#!/usr/bin/env bash
# SessionStart hook: orient the agent to the current Atlas so a new session never starts
# cold. The text is `atlas orient`'s — the CLI is the one place it lives, for any workbench.
# Gated on a CLAUDE.md or STATUS.md in cwd; injects the command's output, on an older Atlas
# its pointer to `atlas migrate` included.
[ -f CLAUDE.md ] || [ -f STATUS.md ] || exit 0

if command -v atlas >/dev/null 2>&1; then
    ctx=$(atlas orient 2>/dev/null)
    [ -n "$ctx" ] || ctx="SESSION START — this folder is an Atlas, but \`atlas orient\` printed nothing (an atlas CLI older than 0.16?): upgrade it (uv tool install --reinstall --refresh paranoid-atlas-cli) and run \`atlas orient\`."
else
    ctx="SESSION START — this folder is an Atlas, but the atlas CLI is not on PATH, so its orientation could not be read: install it (uv tool install paranoid-atlas-cli) and run \`atlas orient\`."
fi

jq -n --arg ctx "$ctx" \
  '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$ctx}}'
