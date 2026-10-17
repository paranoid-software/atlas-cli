import datetime
import json
import os
import subprocess
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from atlas_cli.cli import main
from atlas_cli.commands.ui import make_server
from tests.ephemeralatlascontext import EphemeralAtlasContext

_TODAY = datetime.date.today()


def _day(ago: int) -> str:
    return (_TODAY - datetime.timedelta(days=ago)).isoformat()


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


def _timeline(atlas: Path, query: str = "") -> dict:
    with _server(atlas) as port:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/timeline{query}") as response:
            return json.loads(response.read().decode("utf-8"))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _atlas(world: EphemeralAtlasContext, monkeypatch) -> Path:
    monkeypatch.chdir(world.atlas)
    assert main(["init"]) == 0
    return world.atlas


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def _commit_on_spec_branch(repo: Path, branch: str, message: str, date: str) -> None:
    if _git(repo, "branch", "--list", branch).strip() == "":
        _git(repo, "switch", "-q", "-c", branch)
    else:
        _git(repo, "switch", "-q", branch)
    (repo / "work.txt").write_text(f"{message}\n", encoding="utf-8")
    _git(repo, "add", "work.txt")
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", message],
        check=True,
        env={**os.environ, "GIT_AUTHOR_DATE": f"{date}T12:00:00", "GIT_COMMITTER_DATE": f"{date}T12:00:00"},
    )


def _kinds(timeline: dict) -> list[tuple[str, str, str]]:
    return [(event["date"], event["kind"], event["spec"]) for event in timeline["events"]]


def test_turn_the_stamps_of_a_spec_into_events_newest_first(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "_archived" / "SPEC_0002_LOGS.md",
               f"# SPEC_0002_LOGS\ncreated: {_day(5)}\nstarted: {_day(4)}\nclosed: {_day(1)}\nrepos: log-daemon\nmode: paired\n")

        timeline = _timeline(atlas)

    assert _kinds(timeline) == [(_day(1), "closed", "SPEC_0002_LOGS"), (_day(4), "started", "SPEC_0002_LOGS"), (_day(5), "created", "SPEC_0002_LOGS")]
    closed, started, _created = timeline["events"]
    assert closed["detail"] == "working time 3 days"
    assert started["detail"] == "paired"
    assert closed["title"] == "Logs"
    assert closed["repo"] == "log-daemon"


def test_report_the_lead_time_when_a_spec_has_no_started_stamp(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "_archived" / "SPEC_0002_OLD.md", f"# SPEC_0002_OLD\ncreated: {_day(3)}\nclosed: {_day(2)}\n")

        timeline = _timeline(atlas)

    assert [event["kind"] for event in timeline["events"]] == ["closed", "created"]
    assert timeline["events"][0]["detail"] == "lead time 1 day"


def test_turn_each_finding_into_an_event_dated_by_the_close(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "_archived" / "SPEC_0002_LOGS.md", f"# SPEC_0002_LOGS\ncreated: {_day(5)}\nclosed: {_day(1)}\n")
        _write(atlas / "_archived" / "SPEC_0002_FINDINGS.md",
               "# findings\n\n- **The transcript is not a contract.** Long text.\n- Plain finding. More.\n")

        timeline = _timeline(atlas)

    findings = [event for event in timeline["events"] if event["kind"] == "finding"]
    assert [(event["date"], event["detail"]) for event in findings] == [
        (_day(1), "The transcript is not a contract"),
        (_day(1), "Plain finding"),
    ]


