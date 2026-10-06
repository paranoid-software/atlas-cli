#!/bin/sh
# atlas-fetch — read one file of the Atlas framework from the configured source.
#
# The source is a SINGLE, mutually-exclusive value in atlas-source, in the Claude config folder
# (CLAUDE_CONFIG_DIR, or ~/.claude when unset):
#   - a URL          (http:// or https://)  -> fetched with curl
#                       (https://atlas.paranoid.software — the official site; or
#                        http://localhost:8088 for local dev / host.docker.internal in a container)
#   - a local path   (anything else)        -> read from the cloned repo with cat
# To switch (localhost <-> public domain <-> local clone), edit that one line.
#
# Usage:  atlas-fetch.sh <relative/path>
#   e.g.  atlas-fetch.sh llms.txt
#         atlas-fetch.sh method/06-bootstrap.md
config="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
src=$(head -1 "$config/atlas-source" 2>/dev/null | tr -d '[:space:]')
[ -n "$src" ] || { echo "atlas-fetch: configure $config/atlas-source (a URL or a repo path)" >&2; exit 1; }
[ -n "${1:-}" ] || { echo "atlas-fetch: usage: atlas-fetch.sh <relative/path>" >&2; exit 2; }
case "$src" in
  http://*|https://*) exec curl -fsS --max-time 5 "$src/$1" ;;
  *)                  exec cat "$src/$1" ;;
esac
