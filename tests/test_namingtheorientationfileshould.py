import json
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from atlas_cli.cli import main
from atlas_cli.commands.ui import make_server
from tests.ephemeralatlascontext import EphemeralAtlasContext, orient_sources


def _atlas(world: EphemeralAtlasContext, monkeypatch, *sources: str) -> Path:
    monkeypatch.chdir(world.atlas)
    assert main(["init"]) == 0
    for name in sources:
        assert main(["link", name, str(world.source(name))]) == 0
    orient_sources(world.atlas, *sources)
    return world.atlas


def _out(capsys) -> str:
    return capsys.readouterr().out


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


def test_create_agents_md_as_the_orientation_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert main(["init"]) == 0

    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8").startswith(f"# {tmp_path.name} Atlas")
    assert not (tmp_path / "CLAUDE.md").exists()


def test_give_claude_code_a_one_line_import_when_its_workbench_is_declared(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        capsys.readouterr()

        assert main(["workbench", "add", "claude"]) == 0

        assert (atlas / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
        assert "created CLAUDE.md as @AGENTS.md" in _out(capsys)


def test_never_overwrite_a_claude_md_that_holds_more(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        (atlas / "CLAUDE.md").write_text("# mine\n\nMy own notes for Claude.\n", encoding="utf-8")

        assert main(["workbench", "add", "claude"]) == 0

        assert (atlas / "CLAUDE.md").read_text(encoding="utf-8") == "# mine\n\nMy own notes for Claude.\n"


def test_rename_the_orientation_file_of_an_atlas_of_the_current_model(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        assert main(["workbench", "add", "claude"]) == 0
        (atlas / "CLAUDE.md").unlink()
        (atlas / "AGENTS.md").rename(atlas / "CLAUDE.md")  # an Atlas from before the rename
        orientation = (atlas / "CLAUDE.md").read_text(encoding="utf-8")
        capsys.readouterr()

        assert main(["migrate"]) == 0
        plan = _out(capsys)
        assert main(["migrate", "--apply"]) == 0

        assert plan.splitlines() == [
            "rename CLAUDE.md -> AGENTS.md",
            "write CLAUDE.md as @AGENTS.md, for Claude Code",
            "Run `atlas migrate --apply` to apply this plan.",
        ]
        assert (atlas / "AGENTS.md").read_text(encoding="utf-8") == orientation
        assert (atlas / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"
        capsys.readouterr()
        assert main(["migrate"]) == 0
        assert _out(capsys) == "This Atlas is up to date (model v1).\n"


def test_leave_no_import_line_when_claude_is_not_declared(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        (atlas / "AGENTS.md").rename(atlas / "CLAUDE.md")

        assert main(["migrate", "--apply"]) == 0

        assert (atlas / "AGENTS.md").is_file() and not (atlas / "CLAUDE.md").exists()


def test_rename_while_bringing_an_older_atlas_to_the_model(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = world.atlas
        (atlas / "CLAUDE.md").write_text("# acme\n\n## 1. What lives here\n", encoding="utf-8")
        (atlas / "STATUS.md").write_text("# acme — STATUS\n", encoding="utf-8")
        (atlas / "log-daemon").symlink_to(world.source("log-daemon"), target_is_directory=True)
        (atlas / ".claude").mkdir()
        (atlas / ".claude/settings.local.json").write_text("{}", encoding="utf-8")
        monkeypatch.chdir(atlas)
        capsys.readouterr()

        assert main(["migrate", "--apply"]) == 0

        out = _out(capsys)
        assert "renamed CLAUDE.md -> AGENTS.md" in out and "wrote CLAUDE.md as @AGENTS.md, for Claude Code" in out
        assert (atlas / "AGENTS.md").read_text(encoding="utf-8").startswith("# acme")
        assert (atlas / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"


def test_judge_the_orientation_under_its_old_name_until_renamed(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        (atlas / "AGENTS.md").rename(atlas / "CLAUDE.md")
        capsys.readouterr()

        assert main(["doctor"]) == 0

        assert _out(capsys) == "ok log-daemon\n"
        assert main(["unlink", "log-daemon"]) == 0
        assert "from CLAUDE.md §1" in _out(capsys)


def test_notice_a_claude_md_that_competes_with_agents_md(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        (atlas / "CLAUDE.md").write_text("# other orientation\n", encoding="utf-8")
        capsys.readouterr()

        assert main(["doctor"]) == 0

        out = _out(capsys)
        with _server(atlas) as port:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/doctor") as response:
                report = json.loads(response.read().decode("utf-8"))

    assert out.splitlines()[:2] == ["ok log-daemon", "orientation CLAUDE.md: does not start with @AGENTS.md: AGENTS.md is the orientation file, this one should import it"]
    assert [(f["kind"], f["level"]) for f in report["findings"]] == [("orientation", "notice")]
    assert report["ok"] is True


def test_send_every_session_to_agents_md(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        _atlas(world, monkeypatch)
        capsys.readouterr()

        assert main(["orient"]) == 0

        out = _out(capsys)
    assert "read AGENTS.md in full" in out
    assert "AGENTS.md at the Atlas root is this project's orientation" in out


def test_read_the_conventions_from_the_orientation_file_whatever_its_name(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["spec", "new", "WORK"]) == 0
        assert main(["spec", "start", "SPEC_0001_WORK"]) == 0
        agents = atlas / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8").replace("- _(empty — fill in as conventions get decided.)_\n", "- **Branches:** from develop.\n"), encoding="utf-8", newline="\n")
        agents.rename(atlas / "CLAUDE.md")
        capsys.readouterr()

        assert main(["handover", "SPEC_0001_WORK"]) == 0

        assert "## This Atlas's conventions\n- **Branches:** from develop." in _out(capsys)


def test_accept_claude_specific_lines_below_the_import(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        (atlas / "CLAUDE.md").write_text("@AGENTS.md\n\nUse the Chrome extension for the UI.\n", encoding="utf-8")
        capsys.readouterr()

        assert main(["doctor"]) == 0

        assert _out(capsys) == "ok log-daemon\n"


def test_treat_a_plain_repo_with_an_agents_md_as_no_atlas(tmp_path, monkeypatch, capsys):
    (tmp_path / "AGENTS.md").write_text("# someone's repo\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["orient"]) == 1
    assert main(["migrate"]) == 1
    assert main(["init"]) == 1

    out = _out(capsys)
    assert "older model" not in out and "predates" not in out
    assert "not an Atlas" in out
