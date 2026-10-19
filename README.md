# atlas-cli

The [Atlas](https://atlas.paranoid.software) method made executable: create an Atlas and keep
it in order while several people and agents work in it.

> **What Atlas is:** a spec-driven way to keep the context of real software projects — one
> folder per project, its sources linked by symlink, so any agent or editor opens it cold and
> knows what it is, where each source lives, where the work stands and how it gets closed. This
> CLI is its anchor: `atlas orient`, `atlas spec`, `atlas sync` and `atlas handover` carry the
> whole method, with any workbench or none.

## 1. Prerequisites (macOS + Windows)

> **Windows users:** install the tools with `winget` in PowerShell. If you install a
> workbench's hooks (step 3), run that workbench from **Git Bash** (installed with Git for
> Windows): the hooks are bash scripts.

| Tool | What it's for | macOS | Windows (PowerShell, then reopen Git Bash) |
|---|---|---|---|
| **Git** (+ Git Bash) | Sources and shared Atlases are git repos; on Windows, Git Bash runs a workbench's hooks. | `brew install git` | `winget install Git.Git` |
| **uv** | Installs the `atlas` CLI with its own Python. | `brew install uv` | `winget install astral-sh.uv` |
| **jq** *(only with a workbench's hooks)* | The hooks read and write JSON with it. Without it, they stay silent and the coding-rules gate lets every edit through. | `brew install jq` | `winget install jqlang.jq` |

**Windows only — allow symlinks:** Settings → *Privacy & security* → *For developers* → turn
**Developer Mode ON**, so `atlas link` can create symlinks without admin rights.

Check:

```bash
git --version && uv --version
```

## 2. Install

```bash
uv tool install paranoid-atlas-cli
```

The command is `atlas`; `atlas --version` confirms it. If the shell can't find it, run
`uv tool update-shell` and open a new terminal. Upgrade later with
`uv tool install --reinstall paranoid-atlas-cli`.

## 3. Workbenches

The CLI is the whole method: any editor or agent that opens the Atlas and has a terminal works
with it — `atlas orient` to start, `atlas spec` and `atlas sync` to move the work,
`atlas handover` to delegate. A workbench may have **machinery** — hooks, commands, skills —
that wraps those commands so discipline doesn't depend on the agent remembering. It is
optional, installed per workbench with `atlas setup <workbench>`, and never does what the CLI
does.

| Workbench | Setup | What it gets |
|---|---|---|
| **Claude Code** | `atlas setup claude` | hooks, `/atlas-init`, `/atlas-sync`, the `workspace-baseline` skill |
| Cursor | reads Claude Code's `~/.claude` (below) | the same, through that folder |
| others | the CLI alone, until their `atlas setup <workbench>` exists | `atlas orient`, `spec`, `sync`, `handover` |

### Claude Code

```bash
atlas setup claude
```

It installs the hooks, the `/atlas-init` and `/atlas-sync` commands and the `workspace-baseline`
skill into `~/.claude` (or `CLAUDE_CONFIG_DIR` when set), wires the hooks into `settings.json`
after any hook already there, without touching anything else. Run it again after every
upgrade; it only changes what differs. An `atlas-source` file from an older setup is moved into
the CLI's framework source once (below) and then ignored.

With `CLAUDE_CONFIG_DIR` set, every `~/.claude/…` path in the machinery lives under that folder
instead.

**Cursor** reads Claude Code's configuration from `~/.claude`: once this step is done, it gets
the hooks, the commands and the skill — don't copy them into `~/.cursor/`. The one thing to add
on Cursor's side is the MCP server behind an Atlas's `coding-rules` plugin, if it has one, in
`~/.cursor/mcp.json`.

**The coding-rules gate.** In an Atlas that declares the `coding-rules` plugin, a hook blocks
the first code edit of each Claude Code session until the declared source has been consulted.
If the source can't be reached, start Claude Code with `ATLAS_CODING_RULES_GATE=off` to let
edits through.

## 4. Use it

- **Create an Atlas:** in a new folder, `atlas init` (its orientation file is `AGENTS.md`, which
  Codex, Cursor, OpenCode and others read on their own), then `atlas link <name> <path>`
  for each source and `atlas doctor` to check them — or `/atlas-init` in Claude Code, which does the
  same with you, the workbench declaration below included.
- **Declare its workbenches:** `atlas workbench add claude` writes `.claude/settings.local.json`,
  the sources' real paths as readable directories for Claude Code, and `CLAUDE.md` as the one
  line `@AGENTS.md`, so Claude Code reads the orientation file (that line is versioned, so a
  clone reads it at once; Claude-specific lines may follow it). An Atlas whose orientation
  file is still `CLAUDE.md` is renamed by `atlas migrate`. The declaration is the
  Atlas's and travels with it; the settings file is per machine, never versioned, kept current by
  `atlas link` and `atlas unlink`, and rebuilt with the same command on another machine.
  `atlas doctor` reports a declared workbench whose file is missing or stale;
  `atlas workbench drop` undeclares one. (`.vscode/settings.json`, the editor's git settings
  with relative paths, is the Atlas's own file: `atlas init` creates it, every `atlas link`
  keeps it, and it is versioned with the Atlas, whatever workbench you use.)
- **Join a shared Atlas:** clone it, run `atlas doctor` inside it and follow what it says.
- **Older Atlas:** `atlas migrate` shows the plan to bring it to the current model;
  `atlas migrate --apply` applies it.
- **A SPEC's life:** `atlas spec new <SLUG>` creates it and indexes it in the backlog;
  `atlas spec start <name>` stamps it, enters it in STATUS → Active and prints the branch
  commands; `atlas spec pause|resume|review <name>` keep its Active block; `atlas spec close
  <name>` stamps it, archives it with its findings and lists it as recently closed, refusing
  while its branch is unmerged; `atlas spec lint` reports what a SPEC carries that it should
  not. The Done / Next / Blocked lines are yours or the agent's.
- **Delegating a step:** `atlas handover <name> --step N` prints the brief for a workbench: the
  SPEC, the step, where it stands, this Atlas's conventions, the coding rules (from the file the
  Atlas declares, or `--rules <file>` when the source is an MCP server) and the method's standing
  clauses; `--out <file>` writes it. The principal adds the files to imitate.
