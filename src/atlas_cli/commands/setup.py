import argparse
import json
import os
from importlib.resources import files
from pathlib import Path

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
DEFAULT_SOURCE = "https://atlas.paranoid.software\n"
SETTINGS = "settings.json"


def register(subparsers) -> None:
    parser = subparsers.add_parser("setup", help="install the Atlas machinery for an agent")
    agents = parser.add_subparsers(dest="agent", metavar="<agent>", required=True)
    claude = agents.add_parser(
        "claude", help="install the machinery into CLAUDE_CONFIG_DIR, or ~/.claude when unset"
    )
    claude.set_defaults(handler=run_claude)


def run_claude(args: argparse.Namespace) -> int:
    target = _config_folder()
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


def _config_folder() -> Path:
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
    if destination.exists():
        return f"kept {ATLAS_SOURCE}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(DEFAULT_SOURCE, encoding="utf-8", newline="\n")
    return f"created {ATLAS_SOURCE}"


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
