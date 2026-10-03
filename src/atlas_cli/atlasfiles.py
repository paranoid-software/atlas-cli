import json
import tomllib
from pathlib import Path

ATLAS_TOML = "_settings/atlas.toml"
CLAUDE_SETTINGS = ".claude/settings.local.json"
VSCODE_SETTINGS = ".vscode/settings.json"


def read_atlas_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_atlas_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def read_atlas_toml(path: Path) -> tuple[str, dict]:
    text = read_atlas_file(path)
    try:
        declared = tomllib.loads(text).get("sources", {})
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"Cannot read {ATLAS_TOML} ({error})") from error
    if not isinstance(declared, dict):
        raise ValueError(f"Cannot read {ATLAS_TOML} (sources is not a table)")
    return text, declared


def plan_json_file(target: Path, complete) -> tuple[str, str]:
    if not target.exists():
        return "created", _dump_json(complete({}))
    try:
        settings = json.loads(read_atlas_file(target))
    except json.JSONDecodeError as error:
        raise ValueError(f"Cannot read {target.name} in {target.parent.name}/ ({error.msg})") from error
    return "updated", _dump_json(complete(settings))


def _dump_json(settings: dict) -> str:
    return json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
