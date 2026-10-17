import re
import subprocess
from pathlib import Path

from atlas_cli.atlasfiles import append_toml_section, quote_toml_string

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_SOURCE_HEADER = re.compile(r"""\[\s*sources\s*\.\s*(?:"([^"]*)"|'([^']*)'|([A-Za-z0-9_-]+))\s*\]\s*(?:#.*)?""")
_SUBSECTION_HEADER = re.compile(r"""\[\s*sources\s*\.\s*(?:"([^"]*)"|'([^']*)'|([A-Za-z0-9_-]+))\s*\.""")


def append_source(text: str, name: str, remote: str | None, repos: dict[str, str | None] | None = None) -> str:
    return append_toml_section(text, render_source_section(name, remote, repos))


def render_source_section(name: str, remote: str | None, repos: dict[str, str | None] | None = None) -> str:
    """The `[sources.<name>]` section; a folder of repos gets one `[sources.<name>.repos.<child>]` each."""
    lines = [f"[sources.{_toml_key(name)}]"]
    if remote is not None:
        lines.append(f"remote = {quote_toml_string(remote)}")
    for child, child_remote in sorted((repos or {}).items()):
        lines.append("")
        lines.append(f"[sources.{_toml_key(name)}.repos.{_toml_key(child)}]")
        if child_remote is not None:
            lines.append(f"remote = {quote_toml_string(child_remote)}")
    return "\n".join(lines) + "\n"


def nested_repos(target: Path) -> dict[str, str | None]:
    """The git repos that are direct children of a folder that is not a repo itself, with their origins."""
    if not target.is_dir() or (target / ".git").exists():
        return {}
    return {
        child.name: read_origin(child)
        for child in sorted(target.iterdir(), key=lambda entry: entry.name)
        if child.is_dir() and (child / ".git").exists()
    }


def declared_repos(table: object) -> dict[str, str | None]:
    """The nested repos of a declared source, by child name, with their remotes."""
    if not isinstance(table, dict) or not isinstance(table.get("repos"), dict):
        return {}
    repos: dict[str, str | None] = {}
    for child, child_table in table["repos"].items():
        if not _is_plain_name(str(child)):
            continue  # a hand-edited name like ".." or "a/b" would point outside the folder
        remote = child_table.get("remote") if isinstance(child_table, dict) else None
        repos[str(child)] = remote if isinstance(remote, str) and remote.strip() else None
    return repos


def _is_plain_name(name: str) -> bool:
    try:
        check_source_name(name)
    except ValueError:
        return False
    return True


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
    while end < len(lines) and (not lines[end].lstrip().startswith("[") or _subsection_name(lines[end]) == name):
        end += 1
    while end - 1 > start and _blank_or_comment(lines[end - 1]):
        end -= 1
    return start, end


def stray_subsections(lines: list[str], name: str, span: tuple[int, int]) -> bool:
    """Whether a `[sources.<name>.…]` section lives outside the source's own span (a hand-edited file)."""
    start, end = span
    return any(_subsection_name(line) == name for index, line in enumerate(lines) if not start <= index < end)


def _subsection_name(line: str) -> str | None:
    match = _SUBSECTION_HEADER.match(line.strip())
    if match is None:
        return None
    return next(key for key in match.groups() if key is not None) or None


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
    origin = result.stdout.strip()
    return strip_credentials(origin) if origin else None


def strip_credentials(url: str) -> str:
    """Drop the userinfo of an http(s) URL: https://me:tok@host/x -> https://host/x.

    Only http(s) carries tokens there; ssh:// and scp-like origins keep their user, which is
    the protocol (git@github.com), not a secret.
    """
    return _rewrite_userinfo(url, "")


def has_credentials(url: str) -> bool:
    return strip_credentials(url) != url


def redact_credentials(url: str) -> str:
    return _rewrite_userinfo(url, "…@")


def _rewrite_userinfo(url: str, replacement: str) -> str:
    scheme, separator, rest = url.partition("://")
    if not separator or scheme.lower() not in {"http", "https"}:
        return url
    authority = re.match(r"[^/?#]*", rest).group()
    host_start = authority.rfind("@") + 1
    if host_start == 0:
        return url
    return f"{scheme}://{replacement}{authority[host_start:]}{rest[len(authority):]}"


def _toml_key(name: str) -> str:
    if _BARE_KEY.fullmatch(name):
        return name
    return quote_toml_string(name)


def _blank_or_comment(line: str) -> bool:
    stripped = line.strip()
    return stripped == "" or stripped.startswith("#")
