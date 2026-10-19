"""The workbenches an Atlas declares, and the files each one needs in the Atlas.

A workbench is an editor or agent the Atlas is worked with. Its files are not the Atlas's: they
are written for the workbenches the Atlas declares, from the declared sources, on each machine.
"""

import json
import re
import tomllib
from pathlib import Path

from atlas_cli.atlasfiles import CLAUDE_SETTINGS, plan_json_file, read_atlas_file
from atlas_cli.settingscompletion import add_directory, complete_claude_settings, remove_directories

KNOWN_WORKBENCHES: dict[str, tuple[str, str]] = {
    "claude": (CLAUDE_SETTINGS, "the sources' real paths as readable directories, for Claude Code"),
}
_SECTION = re.compile(r"^\s*\[\s*workbenches\.(\"?)([A-Za-z0-9_-]+)\1\s*\]\s*$")


def declared_workbenches(text: str) -> list[str]:
    """The declared workbenches, in declaration order; an unreadable table counts as none."""
    try:
        table = tomllib.loads(text).get("workbenches", {})
    except tomllib.TOMLDecodeError:
        return []
    return [str(name) for name in table] if isinstance(table, dict) else []


def append_workbench(text: str, name: str) -> str:
    body = text if text.endswith("\n") else text + "\n"
    if not body.endswith("\n\n"):
        body += "\n"
    return body + f"[workbenches.{name}]\n"


def drop_workbench(text: str, name: str) -> str:
    """The text without the workbench's section; raises when the declaration has a shape it can't drop."""
    lines = text.splitlines(keepends=True)
    start = next((index for index, line in enumerate(lines) if _SECTION.match(line) and _SECTION.match(line).group(2) == name), None)
    if start is None:
        raise ValueError(f"{name}'s declaration has an unexpected shape")
    end = next((index for index in range(start + 1, len(lines)) if re.match(r"^\s*\[", lines[index])), len(lines))
    while end - 1 > start and (lines[end - 1].strip() == "" or lines[end - 1].strip().startswith("#")):
        end -= 1  # the next section's comments are its own
    result = "".join(lines[:start] + lines[end:])
    while "\n\n\n" in result:
        result = result.replace("\n\n\n", "\n\n")
    if name in declared_workbenches(result):
        raise ValueError(f"{name}'s declaration has an unexpected shape")
    return result


def undeclared_workbenches(folder: Path, text: str) -> list[str]:
    """Known workbenches whose file sits in the Atlas without a declaration: link and unlink don't keep it."""
    declared = declared_workbenches(text)
    return [name for name, (file, _what) in KNOWN_WORKBENCHES.items() if name not in declared and (folder / file).is_file()]


def workbench_file(name: str) -> str:
    return KNOWN_WORKBENCHES[name][0]


def rebuild(folder: Path, name: str, declared: dict, entries: dict[str, Path]) -> tuple[str, str]:
    """The workbench's file from the Atlas's declaration: (action, content), completing what is there."""
    path = folder / workbench_file(name)
    directories = [_real_path(entries[str(source)]) for source in declared if str(source) in entries and entries[str(source)].is_symlink()]

    def complete(settings: dict) -> dict:
        complete_claude_settings(settings)
        for directory in directories:
            add_directory(directory)(settings)
        return settings

    return plan_json_file(path, complete)


def on_link(folder: Path, workbenches: list[str], name: str, target: Path, previous: Path | None, repos: dict) -> list[tuple[str, tuple[str, str]]]:
    files = []
    if "claude" in workbenches:
        add = add_directory(str(target), previous)
        files.append((CLAUDE_SETTINGS, plan_json_file(folder / CLAUDE_SETTINGS, lambda settings: add(complete_claude_settings(settings)))))
    return files


def on_unlink(folder: Path, workbenches: list[str], name: str, stale: set[str]) -> list[tuple[str, str]]:
    files = []
    for workbench, complete in (("claude", remove_directories(stale)),):
        if workbench not in workbenches:
            continue
        path = folder / workbench_file(workbench)
        if not path.is_file():
            continue
        _action, content = plan_json_file(path, complete)
        if json.loads(content) != json.loads(read_atlas_file(path)):
            files.append((workbench_file(workbench), content))
    return files


def judge(folder: Path, name: str, declared: dict, entries: dict[str, Path]) -> str:
    """`ok`, `missing` or `stale`: whether the workbench's file holds what the declaration says."""
    path = folder / workbench_file(name)
    if not path.is_file():
        return "missing"
    try:
        _action, planned = rebuild(folder, name, declared, entries)
        current = json.loads(read_atlas_file(path))
    except (ValueError, OSError):
        return "stale"
    return "ok" if json.loads(planned) == current else "stale"


def _real_path(entry: Path) -> str:
    try:
        return str(entry.resolve())
    except OSError:
        return str(entry.readlink())
