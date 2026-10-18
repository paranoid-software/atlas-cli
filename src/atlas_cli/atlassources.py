"""Every source of an Atlas, and every nested repo, with what its git says."""
from pathlib import Path

from atlas_cli.atlasfiles import ATLAS_TOML, read_atlas_toml
from atlas_cli.sourcedeclaration import declared_repos
from atlas_cli.sourcegit import describe_repo
from atlas_cli.sourcestate import find_rule_files, judge_source

def _empty() -> dict:
    return {"branch": None, "changes": None, "last": None, "spec_branches": [], "rules": []}


def read_sources(folder: Path) -> dict:
    """One entry per declared source in declaration order, nested repos as `<name>/<child>`."""
    toml_path = folder / ATLAS_TOML
    if not toml_path.is_file():
        return {"sources": [], "unreadable": [], "error": f"This folder is not an Atlas (no {ATLAS_TOML})"}
    try:
        _, declared = read_atlas_toml(toml_path)
    except ValueError as error:
        return {"sources": [], "unreadable": [], "error": str(error)}
    sources: list[dict] = []
    unreadable: list[str] = []
    for name, table in declared.items():
        name = str(name)
        state = judge_source(folder, name)
        nested = declared_repos(table)
        if nested:
            sources.append({"name": name, "state": state, "kind": "folder", **_empty()})
            for child in nested:
                path = folder / name / child
                child_state = "ok" if state == "ok" and (path / ".git").exists() else "missing"
                sources.append(_entry(f"{name}/{child}", child_state, "repo", path, unreadable))
            continue
        kind = "repo" if state == "ok" and (folder / name / ".git").exists() else "plain"
        sources.append(_entry(name, state, kind, folder / name, unreadable))
    return {"sources": sources, "unreadable": unreadable, "error": None}


def _entry(name: str, state: str, kind: str, path: Path, unreadable: list[str]) -> dict:
    entry = {"name": name, "state": state, "kind": kind, **_empty()}
    if state != "ok":
        return entry
    entry["rules"] = find_rule_files(path)  # the source's own rule files: a notice, shown on its card
    if kind != "repo":
        return entry
    described = describe_repo(path)
    if described is None:
        unreadable.append(name)
        return entry
    return {**entry, **described}
