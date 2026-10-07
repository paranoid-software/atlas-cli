import json
import tomllib
from importlib.resources import files
from pathlib import Path
from string import Template

ATLAS_TOML = "_settings/atlas.toml"
CLAUDE_SETTINGS = ".claude/settings.local.json"
VSCODE_SETTINGS = ".vscode/settings.json"
GITIGNORE = ".gitignore"


def read_atlas_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_atlas_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def read_atlas_toml(path: Path) -> tuple[str, dict]:
    try:
        text = read_atlas_file(path)
        declared = tomllib.loads(text).get("sources", {})
    except OSError as error:
        raise ValueError(f"Cannot read {ATLAS_TOML} ({error.strerror})") from error
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"Cannot read {ATLAS_TOML} ({error})") from error
    if not isinstance(declared, dict):
        raise ValueError(f"Cannot read {ATLAS_TOML} (sources is not a table)")
    return text, declared


def render_template(template: str, **values: str) -> str:
    text = files("atlas_cli.templates").joinpath(template).read_text(encoding="utf-8")
    return Template(text).safe_substitute(values)


def quote_toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def append_toml_section(text: str, section: str) -> str:
    body = text if text.endswith("\n") else text + "\n"
    if not body.endswith("\n\n"):
        body += "\n"
    return body + section


def plan_json_file(target: Path, complete) -> tuple[str, str]:
    if not target.exists():
        return "created", _dump_json(complete({}))
    where = f"{target.name} in {target.parent.name}/"
    try:
        settings = json.loads(read_atlas_file(target))
    except json.JSONDecodeError as error:
        raise ValueError(f"Cannot read {where} ({error.msg})") from error
    except OSError as error:
        raise ValueError(f"Cannot read {where} ({error.strerror})") from error
    if not isinstance(settings, dict):
        raise ValueError(f"Cannot read {where} (not a JSON object)")
    return "updated", _dump_json(complete(settings))


def _dump_json(settings: dict) -> str:
    return json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
