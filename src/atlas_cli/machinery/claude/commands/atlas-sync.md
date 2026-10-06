---
description: Checkpoint the current Atlas — refresh STATUS.md (Active resume blocks + recently closed), reconcile the sources, lint SPECs for contamination — per the Atlas model defined in the Atlas framework.
argument-hint: [optional focus area]
---

Checkpoint the current Atlas's memory now. **The model — what STATUS holds, what CLAUDE holds, the digest rules, file naming — is DEFINED IN THE ATLAS FRAMEWORK. Do not restate or improvise it here; fetch it and apply it.**

Optional focus: $ARGUMENTS

1. **Load the definition:** `bash ~/.claude/atlas-fetch.sh method/03-atlas-anatomy.md` (the files of record, `STATUS.md`'s three sections, "Sources: declared once, located per machine") and `bash ~/.claude/atlas-fetch.sh method/04-spec-lifecycle.md` (what a SPEC is / is not, the resume & checkpoint protocol), or invoke the `workspace-baseline` skill. `atlas-fetch.sh` reads the single source in `~/.claude/atlas-source` (URL → curl, local clone → cat). If the fetch fails, surface it — don't improvise.
2. **Locate the Atlas root** — nearest dir at/above CWD with `STATUS.md`. If none, say it's not an Atlas and stop. Run every `atlas` command from that root. If it has no `_settings/atlas.toml`, it is an older Atlas: point to `/atlas-init` (`atlas migrate`) and stop.
3. **Reconcile the sources** with the CLI: run `atlas doctor`.
   - **missing / broken / undeclared** → follow the commands it suggests (`atlas link …`), asking the human before removing anything.
   - **rules** → report the rule files found in that source; don't touch the source.
   - A source added since the last sync needs its orientation block in `CLAUDE.md` §1 (read its README; ask if ambiguous); a source gone leaves a stale block — flag it and **ask before deleting**.
4. **Refresh `STATUS.md`** — start from `atlas status` (Active SPECs, SPECs out of place, each source's branch and changes, paused SPECs); three fixed sections that never mix:
   - **Active** — one block per SPEC currently `IN PROGRESS` / `IN REVIEW`, with **Done / Next / Blocked** (Next = which step of the SPEC's Plan). Take each block's current state from the session (ask the user if unclear) and **rewrite it to the current state — never append**. **Move any closed SPEC out of Active** into Recently closed (and confirm it sits in `_archived/` with its findings file, if any).
   - **Recently closed** — a short rolling window pointing into `_archived/`; the full history stays in `_archived/`.
   - **What it is** — one line.
   Update `CLAUDE.md` only if a standing decision / orientation fact changed (a source added or gone in step 3 is one such change). Let the framework decide what belongs where — your job is to apply that definition, not duplicate it.
5. **Lint the SPECs** (report — don't silently rewrite): flag as **contaminated** any SPEC containing a fenced code block (` ``` `), a checkbox (`- [x]` / `- [ ]`), a `Progress` / `Verification` / `Notes` / `Status` / `Findings` heading or findings content, a Plan that reads like implementation (technique, code, or long), or archaeology ("previously", "used to", "changed from", "attempt", "no longer"). Also flag any SPEC still listed in Active after it closed. Say what to strip and where it belongs: state → `STATUS → Active`; findings → `SPEC_NNNN_FINDINGS.md`; the how / technique → decided live, its record is the code (general working rules → the coding-rules source, when the Atlas declares one); code → the repo; history → git / `_archived/`.
6. **Report** what you wrote to `STATUS.md` and `CLAUDE.md` (incl. any source blocks added or flagged), what `atlas doctor` reported, and every SPEC flagged in step 5.
