"""`atlas sync`: the mechanical part of the checkpoint.

The sources' state, the SPECs' lint, the stamps that are missing, a closed SPEC still in Active,
a SPEC at the root that is in neither the backlog nor Active, then `atlas status`. The Done /
Next / Blocked of each Active block is judgment and stays with the agent or the human.
"""

from datetime import date
from pathlib import Path

from atlas_cli.atlasfiles import ATLAS_TOML
from atlas_cli.commands import doctor
from atlas_cli.commands.spec import ARCHIVED, RECENT_WINDOW, Document, is_spec_name, line_of, lint, stamp_header
from atlas_cli.commands.status import read_active, read_backlog, status_lines


def register(subparsers) -> None:
    parser = subparsers.add_parser("sync", help="checkpoint the Atlas: sources, lint, stamps, placement, status")
    parser.add_argument("--check", action="store_true", help="write nothing; return 1 when something would be written or the lint found something")
    parser.set_defaults(handler=run)


def run(args) -> int:
    folder = Path.cwd()
    if not (folder / ATLAS_TOML).is_file():
        print(f"This folder is not an Atlas (no {ATLAS_TOML}).")
        return 1
    code, lines = sync(folder, check=args.check)
    for line in lines:
        print(line)
    return code


def sync(folder: Path, check: bool = False, today: date | None = None) -> tuple[int, list[str]]:
    stamp = (today or date.today()).isoformat()
    lines: list[str] = []
    broken = False
    try:
        report = doctor.diagnose(folder)
        lines.append("doctor")
        lines.extend(_indent(doctor.report_lines(report)))
    except ValueError as error:
        lines.extend(["doctor", f"  {error}"])
        broken = True
    writes, reports = _plan(folder, stamp)
    if writes and not check:
        _apply(folder, writes, stamp)
    lines.append("would write" if check else "wrote")
    lines.extend(_indent([description for description, _apply_one in writes]))
    try:
        findings = lint(folder)  # after the writes, so it reports what is left for judgment
    except OSError as error:
        findings = [f"cannot lint: {error}"]
    if check:
        fixable = {f"{name}: archived but still in STATUS.md Active" for name in _closing(writes)} | {f"{name}: archived without closed:" for name in _stamping(writes)}
        findings = [finding if finding not in fixable else f"{finding} (sync would fix it)" for finding in findings]
    lines.append("lint")
    lines.extend(_indent(findings))
    lines.append("reports")
    lines.extend(_indent(reports))
    _code, status = status_lines(folder)
    lines.append("status")
    lines.extend(_indent(status))
    if check:
        return (1 if broken or writes or findings else 0), lines
    return (1 if broken or findings else 0), lines


def _plan(folder: Path, stamp: str) -> tuple[list[tuple[str, object]], list[str]]:
    """What sync would write, as (description, action), and what it only reports."""
    writes: list[tuple[str, object]] = []
    reports: list[str] = []
    active = read_active(folder)
    active_names = {spec["name"] for spec in active}
    backlog = read_backlog(folder)
    root = _spec_names(folder)
    archived = _spec_names(folder / ARCHIVED)
    unreadable: set[str] = set()

    def header(path: Path, field: str) -> str | None:
        key = str(path.relative_to(folder))
        try:
            return _header_value(path, field)
        except (OSError, UnicodeDecodeError) as error:
            if key not in unreadable:
                unreadable.add(key)
                reports.append(f"{key} cannot be read ({getattr(error, 'strerror', None) or error})")
            return None

    for name in sorted(active_names - archived):
        path = folder / f"{name}.md"
        if name in root and header(path, "started") is None and str(path.relative_to(folder)) not in unreadable:
            writes.append((f"{name}.md: started: {stamp}", lambda p=path: stamp_header(p, "started", stamp, after=("created",))))
    for name in sorted(archived):
        path = folder / ARCHIVED / f"{name}.md"
        if header(path, "closed") is None and str(path.relative_to(folder)) not in unreadable:
            writes.append((f"{ARCHIVED}/{name}.md: closed: {stamp}", lambda p=path: stamp_header(p, "closed", stamp, after=("started", "created"))))
    for name in sorted(active_names & archived):
        closed_on = header(folder / ARCHIVED / f"{name}.md", "closed") or stamp
        writes.append((f"STATUS.md: {name} out of Active, into Recently closed", ("close", name, closed_on)))
    for name in sorted(root - backlog - (active_names - archived)):
        reports.append(f"{name}.md is at the root but in neither the backlog nor Active: `atlas spec start {name}`, or a backlog line")
    for name in sorted((backlog | active_names) - root - archived):
        reports.append(f"{name} is listed but its file is nowhere")
    return writes, reports


def _apply(folder: Path, writes: list[tuple[str, object]], stamp: str) -> None:
    status = Document(folder / "STATUS.md")
    for _description, action in writes:
        if callable(action):
            action()
            continue
        _kind, name, closed_on = action
        status.remove_block(name)
        status.empty_section_placeholder("## Active", "_(none)_")
        status.remove_from_section("## Recently closed", line_of(name))
        status.add_to_section("## Recently closed", f"- {name} → {ARCHIVED}/ ({closed_on})", first=True)
        status.trim_section("## Recently closed", RECENT_WINDOW)
    if status.changed:
        status.touch(stamp)
        status.save()


def _closing(writes: list[tuple[str, object]]) -> list[str]:
    return [action[1] for _d, action in writes if isinstance(action, tuple)]


def _stamping(writes: list[tuple[str, object]]) -> list[str]:
    return [description.split("/", 1)[1].split(".md:")[0] for description, _a in writes if description.startswith(f"{ARCHIVED}/")]


def _spec_names(base: Path) -> set[str]:
    if not base.is_dir():
        return set()
    return {entry.stem for entry in base.iterdir() if entry.is_file() and entry.suffix == ".md" and is_spec_name(entry.stem)}


def _header_value(path: Path, field: str) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            break
        if line.startswith(f"{field}:"):
            return line[len(field) + 1 :].strip()
    return None


def _indent(lines: list[str]) -> list[str]:
    return [f"  {line}" for line in lines] if lines else ["  (nothing)"]
