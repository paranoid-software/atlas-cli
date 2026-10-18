import json
import subprocess
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from atlas_cli.cli import main
from atlas_cli.commands.ui import make_server
from tests.ephemeralatlascontext import EphemeralAtlasContext

_SPEC = "SPEC_0001_LOGS_ROTATE"


def _atlas(world: EphemeralAtlasContext, monkeypatch, *sources: str) -> Path:
    monkeypatch.chdir(world.atlas)
    assert main(["init"]) == 0
    for name in sources:
        assert main(["link", name, str(world.source(name))]) == 0
    return world.atlas


def _new(atlas: Path, capsys, slug: str = "LOGS_ROTATE", repos: str = "log-daemon") -> Path:
    capsys.readouterr()
    assert main(["spec", "new", slug, "rotate the logs"]) == 0
    path = atlas / capsys.readouterr().out.splitlines()[0].split()[1]
    path.write_text(path.read_text(encoding="utf-8").replace("repos: <repo-a>, <repo-b>", f"repos: {repos}"), encoding="utf-8", newline="\n")
    return path


def _out(capsys) -> list[str]:
    return capsys.readouterr().out.splitlines()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def _work_on_branch(repo: Path, branch: str) -> None:
    _git(repo, "switch", "-q", "-c", branch)
    (repo / "NOTES.md").write_text("work\n", encoding="utf-8")
    _git(repo, "add", "NOTES.md")
    _git(repo, "commit", "-q", "-m", "Work")


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


# --- new ---


