---
name: workspace-baseline
description: Use when bootstrapping a new Atlas (symlink-aggregator project root), editing CLAUDE.md / STATUS.md / BACKLOG.md / SPEC_*.md / DRAFT_*.md / _archived/ / the coding-rules plugin files, deciding where a piece of knowledge belongs across the stores, or auditing the user-global setup. The canonical Atlas framework (architecture + bootstrap recipe) lives in the Atlas framework doc, read with `atlas method`. This skill is the entry point — fetch the framework, then act.
---

# workspace-baseline

The canonical Atlas framework (architecture + bootstrap recipe) lives in the **Atlas framework doc**, read with `atlas method` from the source the CLI keeps (`atlas method --source <url|path>`: the official site `https://atlas.paranoid.software`, `http://localhost:8088` for local dev, or a local clone). This skill is the entry point: fetch the framework, then act.

## Step 1 — load the framework definition

```
atlas method                  # the index — start here
atlas method --full           # the whole framework in one text
atlas method 06               # a specific piece (06, 06-bootstrap or method/06-bootstrap.md)
```

`atlas method` reads the framework from the source the CLI keeps (`atlas method --source <url|path>` sets it: the site, a local copy of it, or a clone of the framework repo). If it fails, the source is unreachable / misconfigured — surface that, don't improvise the framework from memory.

Returns the Atlas framework:

- **The Atlas model** (`method/01-the-atlas.md`) — an **Atlas** is a symlink-aggregator project root; why it exists.
- **The stores model** (`method/02-stores-model.md`) — where each kind of knowledge lives; the `coding-rules` plugin each Atlas chooses (source `mcp:<server>` or `file:<path>`, with `CODING_RULES_CANDIDATES.md` and `CODING_RULES_DEVIATIONS.md`); the universal-only boundary; the decision tree.
- **Atlas anatomy** (`method/03-atlas-anatomy.md`) — the root files of record (incl. `STATUS.md`), naming, the source orientation block, sources declared once and located per machine.
- **The SPEC lifecycle** (`method/04-spec-lifecycle.md`) — READY → IN PROGRESS → IN REVIEW → CLOSED → archived. CLOSED = verified in the code + a commit + the human says close. A SPEC = what + Plan (the route only); no state, no how, no code, no checkboxes, no findings — blockers, misconceptions, wrongly-posed parts go to `SPEC_NNNN_FINDINGS.md`. The how is decided live and its record is the code. Resume from `STATUS → Active` (Done / Next / Blocked).
- **The discipline** (`method/05-discipline.md`) — the cadence (git flow in its steps: branch from `develop`, back to `develop`, never `main`), the drift signals, pausing and resuming a SPEC; the working modes (paired / delegated — who approves the how); sessions are disposable — decisions written when taken, one fresh session per SPEC (or per large block of it), the Active block as the handoff; the human gates; one branch per SPEC; small deliverable specs; independent review in the code before close; clean baseline; commit-message hygiene; no archaeology (files of record are snapshots, never logs); environments and tooling (Atlas imposes none; follow the environment's rules, ask before installing).
- **The bootstrap recipe + Atlas `CLAUDE.md` template** (`method/06-bootstrap.md`).
- **Sharing an Atlas** (`method/07-sharing-an-atlas.md`) — git is how an Atlas is shared; never the symlinks.

## Step 2 — apply per the framework

- **Bootstrapping a new Atlas** → follow the recipe (`method/06-bootstrap.md`).
- **Modifying any Atlas root file of record** (`CLAUDE.md`, `STATUS.md`, `BACKLOG.md`, `SPEC_*.md`, `DRAFT_*.md`, `_archived/`, and the plugin files `CODING_RULES_CANDIDATES.md` / `CODING_RULES_DEVIATIONS.md`) → consult the stores model / anatomy (`method/02`, `method/03`) for what goes in each. `STATUS.md` = the living "where we are" (one section of what `atlas orient` prints and the `session-orient.sh` hook injects at session start); CLAUDE.md = static orientation/why. The lifecycle's transitions are `atlas spec`'s, the checkpoint's mechanics `atlas sync`'s.
- **Before writing any code**, place yourself in the cadence (`method/05-discipline.md`): is there a SPEC in `STATUS → Active`, and are you on its branch? Read its `mode:` (or the Atlas default) and act in your role. Check the other drift signals in `05` too. If one shows, say so once and follow the human's call. Follow the rules of the environment you run in; with none, ask before installing anything.
- **If the Atlas declares `coding-rules`** (`[plugins.coding-rules]` in `_settings/atlas.toml`), recall the rules from its source before writing code; candidate rules go to `CODING_RULES_CANDIDATES.md`, never straight to the source.
- **Deciding where a piece of knowledge belongs** → use the decision tree in the stores model (`method/02-stores-model.md`).

## Commands (the on-demand entry points)

Two user-global slash commands operate on an Atlas; both are thin wrappers that fetch and follow the canonical recipe/model in the Atlas framework (`atlas method`):

- **`/atlas-init`** — create an Atlas with the CLI (`atlas init`, or `atlas migrate` for an older one), add its sources with `atlas link`, declare the workbench with `atlas workbench add claude`, then write their orientation blocks with the human.
- **`/atlas-sync`** — checkpoint an existing Atlas: run `atlas sync` (doctor, lint, missing stamps, a closed SPEC out of Active, `atlas status`), reconcile the sources it reports with `atlas link` (and `atlas unlink`, with the human's approval, for a source that is gone), rewrite each Active block's Done / Next / Blocked, and update `CLAUDE.md` only if a standing fact changed.

Memory mechanism: a `SessionStart` hook (`session-orient.sh`) injects `atlas orient`'s output at start — the method's orientation, the coding rules in force, `atlas status` and `STATUS.md`; a `Stop` hook (`atlas-sync-reminder.sh`) nudges the agent to offer `/atlas-sync` when `STATUS.md` goes stale (throttled). There is no automatic write — checkpointing is deliberate.

## Naming

The concept is an **Atlas** (a map of the project's sources), NOT a "workspace" — "workspace" is overloaded. An Atlas is named after its folder (`atlas init` takes the folder's name).

## What is NOT in this skill

- The actual architecture text → in the Atlas framework doc (`atlas method`).
- The actual CLAUDE.md skeleton → in the framework (`method/06-bootstrap.md`).
- The actual bootstrap steps → in the framework (`method/06-bootstrap.md`).

This skill only exists to route Claude to the **framework doc** at the right moments. If the configured source is unreachable and no local clone is set with `atlas method --source`, surface the problem — do not improvise.
