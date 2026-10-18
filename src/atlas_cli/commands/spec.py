"""`atlas spec`: the SPEC lifecycle's transitions, performed from the CLI.

The stamps, the backlog line, the Active block, `_archived/` and Recently closed are mechanical;
the Done / Next / Blocked content is judgment and stays with the agent or the human.
"""

import re
from datetime import date
from pathlib import Path

from atlas_cli.atlasfiles import ATLAS_TOML, read_atlas_file, render_template
from atlas_cli.commands.status import read_active, read_backlog
from atlas_cli.sourcegit import is_own_repo, run_git

ARCHIVED = "_archived"
RECENT_WINDOW = 10
_NAME = re.compile(r"^SPEC_(\d{4})_([A-Z0-9_]+)$")
_SLUG = re.compile(r"^[A-Z0-9][A-Z0-9_]*$")
_ANY_SPEC = re.compile(r"SPEC_(\d{4})_")
_BASES = ("develop", "main", "master")
_PLACEHOLDER = re.compile(r"^_\(.*\)_\s*$")
_CONTAMINATION = (
    ("a fenced code block", re.compile(r"^\s*```")),
    ("a checkbox", re.compile(r"^\s*- \[[ xX]\]")),
    ("a state heading", re.compile(r"^#{2,}\s*(Progress|Verification|Notes|Status|Findings)\b", re.I)),
    ("archaeology", re.compile(r"\b(previously|used to|changed from|attempt(?:ed|s)?)\b", re.I)),
)


def register(subparsers) -> None:
    parser = subparsers.add_parser("spec", help="move a SPEC through its lifecycle")
    actions = parser.add_subparsers(dest="action", metavar="<action>", required=True)
    new = actions.add_parser("new", help="create a SPEC with the next number and add it to the backlog")
    new.add_argument("slug", help="UPPER_SNAKE words, as in SPEC_NNNN_<SLUG>")
    new.add_argument("summary", nargs="?", default=None, help="the backlog's one line (default: the slug in words)")
    new.set_defaults(handler=run_new)
    for action, handler, text in (
        ("start", run_start, "stamp started:, leave the backlog, enter Active, print the branch commands"),
        ("pause", run_pause, "add the Paused line to its Active block"),
        ("resume", run_resume, "remove the Paused line from its Active block"),
        ("review", run_review, "set its Active block to IN REVIEW"),
    ):
        sub = actions.add_parser(action, help=text)
        sub.add_argument("name", help="SPEC_NNNN_<SLUG>")
        sub.set_defaults(handler=handler)
    close = actions.add_parser("close", help="stamp closed:, move it to _archived/, leave Active, enter Recently closed")
    close.add_argument("name", help="SPEC_NNNN_<SLUG>")
    close.add_argument("--force", action="store_true", help="close even with an unmerged spec branch")
    close.set_defaults(handler=run_close)
    lint = actions.add_parser("lint", help="report what a SPEC carries that it should not")
    lint.add_argument("name", nargs="?", default=None, help="one SPEC (default: every SPEC)")
    lint.set_defaults(handler=run_lint)


class Refusal(Exception):
    pass


def _run(action, args) -> int:
    folder = Path.cwd()
    if not (folder / ATLAS_TOML).is_file():
        print(f"This folder is not an Atlas (no {ATLAS_TOML}).")
        return 1
    try:
        lines = action(folder, args)
    except Refusal as refusal:
        print(f"{refusal}; nothing was changed.")
        return 1
    for line in lines:
        print(line)
    return 0


def run_new(args) -> int:
    return _run(lambda folder, a: new(folder, a.slug, a.summary), args)


def run_start(args) -> int:
    return _run(lambda folder, a: start(folder, a.name), args)


def run_pause(args) -> int:
    return _run(lambda folder, a: pause(folder, a.name), args)


def run_resume(args) -> int:
    return _run(lambda folder, a: resume(folder, a.name), args)


def run_review(args) -> int:
    return _run(lambda folder, a: review(folder, a.name), args)


def run_close(args) -> int:
    return _run(lambda folder, a: close(folder, a.name, a.force), args)


def run_lint(args) -> int:
    folder = Path.cwd()
    if not (folder / ATLAS_TOML).is_file():
        print(f"This folder is not an Atlas (no {ATLAS_TOML}).")
        return 1
    try:
        problems = lint(folder, args.name)
    except Refusal as refusal:
        print(f"{refusal}.")
        return 1
    for line in problems:
        print(line)
    return 1 if problems else 0


