import json
import shlex
from pathlib import Path

from atlas_cli.atlasfiles import ATLAS_TOML, read_atlas_file, read_atlas_toml
from atlas_cli.sourcedeclaration import (
    declared_repos,
    has_credentials,
    nested_repos,
    redact_credentials,
    strip_credentials,
)
from atlas_cli.sourcestate import (
    CLAUDE_MD,
    atlas_entries,
    case_twin,
    find_placeholders,
    find_rule_files,
    judge_source,
    orientation_blocks,
)


def register(subparsers) -> None:
    parser = subparsers.add_parser("doctor", help="report the state of the declared sources")
    parser.add_argument("--json", action="store_true", help="print the same report as JSON")
    parser.set_defaults(handler=run)


def run(args) -> int:
    try:
        report = diagnose(Path.cwd())
    except ValueError as error:
        if args.json:
            print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        else:
            print(f"{error}; nothing was changed.")
        return 1
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for line in _render(report):
            print(line)
    return 0 if report["ok"] else 1


def diagnose(folder: Path) -> dict:
    toml_path = folder / ATLAS_TOML
    if not toml_path.is_file():
        raise ValueError(f"This folder is not an Atlas (no {ATLAS_TOML})")
    _, declared = read_atlas_toml(toml_path)
    entries = atlas_entries(folder)
    blocks = _orientation_blocks(folder)
    sources: list[dict] = []
    findings: list[dict] = []
    for name, table in declared.items():
        name = str(name)
        repos = declared_repos(table)
        remote = _remote(table)
        state = judge_source(folder, name)
        sources.append(_source_state(folder, name, state, repos))
        findings.extend(_source_findings(folder, entries, name, remote, repos, state))
        if blocks is not None:
            findings.extend(_orientation_findings(blocks, name))
        findings.extend(_credential_findings(folder, name, name, remote))
        for child, child_remote in repos.items():
            findings.extend(_credential_findings(folder, f"{name}/{child}", name, child_remote))
    if blocks is None:
        findings.append(_finding("missing", CLAUDE_MD))
    known = {str(declared_name) for declared_name in declared}
    undeclared = sorted(
        (entry for entry in entries.values() if entry.is_symlink() and entry.name not in known),
        key=lambda entry: entry.name,
    )
    for entry in undeclared:
        findings.append(
            _finding(
                "undeclared",
                entry.name,
                fix=[f"atlas link {shlex.quote(entry.name)} {shlex.quote(str(entry.readlink()))}"],
            )
        )
    return {"ok": not any(finding["level"] == "problem" for finding in findings), "sources": sources, "findings": findings}


def _source_state(folder: Path, name: str, state: str, repos: dict[str, str | None]) -> dict:
    slot = folder / name
    entry: dict = {
        "name": name,
        "state": state,
        "target": str(slot.readlink()) if slot.is_symlink() else None,
    }
    if not repos:
        return entry
    entry["repos"] = [
        {"name": child, "state": "ok" if state == "ok" and (slot / child / ".git").exists() else "missing"}
        for child in repos
    ]
    return entry


def _source_findings(
    folder: Path,
    entries: dict[str, Path],
    name: str,
    remote: str | None,
    repos: dict[str, str | None],
    state: str,
) -> list[dict]:
    if state == "ok":
        findings: list[dict] = []
        rule_files = find_rule_files(folder / name)
        if rule_files:
            findings.append(_finding("rules", name, ", ".join(rule_files)))
        findings.extend(_nested_findings(folder, name, repos))
        return findings
    if state == "broken":
        return [_finding("broken", name, str((folder / name).readlink()))]
    fix: list[str] = []
    twin = case_twin(entries, name)
    if twin is not None and entries[twin].is_symlink():
        fix.append(f"atlas unlink {shlex.quote(twin)}")
    if remote is None and not repos:
        fix.append(f"atlas link {shlex.quote(name)} <path>")
        return [_finding("missing", name, fix=fix)]
    destination = shlex.quote(f"../{name}")
    if remote is not None:
        fix.append(f"git clone {shlex.quote(strip_credentials(remote))} {destination}")
    for child, child_remote in repos.items():
        if child_remote is not None:
            fix.append(f"git clone {shlex.quote(strip_credentials(child_remote))} {shlex.quote(f'../{name}/{child}')}")
    fix.append(f"atlas link {shlex.quote(name)} {destination}")
    return [_finding("missing", name, fix=fix)]


