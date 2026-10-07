import re
import subprocess
from pathlib import Path

from atlas_cli.atlasfiles import append_toml_section, quote_toml_string

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_SOURCE_HEADER = re.compile(r"""\[\s*sources\s*\.\s*(?:"([^"]*)"|'([^']*)'|([A-Za-z0-9_-]+))\s*\]\s*(?:#.*)?""")


def append_source(text: str, name: str, remote: str | None) -> str:
    return append_toml_section(text, render_source_section(name, remote))


def render_source_section(name: str, remote: str | None) -> str:
    lines = [f"[sources.{_toml_key(name)}]"]
    if remote is not None:
        lines.append(f"remote = {quote_toml_string(remote)}")
    return "\n".join(lines) + "\n"


def check_source_name(name: str) -> None:
    if not name or name in {".", ".."} or "/" in name or "\\" in name or name.startswith((".", "_")):
        raise ValueError(f"'{name}' is not a source name")


def source_header_name(line: str) -> str | None:
    match = _SOURCE_HEADER.fullmatch(line.strip())
    if match is None:
        return None
    return next(key for key in match.groups() if key is not None) or None


def source_section_span(lines: list[str], name: str) -> tuple[int, int] | None:
    start = next((index for index, line in enumerate(lines) if source_header_name(line) == name), None)
    if start is None:
        return None
    end = start + 1
    while end < len(lines) and not lines[end].lstrip().startswith("["):
        end += 1
    while end - 1 > start and _blank_or_comment(lines[end - 1]):
        end -= 1
    return start, end


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


def _blank_or_comment(line: str) -> bool:
    stripped = line.strip()
    return stripped == "" or stripped.startswith("#")
