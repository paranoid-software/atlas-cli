import argparse
import json
import tomllib
from pathlib import Path

from atlas_cli.atlasfiles import (
    ATLAS_TOML,
    CLAUDE_SETTINGS,
    VSCODE_SETTINGS,
    plan_json_file,
    read_atlas_file,
    read_atlas_toml,
    write_atlas_file,
)
from atlas_cli.settingscompletion import remove_directories, remove_scan_repository
from atlas_cli.sourcedeclaration import check_source_name, source_section_span


def register(subparsers) -> None:
    parser = subparsers.add_parser("unlink", help="drop a source from this Atlas")
    parser.add_argument("name")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    folder = Path.cwd()
    try:
        plan = _plan_unlink(folder, args.name)
    except ValueError as error:
        print(f"{error}; nothing was changed.")
        return 1
    if plan["target"] is not None:
        (folder / plan["name"]).unlink()
        print(f"removed {plan['name']} -> {plan['target']}")
    for path, content in plan["files"]:
        write_atlas_file(folder / path, content)
        print(f"updated {path}")
    print(f"Remove the orientation block of {plan['name']} from CLAUDE.md §1.")
    return 0


def _plan_unlink(folder: Path, name: str) -> dict:
    check_source_name(name)
    toml_path = folder / ATLAS_TOML
    if not toml_path.is_file():
        raise ValueError(f"This folder is not an Atlas (no {ATLAS_TOML})")
    text, declared = read_atlas_toml(toml_path)
    entries = {entry.name: entry for entry in folder.iterdir()}
    slot = entries.get(name)
    if slot is not None and not slot.is_symlink():
        raise ValueError(f"{name} in this Atlas is not a symlink")
    if slot is None and name not in declared:
        raise ValueError(f"{name} is not a source of this Atlas")
    target = slot.readlink() if slot is not None else None
    stale = _target_paths(folder, target) if target is not None else set()
    for other, entry in entries.items():
        if other != name and entry.is_symlink():
            stale -= _target_paths(folder, entry.readlink())
    files = []
    if name in declared:
        files.append((ATLAS_TOML, _drop_source(text, name)))
    for path, complete in (
        (VSCODE_SETTINGS, remove_scan_repository(name)),
        (CLAUDE_SETTINGS, remove_directories(stale)),
    ):
        content = _plan_settings(folder / path, complete)
        if content is not None:
            files.append((path, content))
    return {"name": name, "target": target, "files": files}


def _target_paths(folder: Path, written: Path) -> set[str]:
    paths = {str(written)}
    try:
        paths.add(str((folder / written).resolve()))
    except OSError:
        pass
    return paths


def _plan_settings(path: Path, complete) -> str | None:
    if not path.exists():
        return None
    _, content = plan_json_file(path, complete)
    if json.loads(content) == json.loads(read_atlas_file(path)):
        return None
    return content


def _drop_source(text: str, name: str) -> str:
    lines = text.splitlines(keepends=True)
    span = source_section_span(lines, name)
    if span is None:
        raise ValueError(f"Cannot remove {name} from {ATLAS_TOML} (its declaration has an unexpected shape)")
    start, end = span
    before = lines[:start]
    while before and before[-1].strip() == "":
        before.pop()
    after = lines[end:]
    while after and after[0].strip() == "":
        after.pop(0)
    if before and not before[-1].endswith("\n"):
        before[-1] += "\n"
    result = "".join(before) + ("\n" if before and after else "") + "".join(after)
    if not _source_is_gone(result, name):
        raise ValueError(f"Cannot remove {name} from {ATLAS_TOML} (its declaration has an unexpected shape)")
    return result


def _source_is_gone(text: str, name: str) -> bool:
    try:
        sources = tomllib.loads(text).get("sources", {})
    except tomllib.TOMLDecodeError:
        return False
    return isinstance(sources, dict) and name not in sources
