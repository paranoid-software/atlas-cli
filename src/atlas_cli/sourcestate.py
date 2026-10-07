import unicodedata
from collections.abc import Iterable
from pathlib import Path


def judge_source(folder: Path, name: str) -> str:
    slot = atlas_entries(folder).get(name)
    if slot is not None and slot.is_symlink():
        if slot.exists():
            return "ok"
        return "broken"
    return "missing"


def atlas_entries(folder: Path) -> dict[str, Path]:
    return {entry.name: entry for entry in folder.iterdir()}


def case_twin(names: Iterable[str], name: str) -> str | None:
    folded = fold_name(name)
    return next((str(other) for other in names if str(other) != name and fold_name(str(other)) == folded), None)


def fold_name(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def find_rule_files(source: Path) -> list[str]:
    found: list[str] = []
    for name in ("CLAUDE.md", "CLAUDE.local.md", ".claude/", "AGENTS.md", ".cursorrules"):
        if _rule_file_is_present(source, name):
            found.append(name)
    return found


def _rule_file_is_present(source: Path, name: str) -> bool:
    if name.endswith("/"):
        return (source / name[:-1]).is_dir()
    return (source / name).is_file()
