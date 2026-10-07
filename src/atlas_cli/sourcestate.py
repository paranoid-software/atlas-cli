import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path

CLAUDE_MD = "CLAUDE.md"
_SECTION_ONE = re.compile(r"^## 1\b")
_BLOCK_HEADING = re.compile(r"^### (.+?) —(?:\s|$)")
_PLACEHOLDER = re.compile(r"<[^<>\n]+>")
_CODE_SPAN = re.compile(r"`[^`\n]*`")


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


def orientation_blocks(claude_md: str) -> dict[str, str]:
    """The `### <name> — …` blocks of CLAUDE.md §1, by exact name, heading included.

    Fenced code is left out of the blocks: a heading inside it ends nothing and a
    `<...>` inside it is code, not a placeholder.
    """
    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    in_section_one = False
    fenced = False
    for line in claude_md.splitlines():
        if line.startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("### "):
            heading = _BLOCK_HEADING.match(line.rstrip())
            current = None
            if in_section_one and heading is not None:
                current = blocks.setdefault(heading.group(1), [])
        elif line.startswith(("# ", "## ")):
            in_section_one = _SECTION_ONE.match(line) is not None
            current = None
        if current is not None:
            current.append(line)
    return {name: "\n".join(lines) for name, lines in blocks.items()}


def find_placeholders(block: str) -> list[str]:
    """The `<...>` placeholders of a block, once each in order; inline code is not one."""
    return list(dict.fromkeys(_PLACEHOLDER.findall(_CODE_SPAN.sub("", block))))
