#!/usr/bin/env bash
# Stop hook: nudge the AGENT (via additionalContext) to OFFER a /atlas-sync checkpoint only when
# there is something to lose — a SPEC is in STATUS.md's Active section and one of its repos has
# changes newer than STATUS.md. At most once per checkpoint: after a nudge it stays silent until
# STATUS.md is rewritten. Never inside a Stop hook loop.

input=$(cat)

[ "$(jq -r '.stop_hook_active // false' <<<"$input" 2>/dev/null)" = "true" ] && exit 0

cwd=$(jq -r '.cwd // empty' <<<"$input" 2>/dev/null)
[ -z "$cwd" ] && exit 0

dir="$cwd"; atlas=""
while [ -n "$dir" ] && [ "$dir" != "/" ]; do
  [ -f "$dir/STATUS.md" ] && { atlas="$dir"; break; }
  dir=$(dirname "$dir")
done
[ -z "$atlas" ] && exit 0

status="$atlas/STATUS.md"
mtime=$(stat -c %Y "$status" 2>/dev/null || stat -f %m "$status" 2>/dev/null)
active=$(awk '/^## Active/{inside=1; next} /^## /{inside=0} inside && /^### SPEC_[0-9]+_/{print $2}' "$status")
[ -z "$active" ] && exit 0

changed=""
for spec in $active; do
  spec_file="$atlas/$spec.md"
  [ -f "$spec_file" ] || continue
  repos=$(sed -n 's/^repos:[[:space:]]*//p' "$spec_file" | head -1 | tr ',' ' ')
  for repo in $repos; do
    path="$atlas/$repo"
    git -C "$path" rev-parse --is-inside-work-tree >/dev/null 2>&1 || continue
    committed=$(git -C "$path" log -1 --format=%ct 2>/dev/null)
    [ -n "$committed" ] && [ "$committed" -gt "$mtime" ] && { changed="$changed $spec"; break; }
    while IFS= read -r file; do
      [ -n "$file" ] || continue
      target="$path/$file"
      [ -e "$target" ] || target=$(dirname "$target")
      [ -e "$target" ] && [ "$target" -nt "$status" ] && { changed="$changed $spec"; break 2; }
    done < <({ git -C "$path" diff --name-only HEAD 2>/dev/null; git -C "$path" ls-files --others --exclude-standard 2>/dev/null; })
  done
done
[ -z "$changed" ] && exit 0

cache="${TMPDIR:-/tmp}/atlas-sync-reminders"; mkdir -p "$cache" 2>/dev/null
key=$(printf '%s' "$atlas" | shasum 2>/dev/null | cut -d' ' -f1)
marker="$cache/${key:-default}"
[ -f "$marker" ] && [ "$(cat "$marker" 2>/dev/null)" = "$mtime" ] && exit 0
printf '%s' "$mtime" > "$marker"

msg="[atlas-sync] Work on${changed} changed after STATUS.md was last written. Before stopping, offer the user a quick /atlas-sync checkpoint so the Active block stays the handoff — do not run it unprompted."
jq -n --arg ctx "$msg" '{hookSpecificOutput:{hookEventName:"Stop",additionalContext:$ctx}}'
exit 0
