from pathlib import Path


def judge_source(folder: Path, name: str) -> str:
    slot = folder / name
    if slot.is_symlink():
        if slot.exists():
            return "ok"
        return "broken"
    return "missing"


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
