"""`atlas handover`: the delegated-mode brief, built from what the Atlas already holds.

The SPEC, the chosen step, the Active block, the Atlas's conventions, the rules in force and the
method's standing clauses, in the shape the method fixes. The principal adds what only it knows:
the files to imitate, and the rules recalled from a source the CLI cannot query.
"""

import re
from pathlib import Path

from atlas_cli.atlascorpus import read_corpus
from atlas_cli.atlasfiles import ATLAS_TOML, read_atlas_file

CANDIDATES = "CODING_RULES_CANDIDATES.md"
DEVIATIONS = "CODING_RULES_DEVIATIONS.md"
RULES_SLOT = "<<the principal pastes here the coding rules recalled for this area, by id and text>>"
_STEP = re.compile(r"^(?:-\s*)?(\d+)[.)]\s+(.*)$")
_TEMPLATE_DESCRIPTION = "_Rules that apply to this Atlas"
_TEMPLATE_PLACEHOLDER = "- _(empty — fill in as conventions get decided.)_"
_DEFAULT_MODE = re.compile(r"defaults to \*\*(paired|delegated)\*\*")

STANDING = """## How to work
- Execute the step end to end; decide the how from this brief and the rules above. Stop only on
  a real blocker or a decision this brief does not cover.
- A SPEC that conflicts with what you find is a blocker: report it as a finding, never implement around it.
- Follow the conventions of the environment you run in; install nothing to match this brief.
- Verify with: <<the principal names the verification commands and the output expected>>
- Leave the work staged in the repo, uncommitted; the human commits.

## Report expected
- What was verified, and with what output.
- What was assumed.
- What was not done, and why."""


def register(subparsers) -> None:
    parser = subparsers.add_parser("handover", help="build the delegated-mode brief for a SPEC's step")
    parser.add_argument("name", help="SPEC_NNNN_<SLUG>")
    parser.add_argument("--step", type=int, default=None, help="the Plan step to hand over (default: the whole Plan)")
    parser.add_argument("--rules", default=None, metavar="FILE", help="the coding rules recalled for the area, when the source is mcp:")
    parser.add_argument("--out", default=None, metavar="FILE", help="write the brief here instead of printing it")
    parser.add_argument("--any", action="store_true", help="hand over a SPEC that is not in Active")
    parser.set_defaults(handler=run)


def run(args) -> int:
    folder = Path.cwd()
    if not (folder / ATLAS_TOML).is_file():
        print(f"This folder is not an Atlas (no {ATLAS_TOML}).")
        return 1
    try:
        text = handover(folder, args.name, step=args.step, rules_file=args.rules, any_place=args.any)
    except Refusal as refusal:
        print(f"{refusal}.")
        return 1
    if args.out:
        try:
            Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        except OSError as error:
            print(f"Cannot write {args.out} ({error.strerror or error}).")
            return 1
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


class Refusal(Exception):
    pass


def handover(folder: Path, name: str, step: int | None = None, rules_file: str | None = None, any_place: bool = False) -> str:
    corpus = read_corpus(folder)
    spec = next((candidate for candidate in corpus["specs"] if candidate["name"] == name), None)
    if spec is None:
        unreadable = [entry for entry in corpus.get("unreadable", []) if entry.endswith(f"{name}.md")]
        if unreadable:
            raise Refusal(f"{unreadable[0]} cannot be read")
        raise Refusal(f"{name} is not a SPEC of this Atlas")
    if spec["place"] != "active" and not any_place:
        raise Refusal(f"{name} is not in STATUS.md Active (--any to hand it over anyway)")
    sections = spec["sections"]
    plan = sections.get("Plan", "")
    steps = _steps(plan)
    if step is not None and step not in steps:
        raise Refusal(f"{name} has no step {step} in its Plan")
    parts = [f"# Hand-over: {name} — {spec['title']}" + (f", step {step}" if step is not None else "")]
    parts.append(f"The SPEC is `{spec['file']}` at the Atlas root; its findings go beside it in `SPEC_{spec['number']}_FINDINGS.md`.")
    for heading in ("What", "Acceptance", "Out of scope"):
        parts.append(f"## {heading}\n{sections.get(heading, '').strip() or '_(none)_'}")
    if step is not None:
        parts.append(f"## The step\n{steps[step]}\n\nThe whole Plan, for context:\n{plan.strip()}")
    else:
        parts.append(f"## Plan\n{plan.strip() or '_(none)_'}")
    repos = ", ".join(spec["repos"]) or "_(none declared)_"
    mode = spec["mode"] or _default_mode(folder)
    branch = f"spec/{spec['number']}-{spec['name'][10:].lower().replace('_', '-')}"
    parts.append(f"## Repos and mode\nRepos: {repos}\nBranch in each: `{branch}`\nMode: {mode}")
    if spec["handoff"]:
        parts.append("## Where it stands\n" + "\n".join(f"- {key}: {value}" for key, value in spec["handoff"].items()))
    conventions = _conventions(folder)
    parts.append("## This Atlas's conventions\n" + (conventions or "_(none declared)_"))
    parts.append("## Coding rules\n" + _rules(folder, corpus["rules"], rules_file))
    parts.append(STANDING)
    return "\n\n".join(parts) + "\n"


