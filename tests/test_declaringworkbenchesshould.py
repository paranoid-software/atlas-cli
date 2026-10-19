import json
import threading
import tomllib
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


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _toml(atlas: Path) -> dict:
    return tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))


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


def test_declare_claude_and_write_its_file_from_the_declared_sources(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"], plain_sources=["notes"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon", "notes")
        capsys.readouterr()

        assert main(["workbench", "add", "claude"]) == 0

        assert _out(capsys) == "declared claude in _settings/atlas.toml\ncreated .claude/settings.local.json\ncreated CLAUDE.md as @AGENTS.md, so Claude Code reads the orientation file\n"
        assert _toml(atlas)["workbenches"] == {"claude": {}}
        assert _json(atlas / ".claude/settings.local.json")["permissions"]["additionalDirectories"] == [
            str(world.source("log-daemon").resolve()), str(world.source("notes").resolve()),
        ]


def test_write_no_workbench_file_while_none_is_declared(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon", "vault"]) as world:
        atlas = _atlas(world, monkeypatch)

        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        assert main(["link", "vault", str(world.source("vault"))]) == 0
        assert main(["unlink", "vault"]) == 0

        assert _json(atlas / ".vscode/settings.json")["git.scanRepositories"] == ["log-daemon"]
        assert not (atlas / ".claude").exists()


def test_keep_the_declared_workbench_s_file_current_on_link_and_unlink(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon", "vault"]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["workbench", "add", "claude"]) == 0

        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        assert main(["link", "vault", str(world.source("vault"))]) == 0
        assert main(["unlink", "vault"]) == 0

        assert _json(atlas / ".claude/settings.local.json")["permissions"]["additionalDirectories"] == [str(world.source("log-daemon").resolve())]


def test_keep_a_workbench_s_file_when_dropping_its_declaration(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["workbench", "add", "claude"]) == 0
        capsys.readouterr()

        assert main(["workbench", "drop", "claude"]) == 0

        assert "workbenches" not in _toml(atlas) or _toml(atlas)["workbenches"] == {}
        assert (atlas / ".claude/settings.local.json").is_file()
        assert "kept .claude/settings.local.json" in _out(capsys)
        assert main(["workbench", "drop", "claude"]) == 1


def test_list_the_declared_workbenches_with_the_state_of_their_files(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        assert main(["workbench", "add", "claude"]) == 0
        capsys.readouterr()
        assert main(["workbench", "list"]) == 0
        listed = _out(capsys)
        (atlas / ".claude/settings.local.json").unlink()

        assert main(["workbench", "list"]) == 0

        assert listed == "claude: ok (.claude/settings.local.json)\n"
        assert _out(capsys) == "claude: missing (.claude/settings.local.json)\n"


def test_refuse_a_workbench_it_does_not_know(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        _atlas(world, monkeypatch)
        capsys.readouterr()

        assert main(["workbench", "add", "emacs"]) == 1

        assert _out(capsys) == "Unknown workbench 'emacs' (known: claude); nothing was changed.\n"


def test_report_a_declared_workbench_whose_file_is_missing_or_stale(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        assert main(["workbench", "add", "claude"]) == 0
        claude = atlas / ".claude/settings.local.json"
        claude.write_text(json.dumps({"permissions": {"allow": [], "additionalDirectories": []}}), encoding="utf-8")
        capsys.readouterr()
        assert main(["doctor"]) == 1
        stale = _out(capsys)
        claude.unlink()
        assert main(["doctor"]) == 1
        missing = _out(capsys)

        assert stale == "ok log-daemon\nworkbench claude: stale\natlas workbench add claude\n"
        assert missing == "ok log-daemon\nworkbench claude: missing\natlas workbench add claude\n"
        assert main(["workbench", "add", "claude"]) == 0
        capsys.readouterr()
        assert main(["doctor"]) == 0


def test_rebuild_a_workbench_s_file_on_another_machine_from_the_declaration(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        assert main(["workbench", "add", "claude"]) == 0
        (atlas / ".claude/settings.local.json").unlink()

        assert main(["workbench", "add", "claude"]) == 0

        assert _json(atlas / ".claude/settings.local.json")["permissions"]["additionalDirectories"] == [str(world.source("log-daemon").resolve())]


def test_show_the_workbench_finding_in_the_ui(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["workbench", "add", "claude"]) == 0
        (atlas / ".claude/settings.local.json").unlink()

        with _server(atlas) as port:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/doctor") as response:
                report = json.loads(response.read().decode("utf-8"))
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/machinery") as response:
                machinery = json.loads(response.read().decode("utf-8"))

    assert [(f["kind"], f["subject"], f["detail"], f["level"]) for f in report["findings"]] == [("workbench", "claude", "missing", "problem")]
    assert machinery["workbench"] == "claude"


def test_declare_the_workbenches_an_older_atlas_already_has(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = world.atlas
        (atlas / "CLAUDE.md").write_text("# acme\n", encoding="utf-8")
        (atlas / "STATUS.md").write_text("# acme — STATUS\n", encoding="utf-8")
        (atlas / "log-daemon").symlink_to(world.source("log-daemon"), target_is_directory=True)
        (atlas / ".claude").mkdir()
        (atlas / ".claude/settings.local.json").write_text("{}", encoding="utf-8")
        monkeypatch.chdir(atlas)
        capsys.readouterr()

        assert main(["migrate", "--apply"]) == 0

        assert "declared workbench claude and completed .claude/settings.local.json" in _out(capsys)
        assert _toml(atlas)["workbenches"] == {"claude": {}}
        assert _json(atlas / ".claude/settings.local.json")["permissions"]["additionalDirectories"] == [str(world.source("log-daemon").resolve())]


def test_report_a_workbench_file_that_is_there_but_undeclared(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        (atlas / ".claude").mkdir()
        (atlas / ".claude/settings.local.json").write_text("{}", encoding="utf-8")
        capsys.readouterr()

        assert main(["doctor"]) == 1

        out = _out(capsys)
        assert main(["workbench", "add", "claude"]) == 0
        capsys.readouterr()
        assert main(["doctor"]) == 0
    assert out == "ok log-daemon\nworkbench claude: undeclared (.claude/settings.local.json is there but link and unlink don't keep it)\natlas workbench add claude\n"


def test_keep_the_next_section_s_comment_when_dropping(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["workbench", "add", "claude"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        toml = atlas / "_settings/atlas.toml"
        toml.write_text(toml.read_text(encoding="utf-8").replace("[sources.log-daemon]", "# Sources this Atlas maps.\n[sources.log-daemon]"), encoding="utf-8", newline="\n")
        before = toml.read_text(encoding="utf-8")

        assert main(["workbench", "drop", "claude"]) == 0

        after = toml.read_text(encoding="utf-8")
        assert "[workbenches.claude]" not in after
        assert "# Sources this Atlas maps.\n[sources.log-daemon]" in after
        assert tomllib.loads(after)["sources"] == tomllib.loads(before)["sources"]


def test_refuse_to_drop_a_declaration_it_cannot_parse(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        toml = atlas / "_settings/atlas.toml"
        toml.write_text(toml.read_text(encoding="utf-8") + "\n[workbenches]\nclaude = {}\n", encoding="utf-8", newline="\n")
        before = toml.read_bytes()
        capsys.readouterr()

        assert main(["workbench", "drop", "claude"]) == 1

        assert toml.read_bytes() == before
        assert "unexpected shape; nothing was changed" in _out(capsys)
