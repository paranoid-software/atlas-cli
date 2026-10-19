"""`atlas method`: the framework's pages, from the CLI.

The source is the published site unless `--source` set another: a URL, or the path of a local
clone of the framework repo. The CLI keeps that choice in its own user configuration, never in
an Atlas and never in a workbench's folder.
"""

import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_SOURCE = "https://atlas.paranoid.software"
CONFIG_FOLDER_VARIABLE = "ATLAS_CONFIG_DIR"
SOURCE_FILE = "source"
TIMEOUT = 5
_PAGE = re.compile(r"method/((\d{2})-[a-z0-9-]+)\.md")


def register(subparsers) -> None:
    parser = subparsers.add_parser("method", help="print the framework: its index, one page, or all of it")
    parser.add_argument("page", nargs="?", default=None, help="a page: method/04-spec-lifecycle.md, 04-spec-lifecycle or 04")
    parser.add_argument("--full", action="store_true", help="the whole framework in one text")
    parser.add_argument("--source", default=None, metavar="URL|PATH", help="set where the framework comes from, once")
    parser.set_defaults(handler=run)


def run(args) -> int:
    if args.source is not None:
        path = write_source(args.source)
        print(f"framework source: {args.source} (kept in {path})")
        if args.page is None and not args.full:
            return 0
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        if args.full:
            text = full_text(read_source())
        elif args.page is not None:
            text = page(read_source(), args.page)
        else:
            text = index(read_source())
    except MethodError as error:
        print(f"{error}.")
        return 1
    print(text, end="" if text.endswith("\n") else "\n")
    return 0


class MethodError(Exception):
    pass


# --- the source ------------------------------------------------------------------------------


def config_folder() -> Path:
    configured = os.environ.get(CONFIG_FOLDER_VARIABLE)
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Roaming") / "atlas"
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "atlas"


def read_source() -> str:
    path = config_folder() / SOURCE_FILE
    try:
        value = path.read_text(encoding="utf-8").strip().splitlines()[0].strip() if path.is_file() else ""
    except (OSError, UnicodeDecodeError, IndexError):
        value = ""
    return value or DEFAULT_SOURCE


def write_source(value: str) -> Path:
    folder = config_folder()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / SOURCE_FILE
    path.write_text(value.strip() + "\n", encoding="utf-8", newline="\n")
    return path


def has_source() -> bool:
    return (config_folder() / SOURCE_FILE).is_file()


# --- the pages -------------------------------------------------------------------------------


def index(source: str) -> str:
    if _is_url(source):
        return _fetch(source, "llms.txt")
    return _read(source, "method/README.md")


def full_text(source: str) -> str:
    if _is_url(source):
        return _fetch(source, "llms-full.txt")
    parts = [_read(source, "method/README.md")]
    for name in _clone_pages(source):
        parts.append(_read(source, f"method/{name}.md"))
    return "\n\n".join(part.rstrip("\n") for part in parts) + "\n"


def page(source: str, wanted: str) -> str:
    name = _resolve(source, wanted)
    if _is_url(source):
        return _fetch(source, f"method/{name}.md")
    return _read(source, f"method/{name}.md")


def _resolve(source: str, wanted: str) -> str:
    """`method/04-spec-lifecycle.md`, `04-spec-lifecycle` or `04` to the page's name."""
    wanted = wanted.strip()
    if wanted.startswith("method/"):
        wanted = wanted[len("method/"):]
    if wanted.endswith(".md"):
        wanted = wanted[:-3]
    if wanted == "README":
        return "README"
    pages = _url_pages(source) if _is_url(source) else _clone_pages(source)
    if wanted in pages:
        return wanted
    if re.fullmatch(r"\d{1,2}", wanted):
        number = f"{int(wanted):02d}"
        found = [name for name in pages if name.startswith(f"{number}-")]
        if found:
            return found[0]
    raise MethodError(f"The framework has no page '{wanted}'; the pages are " + ", ".join(pages))


def _url_pages(source: str) -> list[str]:
    return [match.group(1) for match in _PAGE.finditer(_fetch(source, "llms.txt"))]


def _clone_pages(source: str) -> list[str]:
    folder = Path(source).expanduser() / "method"
    if not folder.is_dir():
        raise MethodError(f"{source} has no method/ folder: not a clone of the framework repo")
    return sorted(entry.stem for entry in folder.iterdir() if entry.is_file() and re.fullmatch(r"\d{2}-[a-z0-9-]+\.md", entry.name))


def _is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def _fetch(source: str, relative: str) -> str:
    url = f"{source.rstrip('/')}/{relative}"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        raise MethodError(f"The framework source answered {error.code} for {url}") from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        reason = getattr(error, "reason", None) or error
        raise MethodError(f"The framework source {source} could not be reached ({reason}); `atlas method --source <url|path>` sets another") from error


def _read(source: str, relative: str) -> str:
    path = Path(source).expanduser() / relative
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise MethodError(f"The framework source {source} has no readable {relative} ({getattr(error, 'strerror', None) or error})") from error