def test_turn_the_commits_on_a_spec_branch_into_events(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        _write(atlas / "SPEC_0007_LOGS.md", f"# SPEC_0007_LOGS\ncreated: {_day(6)}\nstarted: {_day(3)}\nrepos: log-daemon\n")
        repo = world.source("log-daemon")
        _commit_on_spec_branch(repo, "spec/0007-logs", "Add the logger", _day(2))
        _commit_on_spec_branch(repo, "spec/0007-logs", "Rotate the logs", _day(1))

        timeline = _timeline(atlas)

    commits = [event for event in timeline["events"] if event["kind"] == "commit"]
    assert [(event["date"], event["spec"], event["repo"], event["detail"]) for event in commits] == [
        (_day(1), "SPEC_0007_LOGS", "log-daemon", "Atlas: Rotate the logs"),
        (_day(2), "SPEC_0007_LOGS", "log-daemon", "Atlas: Add the logger"),
    ]
    assert commits[0]["title"] == "Logs"


def test_leave_out_the_commits_of_the_base_branch_itself(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        repo = world.source("log-daemon")
        (repo / "base.txt").write_text("x\n", encoding="utf-8")
        _git(repo, "add", "base.txt")
        _git(repo, "commit", "-q", "-m", "Work on main")

        timeline = _timeline(atlas)

    assert [event["kind"] for event in timeline["events"]] == []


def test_keep_the_commits_of_a_spec_branch_once_it_is_merged(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        repo = world.source("log-daemon")
        _commit_on_spec_branch(repo, "spec/0007-logs", "Add the logger", _day(2))
        _commit_on_spec_branch(repo, "spec/0007-logs", "Rotate the logs", _day(1))
        _git(repo, "switch", "-q", "main")
        _git(repo, "merge", "-q", "--no-ff", "-m", "Merge pull request #3 from me/spec/0007-logs", "spec/0007-logs")
        _git(repo, "branch", "-q", "-D", "spec/0007-logs")

        timeline = _timeline(atlas)

    commits = [(event["date"], event["spec"], event["detail"]) for event in timeline["events"] if event["kind"] == "commit"]
    assert commits == [(_day(1), "SPEC_0007", "Atlas: Rotate the logs"), (_day(2), "SPEC_0007", "Atlas: Add the logger")]


def test_count_a_commit_once_when_its_branch_is_both_kept_and_merged(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        repo = world.source("log-daemon")
        _commit_on_spec_branch(repo, "spec/0007-logs", "Add the logger", _day(2))
        _git(repo, "switch", "-q", "main")
        _git(repo, "merge", "-q", "--no-ff", "-m", "Merge pull request #3 from me/spec/0007-logs", "spec/0007-logs")

        timeline = _timeline(atlas)

    assert [event["detail"] for event in timeline["events"] if event["kind"] == "commit"] == ["Atlas: Add the logger"]


def test_keep_only_the_window_asked_for_and_count_every_day_of_it(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "_archived" / "SPEC_0001_OLD.md", f"# SPEC_0001_OLD\ncreated: {_day(40)}\nclosed: {_day(30)}\n")
        _write(atlas / "_archived" / "SPEC_0002_NEW.md", f"# SPEC_0002_NEW\ncreated: {_day(6)}\nclosed: {_day(0)}\n")

        week = _timeline(atlas, "?days=7")
        everything = _timeline(atlas, "?days=all")
        default = _timeline(atlas)

    assert _kinds(week) == [(_day(0), "closed", "SPEC_0002_NEW"), (_day(6), "created", "SPEC_0002_NEW")]
    assert [day["date"] for day in week["days"]] == [_day(6 - offset) for offset in range(7)]
    assert [day["count"] for day in week["days"]] == [1, 0, 0, 0, 0, 0, 1]
    assert len(everything["events"]) == 4
    assert len(default["days"]) == 14


def test_fall_back_to_the_default_window_on_a_bad_value(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)

        timeline = _timeline(atlas, "?days=soon")

    assert len(timeline["days"]) == 14
    assert timeline["events"] == []


def test_order_the_events_of_one_day_as_the_work_happens(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        _write(atlas / "_archived" / "SPEC_0007_LOGS.md", f"# SPEC_0007_LOGS\ncreated: {_day(0)}\nstarted: {_day(0)}\nclosed: {_day(0)}\nrepos: log-daemon\n")
        _write(atlas / "_archived" / "SPEC_0007_FINDINGS.md", "# findings\n\n- One finding.\n")
        _commit_on_spec_branch(world.source("log-daemon"), "spec/0007-logs", "Do it", _day(0))

        timeline = _timeline(atlas)

    assert [event["kind"] for event in timeline["events"]] == ["closed", "finding", "commit", "started", "created"]


def _merge(repo: Path, branch: str, message: str) -> None:
    _git(repo, "merge", "-q", "--no-ff", "-m", message, branch)


def test_read_merged_work_from_the_develop_branch(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        repo = world.source("log-daemon")
        _git(repo, "switch", "-q", "-c", "develop")
        _commit_on_spec_branch(repo, "spec/0007-logs", "Add the logger", _day(2))
        _git(repo, "switch", "-q", "develop")
        _merge(repo, "spec/0007-logs", "Merge pull request #3 from me/spec/0007-logs")

        timeline = _timeline(atlas)

    assert [(event["spec"], event["detail"]) for event in timeline["events"] if event["kind"] == "commit"] == [("SPEC_0007", "Atlas: Add the logger")]


def test_never_count_develop_merged_into_a_spec_branch_as_spec_work(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        repo = world.source("log-daemon")
        _git(repo, "switch", "-q", "-c", "develop")
        _commit_on_spec_branch(repo, "spec/0040-x", "Spec work", _day(3))
        _git(repo, "switch", "-q", "develop")
        (repo / "other.txt").write_text("x\n", encoding="utf-8")
        _git(repo, "add", "other.txt")
        _git(repo, "commit", "-q", "-m", "Develop work")
        _git(repo, "switch", "-q", "spec/0040-x")
        _merge(repo, "develop", "Merge branch 'develop' into spec/0040-x")
        _git(repo, "switch", "-q", "develop")
        _merge(repo, "spec/0040-x", "Merge pull request #9 from me/spec/0040-x")

        timeline = _timeline(atlas)

    details = [event["detail"] for event in timeline["events"] if event["kind"] == "commit"]
    assert details == ["Atlas: Spec work"]


def test_count_every_branch_of_an_octopus_merge(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        repo = world.source("log-daemon")
        _git(repo, "switch", "-q", "-c", "spec/0008-a")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        _git(repo, "add", "a.txt")
        _git(repo, "commit", "-q", "-m", "Work a")
        _git(repo, "switch", "-q", "main")
        _git(repo, "switch", "-q", "-c", "spec/0008-b")
        (repo / "b.txt").write_text("b\n", encoding="utf-8")
        _git(repo, "add", "b.txt")
        _git(repo, "commit", "-q", "-m", "Work b")
        _git(repo, "switch", "-q", "main")
        _git(repo, "merge", "-q", "--no-ff", "-m", "Merge branch 'spec/0008-a' and 'spec/0008-b'", "spec/0008-a", "spec/0008-b")
        _git(repo, "branch", "-q", "-D", "spec/0008-a", "spec/0008-b")

        timeline = _timeline(atlas, "?days=all")

    assert sorted(event["detail"] for event in timeline["events"] if event["kind"] == "commit") == ["Atlas: Work a", "Atlas: Work b"]


def test_read_no_spec_commits_from_a_repo_without_a_base_branch(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        repo = world.source("log-daemon")
        _git(repo, "branch", "-q", "-m", "main", "trunk")
        _commit_on_spec_branch(repo, "spec/0007-logs", "Spec work", _day(1))

        timeline = _timeline(atlas)

    assert [event for event in timeline["events"] if event["kind"] == "commit"] == []


def test_name_the_nested_repo_a_commit_belongs_to(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], grouped_sources={"infra": ["gke-logy"]}) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["link", "infra", str(world.source("infra"))]) == 0
        _commit_on_spec_branch(world.source("infra") / "gke-logy", "spec/0007-logs", "Spec work", _day(1))

        timeline = _timeline(atlas)

    assert [event["repo"] for event in timeline["events"] if event["kind"] == "commit"] == ["infra/gke-logy"]


def test_never_read_the_git_of_the_atlas_itself(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _git(atlas, "init", "-q", "-b", "main")
        _git(atlas, "add", "-A")
        _git(atlas, "commit", "-q", "-m", "Atlas")
        _git(atlas, "switch", "-q", "-c", "spec/0001-atlas")
        _write(atlas / "NOTES.md", "notes\n")
        _git(atlas, "add", "NOTES.md")
        _git(atlas, "commit", "-q", "-m", "Atlas work")
        _git(atlas, "switch", "-q", "main")
        _git(atlas, "merge", "-q", "--no-ff", "-m", "Merge branch 'spec/0001-atlas'", "spec/0001-atlas")

        timeline = _timeline(atlas, "?days=all")

    assert [event for event in timeline["events"] if event["kind"] == "commit"] == []


def test_cap_a_huge_window(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)

        timeline = _timeline(atlas, "?days=1000000")

    assert len(timeline["days"]) == 3650


def test_count_every_day_from_the_first_event_when_asked_for_everything(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "_archived" / "SPEC_0001_OLD.md", f"# SPEC_0001_OLD\ncreated: {_day(4)}\nclosed: {_day(2)}\n")

        timeline = _timeline(atlas, "?days=all")

    assert [day["date"] for day in timeline["days"]] == [_day(4), _day(3), _day(2), _day(1), _day(0)]