def _steps(plan: str) -> dict[int, str]:
    """Each numbered step with its own lines: sub-bullets, continuations, a paragraph of its own."""
    steps: dict[int, list[str]] = {}
    current: int | None = None
    pending_blank = False
    for line in plan.splitlines():
        match = _STEP.match(line)
        if match:
            current = int(match.group(1))
            steps[current] = [line.rstrip()]
            pending_blank = False
        elif current is None:
            continue
        elif not line.strip():
            pending_blank = True
        elif line[0].isspace():
            if pending_blank:
                steps[current].append("")
                pending_blank = False
            steps[current].append(line.rstrip())
        else:
            current = None  # a non-indented line that is not a step ends the list
    return {number: "\n".join(lines) for number, lines in steps.items()}


def _default_mode(folder: Path) -> str:
    text = _orientation(folder)
    match = _DEFAULT_MODE.search(text)
    return f"{match.group(1)} (the Atlas default)" if match else "not stated (the SPEC has no mode: line and the orientation file declares no default)"


def _conventions(folder: Path) -> str:
    """The orientation file's section 5, the conventions of this Atlas alone, as written."""
    lines = _orientation(folder).splitlines()
    start = next((index for index, line in enumerate(lines) if line.startswith("## 5") or (line.startswith("## ") and "Conventions" in line)), None)
    if start is None:
        return ""
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    body = lines[start + 1 : end]
    if body and body[0].startswith(_TEMPLATE_DESCRIPTION):
        stop = next((index for index, line in enumerate(body) if line.rstrip().endswith("_")), len(body) - 1)
        body = body[stop + 1 :]  # the template's own description is not a convention
    body = [line for line in body if line.strip() != _TEMPLATE_PLACEHOLDER]
    return "\n".join(body).strip()


def _orientation(folder: Path) -> str:
    try:
        return read_atlas_file(folder / "CLAUDE.md")
    except (OSError, UnicodeDecodeError):
        return ""


def _rules(folder: Path, rules: dict, rules_file: str | None) -> str:
    source = rules.get("source")
    parts: list[str] = []
    if source is None:
        parts.append("This Atlas declares no coding-rules source.")
    elif source.startswith("file:"):
        parts.append(_rules_file_inside(folder, source[len("file:"):]))
    elif rules_file is not None:
        try:
            parts.append(Path(rules_file).read_text(encoding="utf-8").strip())
        except (OSError, UnicodeDecodeError) as error:
            raise Refusal(f"Cannot read {rules_file} ({getattr(error, 'strerror', None) or error})") from error
    else:
        parts.append(f"The rules come from `{source}`, which this command cannot query.\n{RULES_SLOT}")
    if rules_file is not None and (source is None or source.startswith("file:")):
        parts.append(f"(`--rules {rules_file}` was not used: this Atlas's rules come from {source or 'no source'}.)")
    for label, text, heading in (
        ("Candidate rules of this Atlas, not yet in the source", rules.get("candidates"), "## Open"),
        ("Deviations in force in this Atlas", rules.get("deviations"), "## In force"),
    ):
        entries = _entries(text or "", heading)
        if entries:
            parts.append(f"### {label}\n{entries}")
    return "\n\n".join(parts)


def _rules_file_inside(folder: Path, relative: str) -> str:
    """The declared file, read only when it sits inside the Atlas: the brief is pasted elsewhere."""
    try:
        target = (folder / relative).resolve()
        target.relative_to(folder.resolve())
    except (OSError, ValueError):
        return f"The coding-rules file `{relative}` is outside the Atlas and was not read."
    try:
        return read_atlas_file(target).strip()
    except (OSError, UnicodeDecodeError) as error:
        return f"The coding-rules file `{relative}` could not be read ({getattr(error, 'strerror', None) or error})."


def _entries(text: str, heading: str) -> str:
    """What sits under `heading`, when it is more than the template's placeholder."""
    inside = False
    kept: list[str] = []
    for line in text.splitlines():
        if line.strip() == heading:
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside:
            kept.append(line)
    body = "\n".join(kept).strip()
    return "" if not body or (body.startswith("_(") and body.endswith(")_")) else body
