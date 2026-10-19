import re
import sys
import tomllib
from pathlib import Path

from atlas_cli.atlasfiles import ATLAS_TOML, read_atlas_file
from atlas_cli.commands.status import status_lines

CANDIDATES = "CODING_RULES_CANDIDATES.md"
DEVIATIONS = "CODING_RULES_DEVIATIONS.md"

ORIENTATION = """SESSION START — Orient before doing substantive work: read AGENTS.md in full (the orientation file; CLAUDE.md while an Atlas has not renamed it); skim any SPEC_*.md / BACKLOG.md at the workspace root; and consult the Atlas framework for the method/conventions (run `atlas method` for the index, then `atlas method <page>` for the piece you need). Do NOT start from zero or make the user re-explain the workspace, repos, or what the project is.

STORES — each kind of knowledge has one home. AGENTS.md at the Atlas root is this project's orientation (what each source is and how it is worked on) and the conventions of this Atlas alone (its §5); it never holds universal rules. The coding-rules source the Atlas declares holds the universal rules, true for any project; it never holds this Atlas's conventions. CODING_RULES_CANDIDATES.md holds rules this Atlas already applies while they wait for promotion to the source: follow them here exactly as you follow the source's. CODING_RULES_DEVIATIONS.md holds the deliberate divergences from the source in force here. A source may carry its own rule files (CLAUDE.md, .claude/, AGENTS.md, .cursorrules): atlas doctor lists them as a notice. Read them with caution, as that source's context, never as the Atlas's rules; where they contradict the Atlas or the coding rules, the Atlas and the coding rules prevail, and the contradiction stops the work and goes to the human.

CADENCE — follow the Atlas cadence (method/05-discipline.md): bounded SPEC -> its branch from develop -> step by step, the how approved per the SPEC's working mode -> findings beside the SPEC -> independent review -> the human commits and closes. If you see a drift signal (code requested with no SPEC in STATUS Active; two SPECs in progress and not paused in one repo; work outside the SPEC branch or on main; in paired mode, a step coded without its how approved; a close without independent review or commit), say so ONCE, then follow the human's call. The human runs every git command; give them the exact command. Sessions are disposable: write a decision where it belongs (AGENTS.md, the SPEC, its findings or the backlog) the moment it is taken — except the how, whose record is the code; one fresh session per SPEC (or per large block of it), and before stopping rewrite its Active block as the handoff. WORKING MODE — read the active SPEC's mode: line (or the Atlas default in AGENTS.md). paired: propose the how of each step and wait for the human's approval. delegated: as the workbench, execute end to end and stop only on a real blocker or a decision the SPEC doesn't cover; as the principal, hand over a precise, self-contained prompt and review the result. ENVIRONMENT — look at where you stand and what is available, and follow that environment's own rules; where there are none, propose carefully and ask the human before installing or changing anything — never install tooling to match a prompt."""

CODING_RULES = (
    "CODING RULES — this Atlas declares the coding-rules plugin with source \"{source}\" (an mcp:<server> source is queried through that MCP server's tools; a file:<path> source is read from the Atlas). Before the first step of a SPEC, recall the rules for its area from it, say which apply (by id when the source has ids) and follow them; a hand-over carries them to the workbench. Where the workbench has a gate (Claude Code does), the first code edit of a session is blocked until the source has been consulted. A candidate rule goes to CODING_RULES_CANDIDATES.md, is in force in this Atlas from that moment, and is promoted to the source only in a dedicated session with the human's approval — never written to the source mid-task. A deliberate divergence goes to CODING_RULES_DEVIATIONS.md."
)

UNREADABLE_SOURCE = "(unreadable — check [plugins.coding-rules] in _settings/atlas.toml)"
_PLUGIN_HEADER = re.compile(r'^\s*\[\s*plugins\."?coding-rules"?\s*\]', re.M)


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "orient", help="print what an agent needs at session start: stores, cadence, rules, state"
    )
    parser.set_defaults(handler=run)


def run(args) -> int:
    code, text = orient(Path.cwd())
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # the files' text, whatever the console's codec
    print(text)
    return code


def orient(folder: Path) -> tuple[int, str]:
    """The session-start orientation, for any workbench or a human in a terminal.

    The text is the method's; this Atlas's part is its coding-rules source, the candidates and
    deviations in force, `atlas status` and STATUS.md.
    """
    current = (folder / ATLAS_TOML).is_file()
    if not current and not (folder / "STATUS.md").is_file() and not (folder / "CLAUDE.md").is_file():
        return 1, f"This folder is not an Atlas (no {ATLAS_TOML})."
    parts: list[str] = []
    if not current:
        parts.append(f"This is an Atlas of the older model (no {ATLAS_TOML}): run `atlas migrate` to bring it up to date.")
    parts.append(ORIENTATION)
    if current:
        parts.extend(_coding_rules(folder))
        _code, lines = status_lines(folder)
        parts.append("=== atlas status — where the Atlas and its sources stand ===\n" + "\n".join(lines))
    if (folder / "STATUS.md").is_file():
        parts.append("=== STATUS.md — current state & next steps (read this first) ===\n" + _read(folder / "STATUS.md"))
    return (0 if current else 1), "\n\n".join(parts)


def _coding_rules(folder: Path) -> list[str]:
    source = _rules_source(folder)
    if source is None:
        return []
    parts = [CODING_RULES.format(source=source)]
    if (folder / CANDIDATES).is_file() and _has_open_candidates(_read(folder / CANDIDATES)):
        parts.append(f"=== {CANDIDATES} — candidate rules in force here ===\n" + _read(folder / CANDIDATES))
    if (folder / DEVIATIONS).is_file():
        parts.append(f"=== {DEVIATIONS} — deviations in force ===\n" + _read(folder / DEVIATIONS))
    return parts


def _rules_source(folder: Path) -> str | None:
    """The declared source, the unreadable marker when the plugin is declared without one, None without the plugin."""
    try:
        text = read_atlas_file(folder / ATLAS_TOML)
    except OSError:
        return None
    try:
        plugins = tomllib.loads(text).get("plugins", {})
    except tomllib.TOMLDecodeError:
        # The gate hook finds the section by its header: say the plugin is declared, as it does.
        return UNREADABLE_SOURCE if _PLUGIN_HEADER.search(text) else None
    plugin = plugins.get("coding-rules") if isinstance(plugins, dict) else None
    if not isinstance(plugin, dict):
        return None
    source = plugin.get("source")
    return source if isinstance(source, str) and source else UNREADABLE_SOURCE


def _has_open_candidates(text: str) -> bool:
    inside = False
    for line in text.splitlines():
        if line.strip() == "## Open":
            inside = True
            continue
        if inside and line.startswith("## "):
            return False
        if inside and line.strip() and not (line.strip().startswith("_(") and line.strip().endswith(")_")):
            return True
    return False


def _read(path: Path) -> str:
    return read_atlas_file(path).rstrip("\n")
