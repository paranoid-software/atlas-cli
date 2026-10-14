import argparse
import tomllib
from fnmatch import fnmatchcase
from pathlib import Path

from atlas_cli.atlasfiles import (
    ATLAS_TOML,
    CLAUDE_SETTINGS,
    GITIGNORE,
    VSCODE_SETTINGS,
    plan_json_file,
    read_atlas_file,
    render_template,
    write_atlas_file,
)
from atlas_cli.plugindeclaration import KNOWN_PLUGINS, append_plugin
from atlas_cli.settingscompletion import (
    add_directory,
    add_scan_repository,
    complete_claude_settings,
    complete_vscode_settings,
)
from atlas_cli.settingscompletion import scan_entries
from atlas_cli.sourcedeclaration import append_source, nested_repos, read_origin

V0_MARKERS = ("CLAUDE.md", "STATUS.md")
COCO_CANDIDATES = "COCO_CANDIDATES.md"
COCO_DEVIATIONS = "DEVIATIONS.md"
CODING_RULES = "coding-rules"
CODING_RULES_SOURCE = "mcp:coco"
PLANNING_FILES = ("STATUS.md", "BACKLOG.md", "SPEC_*.md", "DRAFT_*.md")


def register(subparsers) -> None:
    parser = subparsers.add_parser("migrate", help="bring an Atlas created before _settings/ to the current model")
    parser.add_argument("--apply", action="store_true", help="apply the plan instead of only printing it")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    folder = Path.cwd()
    try:
        model = _detect_model(folder)
        if model is None:
            print("This folder is not an Atlas.")
            return 1
        if model == 1:
            print("This Atlas is up to date (model v1).")
            return 0
        plan = _plan_migration(folder)
    except (ValueError, OSError) as error:
        print(f"{error}; nothing was changed.")
        return 1
    if not args.apply:
        for planned, _ in plan["steps"]:
            print(planned)
        print("Run `atlas migrate --apply` to apply this plan.")
        return 0
    for path, content in plan["writes"].items():
        write_atlas_file(folder / path, content)
    for path in plan["removals"]:
        (folder / path).unlink()
    for _, done in plan["steps"]:
        print(done)
    return 0


def _detect_model(folder: Path) -> int | None:
    toml_path = folder / ATLAS_TOML
    if toml_path.is_file():
        try:
            version = tomllib.loads(_read_file(toml_path)).get("version")
        except tomllib.TOMLDecodeError as error:
            raise ValueError(f"Cannot read {ATLAS_TOML} ({error})") from error
        if version != 1:
            raise ValueError(f"{ATLAS_TOML} declares version {version!r}, a model atlas migrate does not know")
        return 1
    if any((folder / marker).exists() for marker in V0_MARKERS):
        return 0
    return None


def _plan_migration(folder: Path) -> dict:
    sources = sorted((entry for entry in folder.iterdir() if entry.is_symlink()), key=lambda entry: entry.name)
    targets = {entry.name: entry.resolve() for entry in sources}
    steps: list[tuple[str, str]] = [(f"create {ATLAS_TOML}", f"created {ATLAS_TOML}")]
    writes: dict[str, str] = {}
    removals: list[str] = []
    toml_text = render_template("atlas.toml")
    scanned: list[str] = []
    for name, target in targets.items():
        remote = read_origin(target)
        repos = nested_repos(target)
        toml_text = append_source(toml_text, name, remote, repos)
        label = _describe_source(target, remote, repos)
        steps.append((f"declare {name} ({label})", f"declared {name} ({label})"))
        scanned.extend(scan_entries(name, repos))
    _, writes[VSCODE_SETTINGS] = plan_json_file(folder / VSCODE_SETTINGS, _complete_vscode(scanned))
    steps.append((f"complete {VSCODE_SETTINGS}", f"completed {VSCODE_SETTINGS}"))
    directories = [str(target) for target in targets.values()]
    _, writes[CLAUDE_SETTINGS] = plan_json_file(folder / CLAUDE_SETTINGS, _complete_claude(directories))
    steps.append((f"complete {CLAUDE_SETTINGS}", f"completed {CLAUDE_SETTINGS}"))
    if (folder / GITIGNORE).exists():
        steps.append((f"keep {GITIGNORE}", f"kept {GITIGNORE}"))
    else:
        writes[GITIGNORE] = render_template("gitignore")
        steps.append((f"create {GITIGNORE}", f"created {GITIGNORE}"))
    if (folder / COCO_CANDIDATES).is_file():
        toml_text = append_plugin(toml_text, CODING_RULES, CODING_RULES_SOURCE)
        declared = f"{CODING_RULES} ({CODING_RULES_SOURCE})"
        steps.append((f"declare {declared}", f"declared {declared}"))
        for old, new in zip((COCO_CANDIDATES, COCO_DEVIATIONS), KNOWN_PLUGINS[CODING_RULES]):
            steps.extend(_plan_plugin_file(folder, old, new, writes, removals))
    elif (folder / COCO_DEVIATIONS).is_file():
        note = f"note: {COCO_DEVIATIONS} needs a coding-rules source (atlas plugin add {CODING_RULES} <source>)"
        steps.append((note, note))
    writes[ATLAS_TOML] = toml_text
    for name, target in targets.items():
        found = _list_planning_files(target)
        if found:
            note = f"note: {name} holds planning files: {', '.join(found)}"
            steps.append((note, note))
    return {"steps": steps, "writes": writes, "removals": removals}


def _describe_source(target: Path, remote: str | None, repos: dict[str, str | None]) -> str:
    if remote is not None:
        return remote
    if not target.exists():
        return "broken"
    if (target / ".git").exists():
        return "no remote"
    if repos:
        return f"folder of {len(repos)} repos: {', '.join(sorted(repos))}"
    return "not git"


def _complete_vscode(names: list[str]):
    def complete(settings: dict) -> dict:
        complete_vscode_settings(settings)
        for name in names:
            add_scan_repository(name)(settings)
        return settings

    return complete


def _complete_claude(directories: list[str]):
    def complete(settings: dict) -> dict:
        complete_claude_settings(settings)
        for directory in directories:
            add_directory(directory)(settings)
        return settings

    return complete


def _plan_plugin_file(folder: Path, old: str, new: str, writes: dict[str, str], removals: list[str]) -> list[tuple[str, str]]:
    if (folder / new).exists():
        steps = [(f"keep {new}", f"kept {new}")]
        if (folder / old).exists():
            note = f"note: {old} left in place because {new} already exists"
            steps.append((note, note))
        return steps
    if (folder / old).is_file():
        writes[new] = _read_file(folder / old)
        removals.append(old)
        return [(f"rename {old} -> {new}", f"renamed {old} -> {new}")]
    writes[new] = render_template(new)
    return [(f"create {new}", f"created {new}")]


def _list_planning_files(target: Path) -> list[str]:
    if not target.is_dir():
        return []
    return sorted(
        entry.name
        for entry in target.iterdir()
        if entry.is_file() and any(fnmatchcase(entry.name, pattern) for pattern in PLANNING_FILES)
    )


def _read_file(path: Path) -> str:
    try:
        return read_atlas_file(path)
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"Cannot read {path.name} ({error})") from error
