import argparse
from pathlib import Path

from atlas_cli.atlasfiles import (
    ATLAS_TOML,
    CLAUDE_SETTINGS,
    VSCODE_SETTINGS,
    plan_json_file,
    read_atlas_toml,
    write_atlas_file,
)
from atlas_cli.settingscompletion import add_directory, add_scan_repository
from atlas_cli.sourcedeclaration import (
    append_source,
    check_source_name,
    read_origin,
    render_source_section,
    source_section_span,
)


def register(subparsers) -> None:
    parser = subparsers.add_parser("link", help="add or rebind a source in this Atlas")
    parser.add_argument("name")
    parser.add_argument("path")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    folder = Path.cwd()
    try:
        plan = _plan_link(folder, args.name, Path(args.path))
    except ValueError as error:
        print(f"{error}; nothing was changed.")
        return 1
    for path, (action, content) in plan["files"]:
        write_atlas_file(folder / path, content)
        print(f"{action} {path}")
    link = folder / plan["name"]
    if link.is_symlink():
        link.unlink()
    link.symlink_to(plan["target"], target_is_directory=plan["target"].is_dir())
    print(f"{plan['link']} {plan['name']} -> {plan['target']}")
    return 0


def _plan_link(folder: Path, name: str, given: Path) -> dict:
    check_source_name(name)
    toml_path = folder / ATLAS_TOML
    if not toml_path.is_file():
        raise ValueError(f"This folder is not an Atlas (no {ATLAS_TOML})")
    if not given.expanduser().exists():
        raise ValueError(f"{given} does not exist")
    target = given.expanduser().resolve()
    text, declared = read_atlas_toml(toml_path)
    remote = read_origin(target)
    slot = folder / name
    previous = None
    if name in declared:
        if slot.exists() and not slot.is_symlink():
            raise ValueError(f"{name} already exists in this Atlas")
        if slot.is_symlink():
            previous = slot.readlink()
        toml_text = _rebind_source(text, name, remote)
        link_action = "rebound" if previous is not None else "created"
    else:
        if slot.exists() and not slot.is_symlink():
            raise ValueError(f"{name} already exists in this Atlas")
        if slot.is_symlink():
            previous = slot.readlink()
            link_action = "rebound"
        else:
            link_action = "created"
        toml_text = append_source(text, name, remote)
    files = [(ATLAS_TOML, ("updated", toml_text))]
    files.append((VSCODE_SETTINGS, plan_json_file(folder / VSCODE_SETTINGS, add_scan_repository(name))))
    files.append((CLAUDE_SETTINGS, plan_json_file(folder / CLAUDE_SETTINGS, add_directory(str(target), previous))))
    return {"name": name, "target": target, "link": link_action, "files": files}


def _rebind_source(text: str, name: str, remote: str | None) -> str:
    lines = text.splitlines(keepends=True)
    span = source_section_span(lines, name)
    if span is None:
        raise ValueError(f"Cannot update {name} in {ATLAS_TOML}")
    start, end = span
    return "".join(lines[:start]) + render_source_section(name, remote) + "".join(lines[end:])
