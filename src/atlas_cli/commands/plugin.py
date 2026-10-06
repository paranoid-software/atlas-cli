import argparse
import re
import tomllib
from pathlib import Path

from atlas_cli.atlasfiles import (
    ATLAS_TOML,
    read_atlas_file,
    render_template,
    write_atlas_file,
)
from atlas_cli.plugindeclaration import KNOWN_PLUGINS, append_plugin

_SOURCE = re.compile(r"mcp:[A-Za-z0-9_.-]+|file:[^/\\].*\.md")


def register(subparsers) -> None:
    parser = subparsers.add_parser("plugin", help="enable a plugin in this Atlas")
    actions = parser.add_subparsers(dest="action", metavar="<action>", required=True)
    add = actions.add_parser("add", help="declare a plugin and create its files")
    add.add_argument("name", help=f"the plugin ({', '.join(KNOWN_PLUGINS)})")
    add.add_argument("source", help="where its content comes from: mcp:<server> or file:<path to a .md in the Atlas>")
    add.set_defaults(handler=run_add)


def run_add(args: argparse.Namespace) -> int:
    folder = Path.cwd()
    try:
        toml_text = _plan_declaration(folder, args.name, args.source)
    except ValueError as error:
        print(f"{error}; nothing was changed.")
        return 1
    write_atlas_file(folder / ATLAS_TOML, toml_text)
    print(f"declared {args.name} ({args.source}) in {ATLAS_TOML}")
    for file_name in KNOWN_PLUGINS[args.name]:
        target = folder / file_name
        if target.exists():
            print(f"kept {file_name}")
            continue
        write_atlas_file(target, render_template(file_name))
        print(f"created {file_name}")
    return 0


def _plan_declaration(folder: Path, name: str, source: str) -> str:
    toml_path = folder / ATLAS_TOML
    if not toml_path.is_file():
        raise ValueError(f"This folder is not an Atlas (no {ATLAS_TOML})")
    if name not in KNOWN_PLUGINS:
        raise ValueError(f"Unknown plugin '{name}' (known: {', '.join(KNOWN_PLUGINS)})")
    if not _SOURCE.fullmatch(source) or ".." in Path(source.removeprefix("file:")).parts:
        raise ValueError(f"'{source}' is not a source (use mcp:<server> or file:<path to a .md in the Atlas>)")
    text = read_atlas_file(toml_path)
    try:
        plugins = tomllib.loads(text).get("plugins", {})
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"Cannot read {ATLAS_TOML} ({error})") from error
    if name in plugins:
        raise ValueError(f"{name} is already declared in {ATLAS_TOML}")
    return append_plugin(text, name, source)
