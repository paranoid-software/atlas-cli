import argparse
import re
import subprocess
from pathlib import Path

from atlas_cli.atlasfiles import (
    ATLAS_TOML,
    CLAUDE_SETTINGS,
    VSCODE_SETTINGS,
    plan_json_file,
    read_atlas_toml,
    write_atlas_file,
)

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


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
    _check_name(name)
    toml_path = folder / ATLAS_TOML
    if not toml_path.is_file():
        raise ValueError(f"This folder is not an Atlas (no {ATLAS_TOML})")
    if not given.expanduser().exists():
        raise ValueError(f"{given} does not exist")
    target = given.expanduser().resolve()
    text, declared = read_atlas_toml(toml_path)
    remote = _origin(target)
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
        toml_text = _append_source(text, name, remote)
    files = [(ATLAS_TOML, ("updated", toml_text))]
    files.append((VSCODE_SETTINGS, plan_json_file(folder / VSCODE_SETTINGS, _add_scan_repository(name))))
    files.append((CLAUDE_SETTINGS, plan_json_file(folder / CLAUDE_SETTINGS, _add_directory(str(target), previous))))
    return {"name": name, "target": target, "link": link_action, "files": files}


def _check_name(name: str) -> None:
    if name in {".", ".."} or "/" in name or "\\" in name or name.startswith((".", "_")):
        raise ValueError(f"'{name}' is not a source name")


def _append_source(text: str, name: str, remote: str | None) -> str:
    body = text if text.endswith("\n") else text + "\n"
    if not body.endswith("\n\n"):
        body += "\n"
    return body + _source_section(name, remote)


def _rebind_source(text: str, name: str, remote: str | None) -> str:
    lines = text.splitlines(keepends=True)
    start = next((index for index, line in enumerate(lines) if _header_name(line) == name), None)
    if start is None:
        raise ValueError(f"Cannot update {name} in {ATLAS_TOML}")
    body_end = start + 1
    while body_end < len(lines) and not lines[body_end].lstrip().startswith("["):
        body_end += 1
    while body_end - 1 > start and lines[body_end - 1].strip() == "":
        body_end -= 1
    return "".join(lines[:start]) + _source_section(name, remote) + "".join(lines[body_end:])


def _header_name(line: str) -> str | None:
    stripped = line.strip()
    if len(stripped) < 3 or not stripped.startswith("[") or not stripped.endswith("]"):
        return None
    inner = stripped[1:-1].strip()
    marker = "sources."
    if not inner.startswith(marker):
        return None
    key = inner[len(marker):].strip()
    if len(key) >= 2 and key[0] == '"' and key[-1] == '"':
        key = key[1:-1]
    return key or None


def _source_section(name: str, remote: str | None) -> str:
    lines = [f"[sources.{_toml_key(name)}]"]
    if remote is not None:
        lines.append(f"remote = {_toml_string(remote)}")
    return "\n".join(lines) + "\n"


def _toml_key(name: str) -> str:
    if _BARE_KEY.fullmatch(name):
        return name
    return _toml_string(name)


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _origin(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "-C", str(path), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _add_scan_repository(name: str):
    def complete(settings: dict) -> dict:
        repositories = settings.setdefault("git.scanRepositories", [])
        if name not in repositories:
            repositories.append(name)
        return settings

    return complete


def _add_directory(absolute: str, previous: Path | None = None):
    def complete(settings: dict) -> dict:
        permissions = settings.setdefault("permissions", {})
        directories = permissions.setdefault("additionalDirectories", [])
        stale = _previous_paths(previous)
        if stale:
            directories[:] = [item for item in directories if item not in stale]
        if absolute not in directories:
            directories.append(absolute)
        return settings

    return complete


def _previous_paths(previous: Path | None) -> set[str]:
    if previous is None:
        return set()
    stale = {str(previous)}
    try:
        stale.add(str(previous.resolve()))
    except OSError:
        pass
    return stale