# --- the transitions -------------------------------------------------------------------------


def new(folder: Path, slug: str, summary: str | None, today: date | None = None) -> list[str]:
    if not _SLUG.match(slug):
        raise Refusal(f"'{slug}' is not a slug: UPPER_SNAKE words, as in SPEC_NNNN_<SLUG>")
    number = max(_known_numbers(folder), default=0) + 1
    name = f"SPEC_{number:04d}_{slug}"
    if name in _everywhere(folder):
        raise Refusal(f"{name} already exists")
    path = folder / f"{name}.md"
    text = render_template("SPEC.md", name=name, today=(today or date.today()).isoformat())
    _write(path, text.splitlines(), "\n", True)
    line = f"- {name} — {summary or slug.replace('_', ' ').lower()}"
    backlog = _Document(folder / "BACKLOG.md")
    backlog.add_to_section("## Open", line)
    backlog.save()
    return [f"created {path.name}", f"added to BACKLOG.md: {line}"]


def start(folder: Path, name: str, today: date | None = None) -> list[str]:
    number, slug = _parse(name)
    if name in {spec["name"] for spec in read_active(folder)}:
        raise Refusal(f"{name} is already in Active")
    if (folder / ARCHIVED / f"{name}.md").is_file():
        raise Refusal(f"{name} is archived")
    path = folder / f"{name}.md"
    if not path.is_file():
        raise Refusal(f"{name}.md is not at the Atlas root")
    done: list[str] = []
    stamp = (today or date.today()).isoformat()
    if _stamp(path, "started", stamp, after=("created",)):
        done.append(f"stamped {path.name}: started: {stamp}")
    backlog = _Document(folder / "BACKLOG.md")
    if backlog.remove_from_section("## Open", _backlog_line(name)):
        backlog.empty_section_placeholder("## Open", "_(empty)_")
        backlog.save()
        done.append(f"removed from BACKLOG.md: {name}")
    status = _Document(folder / "STATUS.md")
    status.add_block("## Active", [f"### {name} — IN PROGRESS", "- **Done:** —", "- **Next:** step 1"])
    status.touch(stamp)
    status.save()
    done.append(f"added to STATUS.md Active: {name} — IN PROGRESS")
    branch = f"spec/{number}-{slug.lower().replace('_', '-')}"
    for repo in _repos(path):
        done.append(f"branch, run by the human: git -C {repo} switch -c {branch} {_base_branch(folder / repo) or 'develop'}")
    return done


def pause(folder: Path, name: str, today: date | None = None) -> list[str]:
    _parse(name)
    status = _Document(folder / "STATUS.md")
    block = status.block_lines(name)
    if block is None:
        raise Refusal(f"{name} is not in Active")
    if any(line.startswith("- **Paused:**") for line in block):
        raise Refusal(f"{name} is already paused")
    repos = ", ".join(_repos(folder / f"{name}.md")) or "<repos>"
    line = f'- **Paused:** {repos} — stash "{name} paused"'
    status.append_to_block(name, line)
    status.touch((today or date.today()).isoformat())
    status.save()
    return [f"added to STATUS.md Active, {name}: {line}", f'stash, run by the human in each repo: git stash push -u -m "{name} paused"']


def resume(folder: Path, name: str, today: date | None = None) -> list[str]:
    _parse(name)
    status = _Document(folder / "STATUS.md")
    block = status.block_lines(name)
    if block is None:
        raise Refusal(f"{name} is not in Active")
    if not status.remove_from_block(name, lambda line: line.startswith("- **Paused:**")):
        raise Refusal(f"{name} is not paused")
    status.touch((today or date.today()).isoformat())
    status.save()
    return [f"removed from STATUS.md Active, {name}: the Paused line", f'stash, run by the human in each repo: git stash pop stash@{{n}}, n from git stash list ("{name} paused")']


def review(folder: Path, name: str, today: date | None = None) -> list[str]:
    _parse(name)
    status = _Document(folder / "STATUS.md")
    if status.block_lines(name) is None:
        raise Refusal(f"{name} is not in Active")
    status.set_block_status(name, "IN REVIEW")
    status.touch((today or date.today()).isoformat())
    status.save()
    return [f"set in STATUS.md Active: {name} — IN REVIEW"]


