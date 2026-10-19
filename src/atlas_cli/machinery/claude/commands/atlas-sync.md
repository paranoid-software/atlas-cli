---
description: Checkpoint the current Atlas — refresh STATUS.md (Active resume blocks + recently closed), reconcile the sources, lint SPECs for contamination — per the Atlas model defined in the Atlas framework.
argument-hint: [optional focus area]
---

Checkpoint the current Atlas's memory now. **The model — what STATUS holds, what AGENTS.md holds, the digest rules, file naming — is DEFINED IN THE ATLAS FRAMEWORK. Do not restate or improvise it here; fetch it and apply it.**

Optional focus: $ARGUMENTS

1. **Load the definition:** `atlas method 03` (the files of record, `STATUS.md`'s three sections, "Sources: declared once, located per machine") and `atlas method 04` (what a SPEC is / is not, the resume & checkpoint protocol), or invoke the `workspace-baseline` skill. `atlas method` reads the source the CLI keeps (`atlas method --source` sets it). If it fails, surface it — don't improvise.
2. **Locate the Atlas root** — nearest dir at/above CWD with `STATUS.md`. If none, say it's not an Atlas and stop. Run every `atlas` command from that root. If it has no `_settings/atlas.toml`, it is an older Atlas: point to `/atlas-init` (`atlas migrate`) and stop.
3. **Run the mechanical part:** `atlas sync`. It prints the doctor's report, what it wrote (a missing `started:` on an Active SPEC, a missing `closed:` on an archived one, a closed SPEC still in Active moved to Recently closed), `atlas spec lint` of what remains, what it only reports (a SPEC at the root in neither the backlog nor Active, a SPEC listed whose file is nowhere) and `atlas status`. Read all of it before writing anything.
4. **Reconcile the sources** from the doctor's lines:
   - **missing / broken / undeclared** → follow the commands it suggests (`atlas link …`) for a source the Atlas keeps; a source that is gone from the Atlas is dropped with `atlas unlink <name>`, **only with the human's approval**.
   - **rules** (a notice, not a problem) → say which rule files that source carries and that they are its context, read with caution, never above the Atlas or the coding rules; don't touch the source.
   - A source added since the last sync needs its orientation block in `AGENTS.md` §1 (read its README; ask if ambiguous); a source gone (or just unlinked) leaves a stale block — flag it and **ask before deleting**.
5. **Write the judgment:** in `STATUS.md → Active`, one block per SPEC `IN PROGRESS` / `IN REVIEW`, with **Done / Next / Blocked** (Next = which step of the SPEC's Plan). Take each block's current state from the session (ask the user if unclear) and **rewrite it to the current state — never append**. The transitions themselves are `atlas spec`'s, never hand-edited: `atlas spec start|pause|resume|review|close <name>`; a SPEC the human says is closed and still sits in Active gets `atlas spec close`. Keep **What it is** to one line. Update `AGENTS.md` only if a standing decision / orientation fact changed (a source added or gone in step 4 is one such change). For each SPEC `atlas spec lint` flagged, and for what only judgment sees — a Plan that reads like implementation, findings content, session notes — say what to strip and where it belongs: state → `STATUS → Active`; findings → `SPEC_NNNN_FINDINGS.md`; the how → decided live, its record is the code; code → the repo; history → git / `_archived/`. Report, don't silently rewrite.
6. **Report** what `atlas sync` wrote and reported, what you wrote to `STATUS.md` and `AGENTS.md` (incl. any source blocks added or flagged), and every SPEC flagged in step 5.
