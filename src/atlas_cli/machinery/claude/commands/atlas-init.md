---
description: Create an Atlas in the current folder — or bring an older one to the current model — with the atlas CLI, then write its orientation with the human.
argument-hint: [optional notes]
---

Create an Atlas in the current folder. **The CLI does everything mechanical; this command never restates its recipe.** The framework (fetched with `bash ~/.claude/atlas-fetch.sh <path>`) is the reference for anything the CLI doesn't decide.

Notes: $ARGUMENTS

1. **Check the CLI:** `atlas --version`. If `atlas` is not available, tell the human it is installed with `uv tool install paranoid-atlas-cli` and stop — don't install it yourself.
2. **Create or migrate:**
   - a folder without `CLAUDE.md`, `STATUS.md` or `_settings/atlas.toml` → `atlas init`;
   - a folder with `CLAUDE.md` or `STATUS.md` but no `_settings/atlas.toml` (an older Atlas) → `atlas migrate`, show the plan to the human, and run `atlas migrate --apply` only on their approval;
   - a folder that already has `_settings/atlas.toml` → it is an Atlas already: stop and point to `/atlas-sync`.
3. **Add the sources** the human names: `atlas link <name> <path>` for each; then `atlas doctor` until every source is `ok`.
4. **Orientation:** with the human, write each source's block in `CLAUDE.md` §1 (`bash ~/.claude/atlas-fetch.sh method/03-atlas-anatomy.md` — "The source orientation block"), from its README; ask when there is none or it is ambiguous.
5. **Coding rules (optional):** if the human wants a shared coding-rules memory for this Atlas, `atlas plugin add coding-rules <source>` with the source they choose.
6. **Report** what the CLI created or changed and what is left for the human.