def close(folder: Path, name: str, force: bool = False, today: date | None = None) -> list[str]:
    number, _slug = _parse(name)
    path = folder / f"{name}.md"
    if (folder / ARCHIVED / f"{name}.md").is_file():
        raise Refusal(f"{name} is already archived")
    if not path.is_file():
        raise Refusal(f"{name}.md is not at the Atlas root")
    notes: list[str] = []
    if not force:
        for repo, reason in _open_work(folder, _repos(path), number, notes):
            raise Refusal(f"{repo} {reason} (--force to close anyway)")
    done: list[str] = list(notes)
    stamp = (today or date.today()).isoformat()
    if _stamp(path, "closed", stamp, after=("started", "created")):
        done.append(f"stamped {path.name}: closed: {stamp}")
    archived = folder / ARCHIVED
    if not archived.is_dir():
        archived.mkdir()
        _write(archived / "README.md", render_template("archived.md").splitlines(), "\n", True)
        done.append(f"created {ARCHIVED}/README.md")
    for moving in (path, folder / f"SPEC_{number}_FINDINGS.md"):
        if moving.is_file():
            moving.rename(archived / moving.name)
            done.append(f"moved {moving.name} to {ARCHIVED}/")
    backlog = _Document(folder / "BACKLOG.md")
    if backlog.remove_from_section("## Open", _backlog_line(name)):
        backlog.empty_section_placeholder("## Open", "_(empty)_")
        backlog.save()
        done.append(f"removed from BACKLOG.md: {name}")
    status = _Document(folder / "STATUS.md")
    if status.remove_block(name):
        status.empty_section_placeholder("## Active", "_(none)_")
        done.append(f"removed from STATUS.md Active: {name}")
    status.remove_from_section("## Recently closed", _backlog_line(name))
    status.add_to_section("## Recently closed", f"- {name} → {ARCHIVED}/ ({stamp})", first=True)
    trimmed = status.trim_section("## Recently closed", RECENT_WINDOW)
    status.touch(stamp)
    status.save()
    done.append(f"added to STATUS.md Recently closed: {name} ({stamp})")
    if trimmed:
        done.append(f"trimmed STATUS.md Recently closed to its last {RECENT_WINDOW}; the full history is {ARCHIVED}/")
    return done


def lint(folder: Path, name: str | None = None) -> list[str]:
    places = {"root": folder, "archived": folder / ARCHIVED}
    specs: list[tuple[str, str, Path]] = []
    for place, base in places.items():
        if not base.is_dir():
            continue
        for entry in sorted(base.iterdir()):
            if entry.is_file() and _NAME.match(entry.stem) and not entry.stem.endswith("_FINDINGS"):
                specs.append((entry.stem, place, entry))
    if name is not None:
        _parse(name)
        specs = [spec for spec in specs if spec[0] == name]
        if not specs:
            raise Refusal(f"{name} is not at the root nor in {ARCHIVED}/")
    active = {spec["name"] for spec in read_active(folder)}
    problems: list[str] = []
    for spec_name, place, path in specs:
        text = read_atlas_file(path)
        header, body = _split_header(text)
        for label, pattern in _CONTAMINATION:
            hits = [number for number, line in enumerate(body, start=len(header) + 1) if pattern.search(line)]
            if hits:
                problems.append(f"{spec_name}: {label} (line {hits[0]})")
        if place == "archived":
            if spec_name in active:
                problems.append(f"{spec_name}: archived but still in STATUS.md Active")
            if not any(line.startswith("closed:") for line in header):
                problems.append(f"{spec_name}: archived without closed:")
    return problems


# --- the pieces ------------------------------------------------------------------------------


def _parse(name: str) -> tuple[str, str]:
    match = _NAME.match(name)
    if not match:
        raise Refusal(f"'{name}' is not a SPEC name (SPEC_NNNN_<SLUG>)")
    return match.group(1), match.group(2)


def _known_numbers(folder: Path) -> set[int]:
    """Numbers taken by a SPEC file, a backlog line or an Active block — names, never prose."""
    numbers = set()
    for base in (folder, folder / ARCHIVED):
        if base.is_dir():
            for entry in base.iterdir():
                match = _ANY_SPEC.match(entry.name)
                if match:
                    numbers.add(int(match.group(1)))
    for name in _everywhere(folder):
        numbers.add(int(name[5:9]))
    return numbers


