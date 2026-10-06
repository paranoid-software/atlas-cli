import re
import subprocess
from pathlib import Path

from atlas_cli.atlasfiles import append_toml_section, quote_toml_string

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def append_source(text: str, name: str, remote: str | None) -> str:
    return append_toml_section(text, render_source_section(name, remote))


def render_source_section(name: str, remote: str | None) -> str:
    lines = [f"[sources.{_toml_key(name)}]"]
    if remote is not None:
        lines.append(f"remote = {quote_toml_string(remote)}")
    return "\n".join(lines) + "\n"


def read_origin(path: Path) -> str | None:
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


def _toml_key(name: str) -> str:
    if _BARE_KEY.fullmatch(name):
        return name
    return quote_toml_string(name)
