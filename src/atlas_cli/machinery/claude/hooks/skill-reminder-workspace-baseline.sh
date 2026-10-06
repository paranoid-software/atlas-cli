#!/usr/bin/env bash
# UserPromptSubmit hook: nudge to invoke the workspace-baseline skill when the prompt is
# about creating / bootstrapping / syncing an Atlas — unless the skill was already invoked in
# this session.
input=$(cat)
PROMPT=$(jq -r '.prompt // ""' <<<"$input")
printf '%s' "$PROMPT" | grep -qiE 'workspace[- ]?baseline|(nuevo|new) atlas|(nuevo|new) workspace|bootstrap.{0,40}(atlas|workspace)|(atlas|workspace).{0,40}bootstrap|atlas[- ]?(init|sync)' || exit 0
transcript=$(jq -r '.transcript_path // empty' <<<"$input")
[ -n "$transcript" ] && [ -f "$transcript" ] && grep -qE '"name":"Skill","input":\{"skill":"workspace-baseline"|command-name>/workspace-baseline<' "$transcript" && exit 0
jq -n --arg ctx 'REMINDER: this prompt relates to workspace-baseline. Invoke the workspace-baseline Skill BEFORE answering. The canonical Atlas framework (architecture + bootstrap recipe) is fetched via "bash ~/.claude/atlas-fetch.sh" from the single source in ~/.claude/atlas-source (a URL or a local clone). Do not rely on memory of any docs folder.' \
  '{hookSpecificOutput:{hookEventName:"UserPromptSubmit",additionalContext:$ctx}}'
