import json
import subprocess
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from atlas_cli.cli import main
from atlas_cli.commands.ui import make_server
from tests.ephemeralatlascontext import EphemeralAtlasContext


@contextmanager
def _server(atlas: Path):
    server = make_server(atlas, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def _get_json(port: int, path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as response:
        return json.loads(response.read().decode("utf-8"))


def _sources(atlas: Path) -> dict:
    with _server(atlas) as port:
        return _get_json(port, "/api/sources")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def _commit_on_spec_branch(repo: Path, branch: str, message: str, date: str) -> None:
    """A commit on a spec branch, dated so the timeline window can be checked."""
    if _git(repo, "branch", "--list", branch).strip() == "":
        _git(repo, "switch", "-q", "-c", branch)
    else:
        _git(repo, "switch", "-q", branch)
    (repo / "work.txt").write_text(f"{message}\n", encoding="utf-8")
    _git(repo, "add", "work.txt")
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", message],
        check=True,
        env={**_env(), "GIT_AUTHOR_DATE": f"{date}T12:00:00", "GIT_COMMITTER_DATE": f"{date}T12:00:00"},
    )


def _env() -> dict:
    import os

    return dict(os.environ)


def _by_name(payload: dict) -> dict:
    return {entry["name"]: entry for entry in payload["sources"]}


def test_describe_a_repo_with_its_branch_changes_and_last_commit(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        repo = world.source("log-daemon")
        (repo / "new.txt").write_text("x\n", encoding="utf-8")

        entry = _by_name(_sources(world.atlas))["log-daemon"]

    assert (entry["state"], entry["kind"], entry["branch"], entry["changes"]) == ("ok", "repo", "main", 1)
    assert entry["last"]["author"] == "Atlas"
    assert entry["last"]["subject"] == "Start"
    assert entry["spec_branches"] == []


def test_list_the_spec_branches_of_a_repo(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        _commit_on_spec_branch(world.source("log-daemon"), "spec/0007-logs", "Add logs", "2026-10-10")

        entry = _by_name(_sources(world.atlas))["log-daemon"]

    assert entry["branch"] == "spec/0007-logs"
    assert entry["spec_branches"] == [{"branch": "spec/0007-logs", "last": "2026-10-10"}]


def test_describe_a_folder_of_repos_and_each_nested_repo(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], grouped_sources={"infra": ["gke-logy", "gke-n8n"]}) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "infra", str(world.source("infra"))]) == 0

        payload = _sources(world.atlas)

    names = [entry["name"] for entry in payload["sources"]]
    assert names == ["infra", "infra/gke-logy", "infra/gke-n8n"]
    by_name = _by_name(payload)
    assert (by_name["infra"]["kind"], by_name["infra"]["branch"]) == ("folder", None)
    assert (by_name["infra/gke-logy"]["kind"], by_name["infra/gke-logy"]["branch"]) == ("repo", "main")


def test_report_a_missing_source_and_a_plain_folder_without_git_fields(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"], plain_sources=["notes"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        assert main(["link", "notes", str(world.source("notes"))]) == 0
        (world.atlas / "log-daemon").unlink()

        by_name = _by_name(_sources(world.atlas))

    assert (by_name["log-daemon"]["state"], by_name["log-daemon"]["branch"]) == ("missing", None)
    assert (by_name["notes"]["kind"], by_name["notes"]["branch"], by_name["notes"]["last"]) == ("plain", None, None)


def test_list_a_source_whose_git_is_broken_as_unreadable(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["odd"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        (world.source("odd") / ".git").write_text("not a repo\n", encoding="utf-8")
        assert main(["link", "odd", str(world.source("odd"))]) == 0

        payload = _sources(world.atlas)

    assert payload["unreadable"] == ["odd"]
    assert _by_name(payload)["odd"]["branch"] is None


def test_write_nothing_in_the_sources_while_reading_their_git(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        repo = world.source("log-daemon")
        _commit_on_spec_branch(repo, "spec/0007-logs", "Add logs", "2026-10-10")
        before = {str(p): p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file() and ".git" not in p.parts}
        head = _git(repo, "rev-parse", "HEAD")

        with _server(world.atlas) as port:
            _get_json(port, "/api/sources")
            _get_json(port, "/api/timeline?days=all")

        assert {str(p): p.read_bytes() for p in sorted(repo.rglob("*")) if p.is_file() and ".git" not in p.parts} == before
        assert _git(repo, "rev-parse", "HEAD") == head
        assert _git(repo, "status", "--porcelain") == ""


def test_never_climb_to_a_parent_repo_from_a_source_with_an_empty_git_folder(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["odd"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        _git(world.root, "init", "-q", "-b", "outer")
        (world.source("odd") / ".git").mkdir()
        assert main(["link", "odd", str(world.source("odd"))]) == 0

        entry = _by_name(_sources(world.atlas))["odd"]

    assert entry["branch"] is None


def test_describe_a_repo_with_no_commits_yet(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], local_git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        fresh = world.root / "fresh"
        _git(world.root, "init", "-q", "-b", "main", str(fresh))
        assert main(["link", "fresh", str(fresh)]) == 0

        payload = _sources(world.atlas)

    entry = _by_name(payload)["fresh"]
    assert (entry["branch"], entry["last"]) == ("main", None)
    assert payload["unreadable"] == []


def test_report_a_broken_source(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        (world.atlas / "log-daemon").unlink()
        (world.atlas / "log-daemon").symlink_to(world.root / "gone")

        entry = _by_name(_sources(world.atlas))["log-daemon"]

    assert (entry["state"], entry["branch"]) == ("broken", None)


def test_skip_a_nested_repo_whose_name_climbs_out_of_its_folder(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], grouped_sources={"infra": ["gke-logy"]}) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "infra", str(world.source("infra"))]) == 0
        toml = world.atlas / "_settings/atlas.toml"
        toml.write_text(toml.read_text(encoding="utf-8") + '\n[sources.infra.repos.".."]\n', encoding="utf-8", newline="\n")

        names = [entry["name"] for entry in _sources(world.atlas)["sources"]]

    assert names == ["infra", "infra/gke-logy"]


def test_tell_the_atlas_name_with_the_version(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        with _server(world.atlas) as port:
            answer = _get_json(port, "/api/version")

    assert answer["name"] == "acme"


def test_list_the_rule_files_a_source_carries(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"], plain_sources=["notes"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        assert main(["link", "notes", str(world.source("notes"))]) == 0
        (world.source("log-daemon") / "AGENTS.md").write_text("rules\n", encoding="utf-8")

        by_name = _by_name(_sources(world.atlas))

    assert by_name["log-daemon"]["rules"] == ["AGENTS.md"]
    assert by_name["notes"]["rules"] == []
