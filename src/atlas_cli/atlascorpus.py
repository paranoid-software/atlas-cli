import hashlib
import re
import tomllib
from pathlib import Path

from atlas_cli.atlasfiles import ATLAS_TOML
from atlas_cli.commands.status import read_active, read_backlog

_SPEC_FILE = re.compile(r"^SPEC_(\d{4})_(\w+)\.md$")
_DRAFT_FILE = re.compile(r"^DRAFT_\w+\.md$")
_HEADER_FIELDS = ("created", "started", "closed", "repos", "mode")
_CANDIDATES = "CODING_RULES_CANDIDATES.md"
_DEVIATIONS = "CODING_RULES_DEVIATIONS.md"


def read_corpus(folder: Path) -> dict:
    """Every SPEC, DRAFT and coding-rules file of the Atlas, as the page needs them."""
    unreadable: list[str] = []
    active = {spec["name"] for spec in _guarded(folder, "STATUS.md", read_active, [], unreadable)}
    backlog = _guarded(folder, "BACKLOG.md", read_backlog, set(), unreadable)
    specs = []
    for place_folder in (folder, folder / "_archived"):
        for path in _spec_files(place_folder):
            text = _read(folder, path, unreadable)
            if text is None:
                continue
            specs.append(_spec(folder, path, text, active, backlog, unreadable))
    drafts = []
    for path in sorted(entry for entry in folder.iterdir() if entry.is_file() and _DRAFT_FILE.match(entry.name)):
        text = _read(folder, path, unreadable)
        if text is not None:
            drafts.append({"name": path.stem, "file": path.name, "text": text})
    rules = {
        "source": _rules_source(folder),
        "candidates": _read(folder, folder / _CANDIDATES, unreadable),
        "deviations": _read(folder, folder / _DEVIATIONS, unreadable),
    }
    return {
        "specs": sorted(specs, key=lambda spec: spec["name"]),
        "drafts": drafts,
        "rules": rules,
        "unreadable": sorted(unreadable),
    }


def fingerprint(folder: Path, machinery: Path | None = None) -> str:
    """Changes whenever something the page shows changes: the Atlas's files, its sources' links,
    and the machinery installed in `machinery` when given."""
    paths = [entry for entry in folder.iterdir() if entry.is_file() and (_SPEC_FILE.match(entry.name) or _DRAFT_FILE.match(entry.name))]
    paths += [folder / name for name in ("CLAUDE.md", "STATUS.md", "BACKLOG.md", _CANDIDATES, _DEVIATIONS, ATLAS_TOML)]
    archived = folder / "_archived"
    if archived.is_dir():
        paths += [entry for entry in archived.iterdir() if entry.is_file() and entry.suffix == ".md"]
    entries: list[tuple] = []
    for path in paths:
        entries.append(_stat(str(path.relative_to(folder)), path))
    for entry in folder.iterdir():
        if entry.is_symlink():
            entries.append((f"link:{entry.name}", str(entry.readlink()), entry.exists()))
            for git_dir in _git_dirs(entry):
                for marker in ("HEAD", "index", "packed-refs"):
                    entries.append(_stat(f"git:{git_dir.relative_to(folder)}/{marker}", git_dir / marker))
                heads = git_dir / "refs" / "heads"
                if heads.is_dir():
                    for ref in heads.rglob("*"):
                        if ref.is_file():
                            entries.append(_stat(f"git:{ref.relative_to(folder)}", ref))
    if machinery is not None and machinery.is_dir():
        for path in sorted(machinery.rglob("*")):
            if path.is_file() and path.suffix in {".sh", ".md", ".json"}:
                entries.append(_stat(f"machinery:{path.relative_to(machinery)}", path))
    return hashlib.sha256(repr(sorted(entries, key=repr)).encode("utf-8")).hexdigest()


def _git_dirs(source: Path) -> list[Path]:
    """The .git folders a source holds: its own, or its direct children's for a folder of repos."""
    try:
        if (source / ".git").is_dir():
            return [source / ".git"]
        if source.is_dir():
            return [child / ".git" for child in sorted(source.iterdir()) if (child / ".git").is_dir()]
    except OSError:
        pass
    return []


def _stat(label: str, path: Path) -> tuple:
    try:
        stat = path.stat()
    except OSError:
        return (label, None, None)
    return (label, stat.st_mtime_ns, stat.st_size)


def _guarded(folder: Path, name: str, read, empty, unreadable: list[str]):
    try:
        return read(folder)
    except (OSError, UnicodeDecodeError):
        unreadable.append(name)
        return empty


def _spec_files(place_folder: Path) -> list[Path]:
    if not place_folder.is_dir():
        return []
    return sorted(
        entry
        for entry in place_folder.iterdir()
        if entry.is_file() and _SPEC_FILE.match(entry.name) and not entry.stem.endswith("_FINDINGS")
    )


def _spec(folder: Path, path: Path, text: str, active: set[str], backlog: set[str], unreadable: list[str]) -> dict:
    number, slug = _SPEC_FILE.match(path.name).groups()
    archived = path.parent != folder
    header = _header(text)
    findings_path = path.with_name(f"SPEC_{number}_FINDINGS.md")
    return {
        "name": path.stem,
        "number": number,
        "title": slug.replace("_", " ").capitalize(),
        "file": str(path.relative_to(folder)),
        "place": "archived" if archived else "active" if path.stem in active else "backlog" if path.stem in backlog else "unplaced",
        "created": header["created"],
        "started": header["started"],
        "closed": header["closed"],
        "repos": [repo.strip() for repo in (header["repos"] or "").split(",") if repo.strip()],
        "mode": header["mode"],
        "sections": _sections(text),
        "findings": _read(folder, findings_path, unreadable) if findings_path.is_file() else None,
    }


def _header(text: str) -> dict[str, str | None]:
    found: dict[str, str | None] = {field: None for field in _HEADER_FIELDS}
    for line in text.splitlines():
        if line.startswith("## "):
            break
        field, separator, value = line.partition(":")
        if separator and field in found:
            found[field] = value.strip() or None
    return found


def _sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = sections.setdefault(line[3:].strip(), [])
        elif current is not None:
            current.append(line)
    return {heading: "\n".join(lines).strip() for heading, lines in sections.items()}


def _rules_source(folder: Path) -> str | None:
    try:
        settings = tomllib.loads((folder / ATLAS_TOML).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    plugin = settings.get("plugins", {}).get("coding-rules")
    source = plugin.get("source") if isinstance(plugin, dict) else None
    return source if isinstance(source, str) else None


def _read(folder: Path, path: Path, unreadable: list[str]) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        unreadable.append(str(path.relative_to(folder)))
        return None
