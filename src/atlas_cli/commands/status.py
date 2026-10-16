import re
import subprocess
from pathlib import Path

from atlas_cli.atlasfiles import ATLAS_TOML, read_atlas_file, read_atlas_toml
from atlas_cli.sourcedeclaration import declared_repos
from atlas_cli.sourcestate import judge_source

_SPEC_NAME = r"SPEC_\d{4}_\w+"
_BACKLOG_LINE = re.compile(rf"^- ({_SPEC_NAME})")
_ACTIVE_HEADING = re.compile(rf"^### ({_SPEC_NAME})(?: — (.*))?$")
_ACTIVE_LINE = re.compile(r"^- \*\*(Done|Next|Blocked|Paused):\*\*")
_SPEC_FILE = re.compile(rf"^({_SPEC_NAME})\.md$")
_REPOS_LINE = re.compile(r"^repos:(.*)$")
_PAUSED_STASH = re.compile(r"^(stash@\{\d+\}): .*?(?<!\w)(SPEC_\d{4}) paused$")


def register(subparsers) -> None:
    parser = subparsers.add_parser("status", help="report where the Atlas and its sources stand")
    parser.set_defaults(handler=run)


def run(args) -> int:
    folder = Path.cwd()
    toml_path = folder / ATLAS_TOML
    if not toml_path.is_file():
        print(f"This folder is not an Atlas (no {ATLAS_TOML}).")
        return 1
    try:
        _, declared = read_atlas_toml(toml_path)
    except ValueError as error:
        print(f"{error}.")
        return 1
    repos = _repo_paths(declared)
    active = _read_active(folder)
    lines = ["SPECs"]
    lines.extend(_indent(_spec_lines(folder, active)))
    lines.append("Sources")
    lines.extend(_indent(_source_lines(folder, repos, active)))
    lines.append("Paused")
    lines.extend(_indent(_paused_lines(folder, repos)))
    for line in lines:
        print(line)
    return 0


def _indent(lines: list[str]) -> list[str]:
    if not lines:
        return ["  (none)"]
    return [f"  {line}" for line in lines]


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return read_atlas_file(path)


def _is_spec(name: str) -> bool:
    return not name.endswith("_FINDINGS")


def _read_active(folder: Path) -> list[dict]:
    active: list[dict] = []
    inside = False
    current: dict | None = None
    for line in _read_text(folder / "STATUS.md").splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Active"
            current = None
            continue
        if not inside:
            continue
        if line.startswith("### "):
            heading = _ACTIVE_HEADING.match(line.rstrip())
            current = None
            if heading and _is_spec(heading.group(1)):
                current = {"name": heading.group(1), "status": heading.group(2) or "", "lines": []}
                active.append(current)
            continue
        if current is not None and _ACTIVE_LINE.match(line):
            current["lines"].append(line)
    return active


def _read_backlog(folder: Path) -> set[str]:
    found = set()
    for line in _read_text(folder / "BACKLOG.md").splitlines():
        match = _BACKLOG_LINE.match(line)
        if match and _is_spec(match.group(1)):
            found.add(match.group(1))
    return found


def _list_spec_files(folder: Path) -> set[str]:
    if not folder.is_dir():
        return set()
    found = set()
    for entry in folder.iterdir():
        match = _SPEC_FILE.match(entry.name)
        if match and entry.is_file() and _is_spec(match.group(1)):
            found.add(match.group(1))
    return found


def _spec_lines(folder: Path, active: list[dict]) -> list[str]:
    lines: list[str] = []
    for spec in active:
        heading = spec["name"] if not spec["status"] else f"{spec['name']} — {spec['status']}"
        lines.append(heading)
        lines.extend(f"  {line}" for line in spec["lines"])
    lines.extend(_placement_problems(folder, {spec["name"] for spec in active}))
    return lines


def _placement_problems(folder: Path, active: set[str]) -> list[str]:
    backlog = _read_backlog(folder)
    archived = _list_spec_files(folder / "_archived")
    root = _list_spec_files(folder)
    problems: list[str] = []
    for name in sorted(backlog | active | archived | root):
        places = [
            label
            for label, members in (("the backlog", backlog), ("Active", active), ("_archived/", archived))
            if name in members
        ]
        if len(places) > 1:
            problems.append(f"! {name}: in {_join(places)}")
        if name in root and name not in backlog and name not in active:
            problems.append(f"! {name}: at the root but in neither the backlog nor Active")
        listed = [label for label in places if label != "_archived/"]
        if listed and name not in root:
            problems.append(f"! {name}: in {_join(listed)} but its file is not at the root")
    return problems


def _join(labels: list[str]) -> str:
    if len(labels) == 1:
        return labels[0]
    return f"{', '.join(labels[:-1])} and {labels[-1]}"


def _read_repos(folder: Path, name: str) -> set[str]:
    for line in _read_text(folder / f"{name}.md").splitlines():
        match = _REPOS_LINE.match(line)
        if match:
            return {repo.strip() for repo in match.group(1).split(",") if repo.strip()}
    return set()


def _repo_paths(declared: dict) -> list[str]:
    """Each declared source, or each nested repo of a folder of repos, as `<name>` or `<name>/<child>`."""
    paths: list[str] = []
    for name, table in declared.items():
        repos = declared_repos(table)
        if repos:
            paths.extend(f"{name}/{child}" for child in repos)
        else:
            paths.append(str(name))
    return paths


def _source_lines(folder: Path, names: list[str], active: list[dict]) -> list[str]:
    touching = [(spec["name"], _read_repos(folder, spec["name"])) for spec in active]
    lines: list[str] = []
    for name in names:
        state = judge_source(folder, name.partition("/")[0])
        if state == "ok" and "/" in name and not (folder / name / ".git").exists():
            state = "missing"
        if state != "ok":
            lines.append(f"{name}: {state}")
            continue
        branch = _run_git(folder / name, ["rev-parse", "--abbrev-ref", "HEAD"])
        if branch is None:
            lines.append(f"{name}: not a git repo")
            continue
        changes = _run_git(folder / name, ["status", "--porcelain"]) or ""
        count = len(changes.splitlines())
        line = f"{name}: {branch.strip()}, {count} changed"
        clauses = [
            _describe_branch(spec, branch.strip()) for spec, repos in touching if name in repos
        ]
        if clauses:
            line = f"{line} — {'; '.join(clauses)}"
        lines.append(line)
    return lines


def _describe_branch(spec: str, branch: str) -> str:
    digits = spec[len("SPEC_"):len("SPEC_") + 4]
    short = f"SPEC_{digits}"
    if branch.startswith(f"spec/{digits}-"):
        return f"on {short}'s branch"
    return f"not on {short}'s branch (spec/{digits}-…)"


def _paused_lines(folder: Path, names: list[str]) -> list[str]:
    lines: list[str] = []
    for name in names:
        if judge_source(folder, name.partition("/")[0]) != "ok":
            continue
        stashes = _run_git(folder / name, ["stash", "list"])
        if stashes is None:
            continue
        for stash in stashes.splitlines():
            match = _PAUSED_STASH.match(stash)
            if match:
                lines.append(f"{name}: {match.group(1)} — {match.group(2)}")
    return lines


def _run_git(source: Path, args: list[str]) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return None
    return result.stdout