def _nested_findings(folder: Path, name: str, repos: dict[str, str | None]) -> list[dict]:
    """A folder of repos: each declared repo present (with its rule files) or missing, and undeclared ones."""
    findings: list[dict] = []
    source = folder / name
    for child, child_remote in repos.items():
        if (source / child / ".git").exists():
            rule_files = find_rule_files(source / child)
            if rule_files:
                findings.append(_finding("rules", f"{name}/{child}", ", ".join(rule_files)))
            continue
        fix: list[str] = []
        if child_remote is not None:
            fix.append(f"git clone {shlex.quote(strip_credentials(child_remote))} {shlex.quote(f'{name}/{child}')}")
        findings.append(_finding("missing", f"{name}/{child}", fix=fix))
    for child in nested_repos(source):
        if child not in repos:
            findings.append(
                _finding(
                    "undeclared",
                    f"{name}/{child}",
                    fix=[f"atlas link {shlex.quote(name)} {shlex.quote(str(source.readlink()))}"],
                )
            )
    return findings


def _orientation_blocks(folder: Path) -> dict[str, str] | None:
    path = folder / CLAUDE_MD
    if not path.is_file():
        return None
    try:
        return orientation_blocks(read_atlas_file(path))
    except OSError as error:
        raise ValueError(f"Cannot read {CLAUDE_MD} ({error.strerror})") from error


def _orientation_findings(blocks: dict[str, str], name: str) -> list[dict]:
    block = blocks.get(name)
    if block is None:
        return [_finding("unoriented", name)]
    placeholders = find_placeholders(block)
    if placeholders:
        return [_finding("placeholder", name, ", ".join(placeholders))]
    return []


def _credential_findings(folder: Path, label: str, source: str, remote: str | None) -> list[dict]:
    """A remote still carrying credentials, with the `atlas link` of its source that rewrites it."""
    if remote is None or not has_credentials(remote):
        return []
    fix: list[str] = []
    if judge_source(folder, source) == "ok":
        target = (folder / source).readlink()
        fix.append(f"atlas link {shlex.quote(source)} {shlex.quote(str(target))}")
    return [_finding("credentials", label, redact_credentials(remote), fix)]


def _remote(table: object) -> str | None:
    if not isinstance(table, dict):
        return None
    remote = table.get("remote")
    if not isinstance(remote, str) or not remote.strip():
        return None
    return remote


NOTICES = {"rules"}
RULES_NOTICE = "a notice, not a problem: that source's own context, read with caution; the Atlas and the coding rules prevail, a contradiction goes to the human"


def _finding(kind: str, subject: str, detail: str | None = None, fix: list[str] | None = None) -> dict:
    """A problem keeps the Atlas from healthy until fixed; a notice is something to know."""
    return {
        "kind": kind,
        "level": "notice" if kind in NOTICES else "problem",
        "subject": subject,
        "detail": detail,
        "fix": [] if fix is None else list(fix),
    }


def report_lines(report: dict) -> list[str]:
    """The report as `atlas doctor` prints it."""
    return _render(report)


def _render(report: dict) -> list[str]:
    lines: list[str] = []
    findings = report["findings"]
    index = 0
    for source in report["sources"]:
        name = source["name"]
        if source["state"] == "ok":
            lines.append(f"ok {name}")
        while index < len(findings) and _about(findings[index], name):
            lines.extend(_render_finding(findings[index]))
            index += 1
    while index < len(findings):
        lines.extend(_render_finding(findings[index]))
        index += 1
    return lines


def _about(finding: dict, name: str) -> bool:
    """Whether this finding belongs with the source's own lines.

    The missing orientation file is also `missing` with subject `CLAUDE.md`, and it is
    printed after every source. A declared source of that name always carries a fix.
    """
    subject = finding["subject"]
    if subject == CLAUDE_MD and finding["kind"] == "missing" and not finding["fix"]:
        return False
    return subject == name or subject.startswith(f"{name}/")


def _render_finding(finding: dict) -> list[str]:
    kind = finding["kind"]
    subject = finding["subject"]
    detail = finding["detail"]
    if kind == "broken":
        line = f"broken {subject} -> {detail}"
    elif kind == "credentials":
        line = f"credentials {subject} -> {detail}"
    elif kind == "rules":
        return [f"rules {subject}: {detail}", f"  {RULES_NOTICE}"]
    elif kind == "placeholder":
        line = f"{kind} {subject}: {detail}"
    else:
        line = f"{kind} {subject}"
    return [line, *finding["fix"]]