- **The framework itself:** `atlas method` prints its index, `atlas method <page>` one page
  (`04`, `04-spec-lifecycle` or `method/04-spec-lifecycle.md`), `atlas method --full` all of it.
  It reads the official site unless `atlas method --source <url|path>` set another, once: a
  local copy of the site (`http://localhost:8088`) or a clone of the framework repo, which
  works offline. The setting lives in the CLI's own folder (`~/.config/atlas`, or
  `ATLAS_CONFIG_DIR`), never in an Atlas.
- **Day to day:** `atlas status` says where things stand; `atlas sync` does the checkpoint's
  mechanics (doctor, lint, missing stamps, a closed SPEC out of Active; `--check` writes nothing);
  `atlas orient` prints what an agent
  needs at session start — stores, cadence, coding rules, state — and is the entry point for
  any workbench or editor (Claude Code's session hook just calls it); the checkpoint is
  `atlas sync` plus the Done / Next / Blocked lines (`/atlas-sync` in Claude Code does both);
  `atlas unlink <name>` drops a source the Atlas no longer uses; `atlas ui` opens a local,
  read-only page on the Atlas — doctor made plain, the SPECs with search, stats, rules and
  machinery.

How an Atlas works — its files, SPECs, cadence and sharing — is the method:
[creating an Atlas](https://atlas.paranoid.software/method/06-bootstrap) and
[sharing one](https://atlas.paranoid.software/method/07-sharing-an-atlas). `atlas --help` lists
every command.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `atlas: command not found` | `uv tool update-shell`, then a new terminal. |
| `The framework source … could not be reached` | Serve it locally or clone the repo, then `atlas method --source <url|path>`. |
| `jq: command not found` | Install jq (step 1); on Windows, reopen Git Bash afterwards. |
| Hooks do nothing on Windows | Not in Git Bash, or Git for Windows isn't installed (step 1). |
| `atlas link` can't create the symlink (Windows) | Turn Developer Mode on (step 1). |
| The site doesn't answer | Serve the framework locally, or clone its repo, and `atlas method --source` it (step 4). |
| Sources don't show in the editor's Source Control | Check `.vscode/settings.json` has `git.autoRepositoryDetection: true` (Cursor defaults to `openEditors`, which ignores `git.scanRepositories`) and reload the window. To see what the editor does, set the Git log level to Trace (`Developer: Set Log Level`), reload, and read the Git output log: its `doInitialScan` line prints the effective `autoRepositoryDetection`. |

## Develop

```bash
uv sync
uv run atlas --version
uv run pytest
```

## Release

Bump `version` in `pyproject.toml`, commit, then push a matching tag (`v0.1.1` for `0.1.1`):
the `Publish paranoid-atlas-cli to PyPI` workflow builds and publishes it. A tag that doesn't match the
version fails the workflow.