def _everywhere(folder: Path) -> set[str]:
    names = {spec["name"] for spec in read_active(folder)} | read_backlog(folder)
    for base in (folder, folder / ARCHIVED):
        if base.is_dir():
            names.update(entry.stem for entry in base.iterdir() if entry.suffix == ".md" and _NAME.match(entry.stem))
    return names


def _repos(path: Path) -> list[str]:
    if not path.is_file():
        return []
    for line in read_atlas_file(path).splitlines():
        if line.startswith("## "):
            break
        if line.startswith("repos:"):
            return [repo.strip() for repo in line[len("repos:"):].split(",") if repo.strip()]
    return []


def _stamp(path: Path, field: str, value: str, after: tuple[str, ...]) -> bool:
    """Write `field: value` in the header once, after the first of `after` found; False when present."""
    lines, newline, final = _read(path)
    header_end = next((index for index, line in enumerate(lines) if line.startswith("## ")), len(lines))
    if any(line.startswith(f"{field}:") for line in lines[:header_end]):
        return False
    position = None
    for anchor in after:
        position = next((index for index, line in enumerate(lines[:header_end]) if line.startswith(f"{anchor}:")), None)
        if position is not None:
            break
    at = position + 1 if position is not None else 1
    lines.insert(at, f"{field}: {value}")
    _write(path, lines, newline, final)
    return True


