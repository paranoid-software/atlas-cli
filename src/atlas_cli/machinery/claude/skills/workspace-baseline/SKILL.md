---
name: workspace-baseline
description: Use when bootstrapping a new Atlas (symlink-aggregator project root), editing CLAUDE.md / STATUS.md / BACKLOG.md / SPEC_*.md / DRAFT_*.md / _archived/ / the coding-rules plugin files, deciding where a piece of knowledge belongs across the stores, or auditing the user-global setup. The canonical Atlas framework (architecture + bootstrap recipe) lives in the Atlas framework doc, fetched via `~/.claude/atlas-fetch.sh`. This skill is the entry point — fetch the framework, then act.
---

# workspace-baseline

The canonical Atlas framework (architecture + bootstrap recipe) lives in the **Atlas framework doc**, fetched via `~/.claude/atlas-fetch.sh` from the source configured in `~/.claude/atlas-source` — the official site `https://atlas.paranoid.software`, or `http://localhost:8088` for local dev, or a local clone. This skill is the entry point: fetch the framework, then act.

## Step 1 — load the framework definition

```
bash ~/.claude/atlas-fetch.sh llms.txt          # the index — start here
bash ~/.claude/atlas-fetch.sh llms-full.txt     # the whole framework in one file
bash ~/.claude/atlas-fetch.sh method/06-bootstrap.md   # a specific piece
```

`atlas-fetch.sh` resolves the single source in `~/.claude/atlas-source`: a URL → `curl`, a local path → `cat`. If it fails, the source is unreachable / misconfigured — surface that, don't improvise the framework from memory.

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
- **Modifying any Atlas root file of record** (`CLAUDE.md`, `STATUS.md`, `BACKLOG.md`, `SPEC_*.md`, `DRAFT_*.md`, `_archived/`, and the plugin files `CODING_RULES_CANDIDATES.md` / `CODING_RULES_DEVIATIONS.md`) → consult the stores model / anatomy (`method/02`, `method/03`) for what goes in each. `STATUS.md` = the living "where we are", injected at session start by the `session-orient.sh` hook; CLAUDE.md = static orientation/why.
- **Before writing any code**, place yourself in the cadence (`method/05-discipline.md`): is there a SPEC in `STATUS → Active`, and are you on its branch? Read its `mode:` (or the Atlas default) and act in your role. Check the other drift signals in `05` too. If one shows, say so once and follow the human's call. Follow the rules of the environment you run in; with none, ask before installing anything.
- **If the Atlas declares `coding-rules`** (`[plugins.coding-rules]` in `_settings/atlas.toml`), recall the rules from its source before writing code; candidate rules go to `CODING_RULES_CANDIDATES.md`, never straight to the source.
- **Deciding where a piece of knowledge belongs** → use the decision tree in the stores model (`method/02-stores-model.md`).

## Commands (the on-demand entry points)

Two user-global slash commands operate on an Atlas; both are thin wrappers that fetch and follow the canonical recipe/model in the Atlas framework (`atlas-fetch.sh`):

- **`/atlas-init`** — create an Atlas with the CLI (`atlas init`, or `atlas migrate` for an older one), add its sources with `atlas link`, then write their orientation blocks with the human.
- **`/atlas-sync`** — checkpoint an existing Atlas: reconcile its sources with `atlas doctor` / `atlas link`, refresh `STATUS.md` starting from `atlas status` (Active blocks Done / Next / Blocked; closed SPECs to Recently closed), lint SPECs for contamination, and update `CLAUDE.md` only if a standing fact changed.

Memory mechanism: a `SessionStart` hook (`session-orient.sh`) injects `STATUS.md` at start; a `Stop` hook (`atlas-sync-reminder.sh`) nudges the agent to offer `/atlas-sync` when `STATUS.md` goes stale (throttled). There is no automatic write — checkpointing is deliberate.

## Naming

The concept is an **Atlas** (a map of the project's sources), NOT a "workspace" — "workspace" is overloaded. An Atlas is named after its folder (`atlas init` takes the folder's name).

## What is NOT in this skill

- The actual architecture text → in the Atlas framework doc (`atlas-fetch.sh`).
- The actual CLAUDE.md skeleton → in the framework (`method/06-bootstrap.md`).
- The actual bootstrap steps → in the framework (`method/06-bootstrap.md`).

This skill only exists to route Claude to the **framework doc** at the right moments. If the configured source is unreachable and no local clone is set in `~/.claude/atlas-source`, surface the problem — do not improvise.
