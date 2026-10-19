"""`atlas workbench`: the workbenches this Atlas is worked with, declared once, their files per machine."""

import argparse
from pathlib import Path

from atlas_cli.atlasfiles import ATLAS_TOML, read_atlas_toml, write_atlas_file
from atlas_cli.sourcestate import atlas_entries
from atlas_cli.workbenches import (
    KNOWN_WORKBENCHES,
    append_workbench,
    declared_workbenches,
    drop_workbench,
    judge,
    rebuild,
    workbench_file,
)


def register(subparsers) -> None:
    parser = subparsers.add_parser("workbench", help="declare the workbenches this Atlas is worked with")
    actions = parser.add_subparsers(dest="action", metavar="<action>", required=True)
    add = actions.add_parser("add", help="declare a workbench and write its files from the declared sources")
    add.add_argument("name", help=f"the workbench ({', '.join(KNOWN_WORKBENCHES)})")
    add.set_defaults(handler=run_add)
    drop = actions.add_parser("drop", help="remove a workbench's declaration; its files stay")
    drop.add_argument("name", help=f"the workbench ({', '.join(KNOWN_WORKBENCHES)})")
    drop.set_defaults(handler=run_drop)
    listing = actions.add_parser("list", help="print the declared workbenches and the state of their files")
    listing.set_defaults(handler=run_list)


def run_add(args: argparse.Namespace) -> int:
    folder = Path.cwd()
    try:
        text, declared, workbenches = _read(folder)
        name = _known(args.name)
        action, content = rebuild(folder, name, declared, atlas_entries(folder))
    except ValueError as error:
        print(f"{error}; nothing was changed.")
        return 1
    if name not in workbenches:
        write_atlas_file(folder / ATLAS_TOML, append_workbench(text, name))
        print(f"declared {name} in {ATLAS_TOML}")
    else:
        print(f"{name} is already declared in {ATLAS_TOML}")
    write_atlas_file(folder / workbench_file(name), content)
    print(f"{action} {workbench_file(name)}")
    return 0


def run_drop(args: argparse.Namespace) -> int:
    folder = Path.cwd()
    try:
        text, _declared, workbenches = _read(folder)
        name = _known(args.name)
        if name not in workbenches:
            raise ValueError(f"{name} is not declared in {ATLAS_TOML}")
        dropped = drop_workbench(text, name)
    except ValueError as error:
        print(f"{error}; nothing was changed.")
        return 1
    write_atlas_file(folder / ATLAS_TOML, dropped)
    print(f"dropped {name} from {ATLAS_TOML}")
    print(f"kept {workbench_file(name)}; remove it by hand if {name} is gone for good")
    return 0


def run_list(args: argparse.Namespace) -> int:
    folder = Path.cwd()
    try:
        _text, declared, workbenches = _read(folder)
    except ValueError as error:
        print(f"{error}.")
        return 1
    if not workbenches:
        print(f"No workbench declared; `atlas workbench add <name>` ({', '.join(KNOWN_WORKBENCHES)}).")
        return 0
    entries = atlas_entries(folder)
    for name in workbenches:
        state = judge(folder, name, declared, entries) if name in KNOWN_WORKBENCHES else "unknown"
        print(f"{name}: {state} ({workbench_file(name) if name in KNOWN_WORKBENCHES else 'no files this CLI knows'})")
    return 0


def _read(folder: Path) -> tuple[str, dict, list[str]]:
    toml_path = folder / ATLAS_TOML
    if not toml_path.is_file():
        raise ValueError(f"This folder is not an Atlas (no {ATLAS_TOML})")
    text, declared = read_atlas_toml(toml_path)
    return text, declared, declared_workbenches(text)


def _known(name: str) -> str:
    if name not in KNOWN_WORKBENCHES:
        raise ValueError(f"Unknown workbench '{name}' (known: {', '.join(KNOWN_WORKBENCHES)})")
    return name