def _base_branch(path: Path) -> str | None:
    if not path.is_dir() or not is_own_repo(path):
        return None
    return next((name for name in _BASES if run_git(path, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}") is not None), None)


def _open_work(folder: Path, repos: list[str], number: str, notes: list[str]) -> list[tuple[str, str]]:
    """Work of this SPEC that is not in a repo's base branch: commits on its spec branch, or
    uncommitted changes while the repo stands on it. A squash merge leaves the branch's commits
    off the base and looks the same; --force is the way then."""
    found: list[tuple[str, str]] = []
    for repo in repos:
        path = folder / repo
        if not path.is_dir() or not is_own_repo(path):
            continue
        base = _base_branch(path)
        current = (run_git(path, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
        on_spec_branch = current.startswith(f"spec/{number}-")
        if on_spec_branch and (run_git(path, "status", "--porcelain") or "").strip():
            found.append((repo, f"has uncommitted work on {current}"))
            continue
        if base is None:
            notes.append(f"note: {repo} has no develop, main or master branch, so its spec branch was not checked")
            continue
        refs = run_git(path, "for-each-ref", "--format=%(refname:short)", f"refs/heads/spec/{number}-*") or ""
        for branch in refs.split():
            ahead = run_git(path, "rev-list", "--count", f"{base}..{branch}")
            if ahead is not None and ahead.strip() != "0":
                found.append((repo, f"has {branch} with commits not on {base}; a squash merge looks like this too"))
    return found


def _backlog_line(name: str):
    pattern = re.compile(rf"^- {re.escape(name)}(\s|$)")
    return lambda line: bool(pattern.match(line))


def _split_header(text: str) -> tuple[list[str], list[str]]:
    lines = text.splitlines()
    end = next((index for index, line in enumerate(lines) if line.startswith("## ")), len(lines))
    return lines[:end], lines[end:]


def _read(path: Path) -> tuple[list[str], str, bool]:
    raw = path.read_bytes().decode("utf-8")  # the file's own line endings, kept
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n").split("\n")[: -1 if raw.endswith("\n") else None], newline, raw.endswith("\n") or raw == ""


def _write(path: Path, lines: list[str], newline: str, final: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = newline.join(lines) + (newline if final else "")
    path.write_text(text, encoding="utf-8", newline="")


class _Document:
    """A Markdown file of record, edited by section and block, written back with its own line endings."""

    def __init__(self, path: Path):
        self.path = path
        if path.is_file():
            self.lines, self.newline, self.final = _read(path)
        else:
            self.lines, self.newline, self.final = [], "\n", True
        self.changed = False

    def save(self) -> None:
        if self.changed:
            _write(self.path, self.lines, self.newline, self.final)

    def touch(self, today: str) -> None:
        for index, line in enumerate(self.lines):
            if line.startswith("_Last updated:"):
                if line != f"_Last updated: {today}_":
                    self.lines[index] = f"_Last updated: {today}_"
                    self.changed = True
                return

    def _section(self, heading: str) -> tuple[int, int]:
        start = next((index for index, line in enumerate(self.lines) if line.strip() == heading), None)
        if start is None:
            self.lines.extend(["", heading])
            self.changed = True
            start = len(self.lines) - 1
        end = next((index for index in range(start + 1, len(self.lines)) if self.lines[index].startswith("## ")), len(self.lines))
        return start, end

    def _content_start(self, start: int, end: int) -> int:
        """Past the heading and its italic description, if any."""
        at = start + 1
        if at < end and _PLACEHOLDER.match(self.lines[at]) and not self._is_empty_marker(self.lines[at]):
            at += 1
        return at

    @staticmethod
    def _is_empty_marker(line: str) -> bool:
        return line.strip() in {"_(empty)_", "_(none)_"}

    def add_to_section(self, heading: str, line: str, first: bool = False) -> None:
        start, end = self._section(heading)
        at = self._content_start(start, end)
        for index in range(at, end):
            if self._is_empty_marker(self.lines[index]):
                self.lines[index] = line
                self.changed = True
                return
        if first:
            self.lines.insert(at, line)
        else:
            last = end
            while last > at and not self.lines[last - 1].strip():
                last -= 1
            self.lines.insert(last, line)
        self.changed = True

    def trim_section(self, heading: str, keep: int) -> bool:
        start, end = self._section(heading)
        entries = [index for index in range(start + 1, end) if self.lines[index].startswith("- ")]
        extra = entries[keep:]
        for index in reversed(extra):
            del self.lines[index]
        if extra:
            self.changed = True
        return bool(extra)

    def remove_from_section(self, heading: str, matches) -> bool:
        start, end = self._section(heading)
        kept = [line for line in self.lines[start + 1 : end] if not matches(line)]
        removed = len(kept) != end - start - 1
        if removed:
            self.lines[start + 1 : end] = kept
            self.changed = True
        return removed

    def empty_section_placeholder(self, heading: str, marker: str) -> None:
        start, end = self._section(heading)
        at = self._content_start(start, end)
        if not any(self.lines[index].strip() for index in range(at, end)):
            del self.lines[at:end]
            spaced = [marker] if at == start + 1 else ["", marker]
            if at < len(self.lines) and self.lines[at].startswith("## "):
                spaced.append("")
            self.lines[at:at] = spaced
            self.changed = True

    def _block(self, name: str) -> tuple[int, int] | None:
        start, end = self._section("## Active")
        for index in range(start + 1, end):
            if re.match(rf"^### {re.escape(name)}(?: — .*)?$", self.lines[index].rstrip()):
                stop = next((j for j in range(index + 1, end) if self.lines[j].startswith("### ")), end)
                return index, stop
        return None

    def block_lines(self, name: str) -> list[str] | None:
        found = self._block(name)
        return None if found is None else self.lines[found[0] + 1 : found[1]]

    def add_block(self, heading: str, block: list[str]) -> None:
        start, end = self._section(heading)
        at = self._content_start(start, end)
        for index in range(at, end):
            if self._is_empty_marker(self.lines[index]):
                del self.lines[index]
                end -= 1
                break
        last = end
        while last > at and not self.lines[last - 1].strip():
            last -= 1
        insert = ([""] if last > start + 1 and self.lines[last - 1].strip() else []) + block
        tail = [] if (last < len(self.lines) and not self.lines[last].strip()) else [""]
        self.lines[last:last] = insert + tail
        self.changed = True

    def remove_block(self, name: str) -> bool:
        found = self._block(name)
        if found is None:
            return False
        start, stop = found
        while stop < len(self.lines) and not self.lines[stop].strip() and not (stop + 1 < len(self.lines) and self.lines[stop + 1].startswith("## ")):
            stop += 1
        del self.lines[start:stop]
        while start < len(self.lines) and start > 0 and not self.lines[start].strip() and not self.lines[start - 1].strip():
            del self.lines[start]
        self.changed = True
        return True

    def append_to_block(self, name: str, line: str) -> None:
        start, stop = self._block(name)
        last = stop
        while last > start + 1 and not self.lines[last - 1].strip():
            last -= 1
        self.lines.insert(last, line)
        self.changed = True

    def remove_from_block(self, name: str, matches) -> bool:
        start, stop = self._block(name)
        kept = [line for line in self.lines[start + 1 : stop] if not matches(line)]
        removed = len(kept) != stop - start - 1
        if removed:
            self.lines[start + 1 : stop] = kept
            self.changed = True
        return removed

    def set_block_status(self, name: str, status: str) -> None:
        start, _stop = self._block(name)
        self.lines[start] = f"### {name} — {status}"
        self.changed = True
