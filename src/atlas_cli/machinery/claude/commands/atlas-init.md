---
description: Create an Atlas in the current folder — or bring an older one to the current model — with the atlas CLI, then write its orientation with the human.
argument-hint: [optional notes]
---

Create an Atlas in the current folder. **The CLI does everything mechanical; this command never restates its recipe.** The framework (`atlas method`, `atlas method <page>`) is the reference for anything the CLI doesn't decide.

Notes: $ARGUMENTS

1. **Check the CLI:** `atlas --version`. If `atlas` is not available, tell the human it is installed with `uv tool install paranoid-atlas-cli` and stop — don't install it yourself.
2. **Create or migrate:**
   - a folder without `AGENTS.md`, `CLAUDE.md`, `STATUS.md` or `_settings/atlas.toml` → `atlas init`;
   - a folder with `AGENTS.md`, `CLAUDE.md` or `STATUS.md` but no `_settings/atlas.toml` (an older Atlas), or one whose orientation file is still `CLAUDE.md` → `atlas migrate`, show the plan to the human, and run `atlas migrate --apply` only on their approval;
   - a folder that already has `_settings/atlas.toml` → it is an Atlas already: stop and point to `/atlas-sync`.
3. **Add the sources** the human names: `atlas link <name> <path>` for each. **Declare the workbench:** `atlas workbench add claude`, so Claude Code can read the sources (the editor's git settings are the Atlas's own, written by `atlas init`). Then `atlas doctor` until every source is `ok`.
4. **Orientation:** with the human, write each source's block in `AGENTS.md` §1 (`atlas method 03` — "The source orientation block"), from its README; ask when there is none or it is ambiguous.
5. **Coding rules (optional):** if the human wants a shared coding-rules memory for this Atlas, `atlas plugin add coding-rules <source>` with the source they choose.
6. **Report** what the CLI created or changed and what is left for the human.
