import argparse
import json
import os
from importlib.resources import files
from pathlib import Path

from atlas_cli.commands import method

MACHINERY = (
    "atlas-fetch.sh",
    "hooks/session-orient.sh",
    "hooks/atlas-sync-reminder.sh",
    "hooks/skill-reminder-workspace-baseline.sh",
    "hooks/coding-rules-gate.sh",
    "commands/atlas-init.md",
    "commands/atlas-sync.md",
    "skills/workspace-baseline/SKILL.md",
)
HOOKS = (
    ("SessionStart", "session-orient.sh", None),
    ("Stop", "atlas-sync-reminder.sh", None),
    ("UserPromptSubmit", "skill-reminder-workspace-baseline.sh", None),
    ("PreToolUse", "coding-rules-gate.sh", "Edit|Write|MultiEdit|NotebookEdit"),
    ("PostToolUse", "coding-rules-gate.sh", "mcp__.*|Read"),
)
ATLAS_SOURCE = "atlas-source"
SETTINGS = "settings.json"


def register(subparsers) -> None:
    parser = subparsers.add_parser("setup", help="install the Atlas machinery for an agent")
    agents = parser.add_subparsers(dest="agent", metavar="<agent>", required=True)
    claude = agents.add_parser(
        "claude", help="install the machinery into CLAUDE_CONFIG_DIR, or ~/.claude when unset"
    )
    claude.set_defaults(handler=run_claude)


def run_claude(args: argparse.Namespace) -> int:
    target = config_folder()
    try:
        settings_lines, settings_content = _plan_settings(target / SETTINGS, target)
    except ValueError as error:
        print(f"{error}; nothing was changed.")
        return 1
    for line in _install_machinery(target):
        print(line)
    print(_install_source(target / ATLAS_SOURCE))
    if settings_content is not None:
        target.mkdir(parents=True, exist_ok=True)
        (target / SETTINGS).write_text(settings_content, encoding="utf-8", newline="\n")
    for line in settings_lines:
        print(line)
    return 0


def config_folder() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".claude"


def _install_machinery(target: Path) -> list[str]:
    lines = []
    for name in MACHINERY:
        content = files("atlas_cli").joinpath("machinery", "claude", name).read_bytes()
        destination = target / name
        if destination.is_file() and destination.read_bytes() == content:
            action = "unchanged"
        else:
            action = "replaced" if destination.exists() else "installed"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        if name.endswith(".sh"):
            destination.chmod(destination.stat().st_mode | 0o111)
        lines.append(f"{action} {name}")
    return lines


def _install_source(destination: Path) -> str:
    """The framework's source is the CLI's own setting now; an old atlas-source moves into it once."""
    if not destination.is_file():
        return f"framework source: {method.read_source()} (`atlas method --source` changes it)"
    if method.has_source():
        return f"kept {ATLAS_SOURCE} (unused: the CLI has its own framework source)"
    try:
        value = destination.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except (OSError, UnicodeDecodeError, IndexError):
        value = ""
    if not value or value == method.DEFAULT_SOURCE:
        return f"kept {ATLAS_SOURCE} (unused: the CLI reads the framework from {method.read_source()})"
    path = method.write_source(value)
    return f"moved {ATLAS_SOURCE} into the CLI's framework source ({path})"


def _plan_settings(path: Path, target: Path) -> tuple[list[str], str | None]:
    settings = _read_settings(path)
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"Cannot read {path} (hooks is not an object)")
    lines = []
    changed = not path.exists()
    for event, script, matcher in HOOKS:
        entries = hooks.setdefault(event, [])
        if not isinstance(entries, list):
            raise ValueError(f"Cannot read {path} (hooks.{event} is not a list)")
        if _is_wired(entries, script):
            lines.append(f"already wired {event}")
            continue
        command = f'bash "{target.resolve()}/hooks/{script}"'
        entry = {"hooks": [{"type": "command", "command": command}]}
        if matcher is not None:
            entry = {"matcher": matcher, **entry}
        entries.append(entry)
        lines.append(f"wired {event}")
        changed = True
    content = json.dumps(settings, indent=2, ensure_ascii=False) + "\n" if changed else None
    return lines, content


def _read_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Cannot read {path} ({error.msg})") from error
    except UnicodeDecodeError as error:
        raise ValueError(f"Cannot read {path} (not UTF-8)") from error
    if not isinstance(settings, dict):
        raise ValueError(f"Cannot read {path} (not a JSON object)")
    return settings


def _is_wired(entries: list, script: str) -> bool:
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("hooks", []), list):
            continue
        for hook in entry.get("hooks", []):
            if isinstance(hook, dict) and script in str(hook.get("command", "")):
                return True
    return False


def machinery_state() -> dict:
    """What `setup claude` would find: each machinery file against the package, each hook wired or not."""
    target = config_folder()
    machinery = []
    workbench = "claude"
    for name in MACHINERY:
        packaged = files("atlas_cli").joinpath("machinery", "claude", name).read_bytes()
        destination = target / name
        if not destination.is_file():
            state = "missing"
        else:
            try:
                state = "unchanged" if destination.read_bytes() == packaged else "differs"
            except OSError:
                state = "unreadable"
        machinery.append({"name": name, "state": state})
    error = None
    hooks_table: dict = {}
    try:
        hooks_table = _read_settings(target / SETTINGS).get("hooks", {})
        if not isinstance(hooks_table, dict):
            raise ValueError(f"Cannot read {target / SETTINGS} (hooks is not an object)")
    except ValueError as problem:
        error, hooks_table = str(problem), {}
    except OSError as problem:
        error, hooks_table = f"Cannot read {target / SETTINGS} ({problem.strerror or problem})", {}
    hooks = []
    for event, script, _matcher in HOOKS:
        entries = hooks_table.get(event, [])
        hooks.append({"event": event, "script": script, "wired": isinstance(entries, list) and _is_wired(entries, script)})
    return {"workbench": workbench, "folder": str(target), "files": machinery, "hooks": hooks, "error": error}