def test_create_a_spec_with_the_next_number_and_index_it_in_the_backlog(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        (atlas / "_archived" / "SPEC_0004_OLD_WORK.md").write_text("# SPEC_0004_OLD_WORK\n", encoding="utf-8")
        capsys.readouterr()

        assert main(["spec", "new", "LOGS_ROTATE", "rotate the logs"]) == 0

        text = (atlas / "SPEC_0005_LOGS_ROTATE.md").read_text(encoding="utf-8")
        backlog = (atlas / "BACKLOG.md").read_text(encoding="utf-8")
    assert text.startswith("# SPEC_0005_LOGS_ROTATE\ncreated: ")
    assert "## What\n" in text and "## Acceptance\n" in text and "## Out of scope\n" in text and "## Plan\n" in text
    assert backlog.endswith("## Open\n- SPEC_0005_LOGS_ROTATE — rotate the logs\n")
    assert _out(capsys) == ["created SPEC_0005_LOGS_ROTATE.md", "added to BACKLOG.md: - SPEC_0005_LOGS_ROTATE — rotate the logs"]


def test_refuse_a_slug_that_is_not_upper_snake(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        capsys.readouterr()

        assert main(["spec", "new", "logs-rotate"]) == 1

        assert "is not a slug" in capsys.readouterr().out
        assert not list(atlas.glob("SPEC_*"))


def test_number_after_the_backlog_and_active_too(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _new(atlas, capsys)
        _new(atlas, capsys, slug="SECOND")
        capsys.readouterr()

        assert main(["spec", "new", "THIRD"]) == 0

        assert (atlas / "SPEC_0003_THIRD.md").is_file()


# --- start ---


def test_start_a_spec_stamp_it_enter_active_and_print_the_branch_commands(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon", "vault"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon", "vault")
        path = _new(atlas, capsys, repos="log-daemon, vault")
        capsys.readouterr()

        assert main(["spec", "start", _SPEC]) == 0

        out = _out(capsys)
        spec = path.read_text(encoding="utf-8")
        status = (atlas / "STATUS.md").read_text(encoding="utf-8")
        backlog = (atlas / "BACKLOG.md").read_text(encoding="utf-8")
    assert spec.splitlines()[1].startswith("created: ") and spec.splitlines()[2].startswith("started: ")
    assert f"never appended)_\n\n### {_SPEC} — IN PROGRESS\n- **Done:** —\n- **Next:** step 1\n\n## Recently closed" in status
    assert backlog.endswith("## Open\n_(empty)_\n")
    assert out[-2:] == [
        "branch, run by the human: git -C log-daemon switch -c spec/0001-logs-rotate main",
        "branch, run by the human: git -C vault switch -c spec/0001-logs-rotate main",
    ]


def test_keep_a_started_stamp_already_there(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        path = _new(atlas, capsys)
        path.write_text(path.read_text(encoding="utf-8").replace("\nrepos:", "\nstarted: 2026-01-01\nrepos:"), encoding="utf-8", newline="\n")
        capsys.readouterr()

        assert main(["spec", "start", _SPEC]) == 0

        assert path.read_text(encoding="utf-8").count("started:") == 1
        assert "started: 2026-01-01" in path.read_text(encoding="utf-8")
        assert not any(line.startswith("stamped") for line in _out(capsys))


def test_refuse_to_start_a_spec_already_active_or_archived(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _new(atlas, capsys)
        assert main(["spec", "start", _SPEC]) == 0
        capsys.readouterr()
        assert main(["spec", "start", _SPEC]) == 1
        assert "already in Active" in capsys.readouterr().out
        (atlas / "_archived" / "SPEC_0002_GONE.md").write_text("# SPEC_0002_GONE\ncreated: 2026-01-01\n", encoding="utf-8")

        assert main(["spec", "start", "SPEC_0002_GONE"]) == 1

        assert "is archived" in capsys.readouterr().out


# --- pause, resume, review ---


def test_pause_and_resume_a_spec_through_its_paused_line(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        _new(atlas, capsys)
        assert main(["spec", "start", _SPEC]) == 0
        capsys.readouterr()

        assert main(["spec", "pause", _SPEC]) == 0
        paused = (atlas / "STATUS.md").read_text(encoding="utf-8")
        assert main(["spec", "pause", _SPEC]) == 1
        assert main(["spec", "resume", _SPEC]) == 0
        resumed = (atlas / "STATUS.md").read_text(encoding="utf-8")
        assert main(["spec", "resume", _SPEC]) == 1

    assert f'- **Next:** step 1\n- **Paused:** log-daemon — stash "{_SPEC} paused"\n' in paused
    assert "Paused" not in resumed
    assert f"- **Next:** step 1\n\n## Recently closed" in resumed


def test_put_a_spec_in_review(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _new(atlas, capsys)
        assert main(["spec", "start", _SPEC]) == 0

        assert main(["spec", "review", _SPEC]) == 0

        assert f"### {_SPEC} — IN REVIEW\n" in (atlas / "STATUS.md").read_text(encoding="utf-8")


def test_refuse_pause_resume_and_review_of_a_spec_not_in_active(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _new(atlas, capsys)
        for action in ("pause", "resume", "review"):
            capsys.readouterr()
            assert main(["spec", action, _SPEC]) == 1
            assert "is not in Active" in capsys.readouterr().out


# --- close ---


def test_close_a_spec_stamp_it_archive_it_with_its_findings_and_list_it_as_closed(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _new(atlas, capsys)
        assert main(["spec", "start", _SPEC]) == 0
        (atlas / "SPEC_0001_FINDINGS.md").write_text("- a finding\n", encoding="utf-8")
        capsys.readouterr()

        assert main(["spec", "close", _SPEC]) == 0

        archived = (atlas / "_archived" / f"{_SPEC}.md").read_text(encoding="utf-8")
        status = (atlas / "STATUS.md").read_text(encoding="utf-8")
        assert (atlas / "_archived" / "SPEC_0001_FINDINGS.md").is_file()
        assert not (atlas / f"{_SPEC}.md").exists() and not (atlas / "SPEC_0001_FINDINGS.md").exists()
    assert archived.splitlines()[3].startswith("closed: ")
    assert "never appended)_\n\n_(none)_\n\n## Recently closed" in status
    assert f"lives there)_\n- {_SPEC} → _archived/ (" in status
    assert _SPEC not in status.split("## Recently closed")[0]


def test_refuse_to_close_while_its_branch_is_not_merged_unless_forced(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        _new(atlas, capsys)
        assert main(["spec", "start", _SPEC]) == 0
        _work_on_branch(world.source("log-daemon"), "spec/0001-logs-rotate")
        capsys.readouterr()

        assert main(["spec", "close", _SPEC]) == 1
        refused = capsys.readouterr().out
        assert main(["spec", "close", _SPEC, "--force"]) == 0
        archived = (atlas / "_archived" / f"{_SPEC}.md").is_file()

    assert "log-daemon has spec/0001-logs-rotate with commits not on main" in refused
    assert archived


def test_close_once_the_branch_is_merged(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        _new(atlas, capsys)
        assert main(["spec", "start", _SPEC]) == 0
        repo = world.source("log-daemon")
        _work_on_branch(repo, "spec/0001-logs-rotate")
        _git(repo, "switch", "-q", "main")
        _git(repo, "merge", "-q", "--no-ff", "-m", "Merge branch 'spec/0001-logs-rotate'", "spec/0001-logs-rotate")

        assert main(["spec", "close", _SPEC]) == 0


def test_keep_recently_closed_to_its_window(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        status = atlas / "STATUS.md"
        old = "".join(f"- SPEC_{n:04d}_OLD_{n} → _archived/ (2026-01-{n:02d})\n" for n in range(10, 20))
        status.write_text(status.read_text(encoding="utf-8").rstrip("\n") + "\n" + old, encoding="utf-8", newline="\n")
        name = _new(atlas, capsys, slug="LAST").stem
        assert main(["spec", "start", name]) == 0
        capsys.readouterr()

        assert main(["spec", "close", name]) == 0

        entries = [line for line in status.read_text(encoding="utf-8").splitlines() if line.startswith("- SPEC_")]
        assert entries[0].startswith(f"- {name} → _archived/")
        assert len(entries) == 10
        assert "SPEC_0019_OLD_19" not in status.read_text(encoding="utf-8")
        assert any(line.startswith("trimmed STATUS.md Recently closed") for line in _out(capsys))


def test_refuse_to_close_a_spec_that_is_not_at_the_root(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        _atlas(world, monkeypatch)
        capsys.readouterr()

        assert main(["spec", "close", "SPEC_0009_NOWHERE"]) == 1

        assert "is not at the Atlas root" in capsys.readouterr().out


# --- lint ---


def test_report_what_a_spec_carries_that_it_should_not(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        path = _new(atlas, capsys)
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n## Progress\n- [x] done\n\n```py\nx = 1\n```\nThis step was previously different.\n",
            encoding="utf-8", newline="\n",
        )
        (atlas / "_archived" / "SPEC_0002_STALE.md").write_text("# SPEC_0002_STALE\ncreated: 2026-01-01\n\n## What\nx\n", encoding="utf-8")
        status = atlas / "STATUS.md"
        status.write_text(status.read_text(encoding="utf-8").replace("never appended)_\n", "never appended)_\n\n### SPEC_0002_STALE — IN PROGRESS\n- **Next:** go\n"), encoding="utf-8", newline="\n")
        capsys.readouterr()

        assert main(["spec", "lint"]) == 1

        out = _out(capsys)
    assert [line.split(" (")[0] for line in out] == [
        f"{_SPEC}: a fenced code block",
        f"{_SPEC}: a checkbox",
        f"{_SPEC}: a state heading",
        f"{_SPEC}: archaeology",
        "SPEC_0002_STALE: archived but still in STATUS.md Active",
        "SPEC_0002_STALE: archived without closed:",
    ]


def test_say_nothing_about_a_clean_spec(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _new(atlas, capsys)
        capsys.readouterr()

        assert main(["spec", "lint", _SPEC]) == 0

        assert capsys.readouterr().out == ""


# --- what never changes ---


def test_keep_the_files_line_endings_and_the_rest_of_their_text(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        path = _new(atlas, capsys)
        for name in ("STATUS.md", "BACKLOG.md", path.name):
            file = atlas / name
            file.write_bytes(file.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
        status_before = (atlas / "STATUS.md").read_bytes()

        assert main(["spec", "start", _SPEC]) == 0

        status_after = (atlas / "STATUS.md").read_bytes()
        assert b"\r\n" in status_after and b"\n" not in status_after.replace(b"\r\n", b"")
        assert path.read_bytes().count(b"\r\n") == path.read_bytes().count(b"\n")
        kept = [line for line in status_before.split(b"\r\n") if not line.startswith(b"_Last updated:")]
        assert all(line in status_after.split(b"\r\n") for line in kept)
        assert (atlas / "BACKLOG.md").read_bytes().endswith(b"## Open\r\n_(empty)_\r\n")


def test_never_write_through_git(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        repo = world.source("log-daemon")
        _new(atlas, capsys)
        head = _git(repo, "rev-parse", "HEAD")
        for action in (["start", _SPEC], ["pause", _SPEC], ["resume", _SPEC], ["review", _SPEC], ["close", _SPEC]):
            assert main(["spec", *action]) == 0

        assert _git(repo, "rev-parse", "HEAD") == head
        assert _git(repo, "status", "--porcelain") == ""
        assert not (atlas / ".git").exists()


def test_refuse_outside_an_atlas(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["spec", "new", "ANY"]) == 1

    assert "not an Atlas" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


# --- what the stamps feed ---


def test_feed_the_timeline_with_the_stamps_it_writes(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _new(atlas, capsys)
        assert main(["spec", "start", _SPEC]) == 0
        assert main(["spec", "close", _SPEC]) == 0

        with _server(atlas) as port:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/timeline?days=all") as response:
                events = json.loads(response.read().decode("utf-8"))["events"]

    assert sorted(event["kind"] for event in events if event["spec"] == _SPEC) == ["closed", "created", "started"]


def test_refuse_to_close_with_uncommitted_work_on_its_branch(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        _new(atlas, capsys)
        assert main(["spec", "start", _SPEC]) == 0
        repo = world.source("log-daemon")
        _git(repo, "switch", "-q", "-c", "spec/0001-logs-rotate")
        (repo / "NOTES.md").write_text("work\n", encoding="utf-8")
        capsys.readouterr()

        assert main(["spec", "close", _SPEC]) == 1

        assert "log-daemon has uncommitted work on spec/0001-logs-rotate" in capsys.readouterr().out
        assert (atlas / f"{_SPEC}.md").is_file()


def test_leave_a_sibling_backlog_line_alone(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _new(atlas, capsys, slug="A")
        backlog = atlas / "BACKLOG.md"
        backlog.write_text(backlog.read_text(encoding="utf-8") + "- SPEC_0001_AB — a cousin by name\n", encoding="utf-8", newline="\n")

        assert main(["spec", "start", "SPEC_0001_A"]) == 0

        assert backlog.read_text(encoding="utf-8").endswith("## Open\n- SPEC_0001_AB — a cousin by name\n")


def test_close_a_spec_straight_from_the_backlog(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _new(atlas, capsys)
        capsys.readouterr()

        assert main(["spec", "close", _SPEC]) == 0

        status = (atlas / "STATUS.md").read_text(encoding="utf-8")
        backlog = (atlas / "BACKLOG.md").read_text(encoding="utf-8")
        archived = (atlas / "_archived" / f"{_SPEC}.md").read_text(encoding="utf-8")
    assert archived.splitlines()[2].startswith("closed: ")
    assert backlog.endswith("## Open\n_(empty)_\n")
    assert f"- {_SPEC} → _archived/" in status
    assert not any(line.startswith("removed from STATUS.md") for line in _out(capsys))


def test_refuse_to_lint_a_spec_that_is_nowhere(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        _atlas(world, monkeypatch)
        capsys.readouterr()

        assert main(["spec", "lint", "SPEC_0009_NOWHERE"]) == 1

        assert "is not at the root nor in _archived/" in capsys.readouterr().out


def test_place_the_first_block_cleanly_after_an_empty_active_section(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _new(atlas, capsys)
        status = atlas / "STATUS.md"
        status.write_text(status.read_text(encoding="utf-8").replace("never appended)_\n", "never appended)_\n\n_(none)_\n"), encoding="utf-8", newline="\n")

        assert main(["spec", "start", _SPEC]) == 0

        assert f"never appended)_\n\n### {_SPEC} — IN PROGRESS\n- **Done:** —\n- **Next:** step 1\n\n## Recently closed" in status.read_text(encoding="utf-8")


def test_say_so_instead_of_crashing_on_a_spec_that_is_not_utf8(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        path = _new(atlas, capsys)
        path.write_bytes(b"# SPEC_0001_LOGS_ROTATE\ncreated: 2026-01-01\n\xff\n")
        capsys.readouterr()

        assert main(["spec", "start", _SPEC]) == 1

        assert "A file could not be read" in capsys.readouterr().out
