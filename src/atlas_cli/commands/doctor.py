import shlex
from pathlib import Path

from atlas_cli.atlasfiles import ATLAS_TOML, read_atlas_toml
from atlas_cli.sourcestate import atlas_entries, case_twin, find_rule_files, judge_source


def register(subparsers) -> None:
    parser = subparsers.add_parser("doctor", help="report the state of the declared sources")
    parser.set_defaults(handler=run)


def run(args) -> int:
    try:
        lines = _report(Path.cwd())
    except ValueError as error:
        print(f"{error}; nothing was changed.")
        return 1
    for line in lines:
        print(line)
    if any(line.startswith(("missing ", "broken ", "undeclared ", "rules ")) for line in lines):
        return 1
    return 0


def _report(folder: Path) -> list[str]:
    toml_path = folder / ATLAS_TOML
    if not toml_path.is_file():
        raise ValueError(f"This folder is not an Atlas (no {ATLAS_TOML})")
    _, declared = read_atlas_toml(toml_path)
    entries = atlas_entries(folder)
    lines: list[str] = []
    for name, table in declared.items():
        lines.extend(_declared_source(folder, entries, str(name), _remote(table)))
    known = {str(name) for name in declared}
    undeclared = sorted(
        (entry for entry in entries.values() if entry.is_symlink() and entry.name not in known),
        key=lambda entry: entry.name,
    )
    for entry in undeclared:
        lines.append(f"undeclared {entry.name}")
        lines.append(f"atlas link {shlex.quote(entry.name)} {shlex.quote(str(entry.readlink()))}")
    return lines


def _declared_source(folder: Path, entries: dict[str, Path], name: str, remote: str | None) -> list[str]:
    state = judge_source(folder, name)
    if state == "ok":
        lines = [f"ok {name}"]
        rule_files = find_rule_files(folder / name)
        if rule_files:
            lines.append(f"rules {name}: {', '.join(rule_files)}")
        return lines
    if state == "broken":
        return [f"broken {name} -> {(folder / name).readlink()}"]
    lines = [f"missing {name}"]
    twin = case_twin(entries, name)
    if twin is not None and entries[twin].is_symlink():
        lines.append(f"atlas unlink {shlex.quote(twin)}")
    if remote is None:
        lines.append(f"atlas link {shlex.quote(name)} <path>")
        return lines
    destination = shlex.quote(f"../{name}")
    lines.append(f"git clone {shlex.quote(remote)} {destination}")
    lines.append(f"atlas link {shlex.quote(name)} {destination}")
    return lines


def _remote(table: object) -> str | None:
    if not isinstance(table, dict):
        return None
    remote = table.get("remote")
    if not isinstance(remote, str) or not remote.strip():
        return None
    return remote
