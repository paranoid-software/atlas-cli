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
from atlas_cli.settingscompletion import add_directory, scan_entries, set_scan_repositories
from atlas_cli.sourcedeclaration import (
    append_source,
    check_source_name,
    nested_repos,
    read_origin,
    render_source_section,
    source_section_span,
    stray_subsections,
)
from atlas_cli.sourcestate import atlas_entries, case_twin


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
    if plan["link"] == "rebound":
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
    entries = atlas_entries(folder)
    twin = case_twin([*declared, *entries], name)
    if twin is not None:
        raise ValueError(f"{name} and {twin} are the same name on a case-insensitive disk")
    remote = read_origin(target)
    repos = nested_repos(target)
    slot = entries.get(name)
    if slot is not None and not slot.is_symlink():
        raise ValueError(f"{name} already exists in this Atlas")
    previous = slot.readlink() if slot is not None else None
    link_action = "rebound" if previous is not None else "created"
    if name in declared:
        toml_text = _rebind_source(text, name, remote, repos)
    else:
        toml_text = append_source(text, name, remote, repos)
    files = [(ATLAS_TOML, ("updated", toml_text))]
    scan = set_scan_repositories(name, scan_entries(name, repos))
    files.append((VSCODE_SETTINGS, plan_json_file(folder / VSCODE_SETTINGS, scan)))
    files.append((CLAUDE_SETTINGS, plan_json_file(folder / CLAUDE_SETTINGS, add_directory(str(target), previous))))
    return {"name": name, "target": target, "link": link_action, "files": files}


def _rebind_source(text: str, name: str, remote: str | None, repos: dict[str, str | None]) -> str:
    lines = text.splitlines(keepends=True)
    span = source_section_span(lines, name)
    if span is None:
        raise ValueError(f"Cannot update {name} in {ATLAS_TOML}")
    if stray_subsections(lines, name, span):
        raise ValueError(f"Cannot update {name} in {ATLAS_TOML} (its declaration has an unexpected shape)")
    start, end = span
    return "".join(lines[:start]) + render_source_section(name, remote, repos) + "".join(lines[end:])
