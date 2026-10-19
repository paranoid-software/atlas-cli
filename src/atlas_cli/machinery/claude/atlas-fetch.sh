#!/bin/sh
# atlas-fetch — read one file of the Atlas framework. The CLI does it: `atlas method` prints the
# index, `atlas method <page>` a page, `atlas method --full` the whole text, from the source
# `atlas method --source <url|path>` set. This script only maps the old paths onto it.
#
# Usage:  atlas-fetch.sh llms.txt | llms-full.txt | method/<page>.md
command -v atlas >/dev/null 2>&1 || { echo "atlas-fetch: the atlas CLI is not on PATH" >&2; exit 1; }
case "${1:-}" in
  ""|llms.txt)     exec atlas method ;;
  llms-full.txt)   exec atlas method --full ;;
  method/*)        exec atlas method "$1" ;;
  *)               echo "atlas-fetch: usage: atlas-fetch.sh llms.txt | llms-full.txt | method/<page>.md" >&2; exit 2 ;;
esac
