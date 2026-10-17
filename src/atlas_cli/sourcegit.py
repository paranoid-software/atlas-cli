"""What the sources' git says — read-only, local refs only, never a fetch.

The Atlas's own folder is never read through git: an Atlas need not be a repo. A source that
is a repo is, and that is where branches, commits and authors live. Git is kept inside the
source: it never climbs to a parent repo, and it never takes the index lock.
"""
import os
import re
import subprocess
from pathlib import Path

_SPEC_BRANCH = re.compile(r"^spec/(\d{4})-")
# The merged-in side only: "Merge pull request #N from owner/spec/NNNN-…" or "Merge branch 'spec/NNNN-…'".
_MERGED_SPEC = re.compile(r"(?:\bfrom \S*?|^Merge branch '(?:[^'/]+/)*)spec/(\d{4})-")
_SEPARATOR = "\x1f"
_BASES = ("develop", "main", "master")


def run_git(repo: Path, *args: str) -> str | None:
    """stdout of a read-only git command run inside `repo` itself, or None when git fails."""
    try:
        root = repo.resolve()
    except OSError:
        return None
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(root.parent), "GIT_OPTIONAL_LOCKS": "0"}
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def is_own_repo(repo: Path) -> bool:
    """Whether `repo` is the top of a git repo — not a folder inside some other one."""
    top = run_git(repo, "rev-parse", "--show-toplevel")
    try:
        return top is not None and Path(top.strip()).resolve() == repo.resolve()
    except OSError:
        return False


def describe_repo(repo: Path) -> dict | None:
    """Branch, uncommitted changes, HEAD's commit and the spec/* branches of a repo; None when git fails."""
    if not is_own_repo(repo):
        return None
    branch = run_git(repo, "rev-parse", "--abbrev-ref", "HEAD") or run_git(repo, "symbolic-ref", "--short", "HEAD")
    if branch is None:
        return None
    changes = run_git(repo, "status", "--porcelain")
    head = run_git(repo, "log", "-1", f"--format=%cs{_SEPARATOR}%an{_SEPARATOR}%s")
    refs = run_git(repo, "for-each-ref", "--format=%(refname:short)%09%(committerdate:short)", "refs/heads/spec/")
    return {
        "branch": branch.strip(),
        "changes": len((changes or "").splitlines()),
        "last": _commit(head),
        "spec_branches": [
            {"branch": name, "last": date}
            for name, _tab, date in (line.partition("\t") for line in (refs or "").splitlines())
            if name
        ],
    }


def spec_commits(repo: Path, source_name: str, since: str | None = None) -> list[dict]:
    """Every commit of the work on a spec/NNNN-* branch, as timeline events.

    Unmerged branches: their commits not yet on the base branch (develop, main or master; none
    are read when the repo has no base). Merged work: what each merge made on the base branch
    brought in — `M^1..M`, every parent but the first, so octopus merges count too — when its
    subject names a spec branch as the merged-in side. A commit counts once.
    """
    if not is_own_repo(repo):
        return []
    base = _base_branch(repo)
    if base is None:
        return []
    seen: set[str] = set()
    events: list[dict] = []

    def collect(number: str, selector: str) -> None:
        log = run_git(repo, "log", "--no-merges", f"--format=%H{_SEPARATOR}%cs{_SEPARATOR}%an{_SEPARATOR}%s", selector)
        for line in (log or "").splitlines():
            sha, _sep, rest = line.partition(_SEPARATOR)
            commit = _commit(rest)
            if commit is None or sha in seen:
                continue
            seen.add(sha)
            events.append({
                "date": commit["date"],
                "kind": "commit",
                "number": number,
                "repo": source_name,
                "detail": f"{commit['author']}: {commit['subject']}",
            })

    refs = run_git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/spec/")
    for branch in (refs or "").splitlines():
        match = _SPEC_BRANCH.match(branch)
        if match:
            collect(match.group(1), f"{base}..{branch}")
    window = [f"--since={since}"] if since else []
    merges = run_git(repo, "log", "--merges", "--first-parent", *window, f"--format=%H{_SEPARATOR}%s", base)
    for line in (merges or "").splitlines():
        sha, _sep, subject = line.partition(_SEPARATOR)
        match = _MERGED_SPEC.search(subject)
        if match:
            collect(match.group(1), f"{sha}^1..{sha}")
    return events


def _base_branch(repo: Path) -> str | None:
    for name in _BASES:
        if run_git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}") is not None:
            return name
    return None


def _commit(line: str | None) -> dict | None:
    if not line or not line.strip():
        return None
    date, author, subject = (line.strip().split(_SEPARATOR, 2) + ["", ""])[:3]
    return {"date": date, "author": author, "subject": subject}
