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


SKIPPED_FOLDERS = {"node_modules", ".venv", "venv", "target"}


MAX_DEPTH = 8


def nested_repos(target: Path, with_origins: bool = True) -> dict[str, str | None]:
    """The git repos inside a folder that is not a repo itself, at any depth, by their path with `/`.

    The scan descends into folders that are not repos and never into a repo, a symlink, a hidden
    folder, a `_`-prefixed one (the declaration rejects those names) or one of SKIPPED_FOLDERS;
    it stops at MAX_DEPTH levels. Origins are read only when asked: the undeclared check needs
    the names alone.
    """
    if not target.is_dir() or (target / ".git").exists():
        return {}
    found: dict[str, str | None] = {}
    _scan(target, "", found, with_origins, 1)
    return found


def _scan(folder: Path, prefix: str, found: dict[str, str | None], with_origins: bool, depth: int) -> None:
    if depth > MAX_DEPTH:
        return
    try:
        children = sorted(folder.iterdir(), key=lambda entry: entry.name)
    except OSError:
        return
    for child in children:
        if child.is_symlink() or not child.is_dir() or child.name.startswith((".", "_")) or child.name in SKIPPED_FOLDERS:
            continue
        path = f"{prefix}{child.name}"
        if (child / ".git").exists():
            found[path] = read_origin(child) if with_origins else None
            continue
        _scan(child, f"{path}/", found, with_origins, depth + 1)


def declared_repos(table: object) -> dict[str, str | None]:
    """The nested repos of a declared source, by child name, with their remotes."""
    if not isinstance(table, dict) or not isinstance(table.get("repos"), dict):
        return {}
    repos: dict[str, str | None] = {}
    for child, child_table in table["repos"].items():
        if not is_repo_path(str(child)):
            continue  # a hand-edited name like ".." or "/abs" would point outside the folder
        remote = child_table.get("remote") if isinstance(child_table, dict) else None
        repos[str(child)] = remote if isinstance(remote, str) and remote.strip() else None
    return repos


def is_repo_path(path: str) -> bool:
    """A repo's path inside a folder of repos: plain segments joined by `/`, never leaving the folder."""
    if not path or "\\" in path or path.startswith("/") or path.endswith("/"):
        return False
    try:
        for segment in path.split("/"):
            check_source_name(segment)
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
