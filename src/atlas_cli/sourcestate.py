from pathlib import Path


def judge_source(folder: Path, name: str) -> str:
    slot = folder / name
    if slot.is_symlink():
        if slot.exists():
            return "ok"
        return "broken"
    return "missing"
