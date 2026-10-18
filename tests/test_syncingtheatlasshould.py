from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext, orient_sources

_SPEC = "SPEC_0001_LOGS_ROTATE"


def _atlas(world: EphemeralAtlasContext, monkeypatch, *sources: str) -> Path:
    monkeypatch.chdir(world.atlas)
    assert main(["init"]) == 0
    for name in sources:
        assert main(["link", name, str(world.source(name))]) == 0
    orient_sources(world.atlas, *sources)
    return world.atlas


def _spec(atlas: Path, capsys) -> Path:
    capsys.readouterr()
    assert main(["spec", "new", "LOGS_ROTATE"]) == 0
    capsys.readouterr()
    return atlas / f"{_SPEC}.md"


def _out(capsys) -> str:
    return capsys.readouterr().out


def _tree(folder: Path) -> dict[str, bytes]:
    return {str(path.relative_to(folder)): path.read_bytes() for path in sorted(folder.rglob("*")) if path.is_file()}


def test_stamp_an_active_spec_that_has_no_started(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        path = _spec(atlas, capsys)
        status = atlas / "STATUS.md"
        status.write_text(status.read_text(encoding="utf-8").replace("never appended)_\n", f"never appended)_\n\n### {_SPEC} — IN PROGRESS\n- **Next:** go\n"), encoding="utf-8", newline="\n")

        assert main(["sync"]) == 0

        assert path.read_text(encoding="utf-8").splitlines()[2].startswith("started: ")
        assert f"wrote\n  {_SPEC}.md: started: " in _out(capsys)


def test_stamp_an_archived_spec_that_has_no_closed(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        old = atlas / "_archived" / "SPEC_0002_OLD.md"
        old.write_text("# SPEC_0002_OLD\ncreated: 2026-01-01\nstarted: 2026-01-02\nrepos: x\n\n## What\nx\n", encoding="utf-8", newline="\n")

        assert main(["sync"]) == 0

        assert old.read_text(encoding="utf-8").splitlines()[3].startswith("closed: ")
        assert "_archived/SPEC_0002_OLD.md: closed: " in _out(capsys)


def test_move_a_closed_spec_still_in_active_to_recently_closed(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        (atlas / "_archived" / "SPEC_0002_OLD.md").write_text("# SPEC_0002_OLD\ncreated: 2026-01-01\nclosed: 2026-01-09\n\n## What\nx\n", encoding="utf-8", newline="\n")
        status = atlas / "STATUS.md"
        status.write_text(status.read_text(encoding="utf-8").replace("never appended)_\n", "never appended)_\n\n### SPEC_0002_OLD — IN REVIEW\n- **Next:** close\n"), encoding="utf-8", newline="\n")

        assert main(["sync"]) == 0

        text = status.read_text(encoding="utf-8")
        assert "### SPEC_0002_OLD" not in text
        assert "never appended)_\n\n_(none)_\n\n## Recently closed" in text
        assert "lives there)_\n- SPEC_0002_OLD → _archived/ (2026-01-09)\n" in text
        assert "STATUS.md: SPEC_0002_OLD out of Active, into Recently closed" in _out(capsys)


def test_report_a_spec_that_is_nowhere_placed(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _spec(atlas, capsys)
        backlog = atlas / "BACKLOG.md"
        backlog.write_text(backlog.read_text(encoding="utf-8").replace(f"- {_SPEC}", "- SPEC_0009_GHOST"), encoding="utf-8", newline="\n")

        assert main(["sync"]) == 0

        out = _out(capsys)
    assert f"{_SPEC}.md is at the root but in neither the backlog nor Active" in out
    assert "SPEC_0009_GHOST is listed but its file is nowhere" in out


def test_write_nothing_and_say_so_with_check(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        path = _spec(atlas, capsys)
        status = atlas / "STATUS.md"
        status.write_text(status.read_text(encoding="utf-8").replace("never appended)_\n", f"never appended)_\n\n### {_SPEC} — IN PROGRESS\n- **Next:** go\n"), encoding="utf-8", newline="\n")
        before = _tree(atlas)

        code = main(["sync", "--check"])

        assert code == 1
        assert _tree(atlas) == before
        assert f"would write\n  {_SPEC}.md: started: " in _out(capsys)
        assert "started:" not in path.read_text(encoding="utf-8")


def test_do_nothing_when_there_is_nothing_to_do(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _atlas(world, monkeypatch, "log-daemon")
        path = _spec(atlas, capsys)
        assert main(["spec", "start", _SPEC]) == 0
        before = _tree(atlas)
        capsys.readouterr()

        assert main(["sync"]) == 0
        assert main(["sync", "--check"]) == 0

        assert _tree(atlas) == before
        out = _out(capsys)
        assert path.read_text(encoding="utf-8").count("started:") == 1
    assert "doctor\n  ok log-daemon\n" in out
    assert "wrote\n  (nothing)\n" in out
    assert "status\n  SPECs\n" in out


def test_return_1_while_the_lint_finds_something(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        path = _spec(atlas, capsys)
        path.write_text(path.read_text(encoding="utf-8") + "\n- [ ] a checkbox\n", encoding="utf-8", newline="\n")

        assert main(["sync"]) == 1

        assert f"lint\n  {_SPEC}: a checkbox" in _out(capsys)


def test_refuse_outside_an_atlas(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["sync"]) == 1

    assert "not an Atlas" in _out(capsys)
    assert list(tmp_path.iterdir()) == []


def test_report_an_unreadable_spec_instead_of_crashing(monkeypatch, capsys):
    import os
    import stat

    if os.name == "nt" or os.geteuid() == 0:
        return
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        path = _spec(atlas, capsys)
        assert main(["spec", "start", _SPEC]) == 0
        path.chmod(0)
        try:
            capsys.readouterr()
            code = main(["sync", "--check"])
            out = _out(capsys)
        finally:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert code == 1
    assert f"reports\n  {_SPEC}.md cannot be read" in out
    assert "would write\n  (nothing)" in out


def test_leave_a_root_copy_of_an_archived_spec_alone_and_report_it(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        path = _spec(atlas, capsys)
        (atlas / "_archived" / f"{_SPEC}.md").write_text(path.read_text(encoding="utf-8").replace("created:", "closed: 2026-01-09\ncreated:"), encoding="utf-8", newline="\n")
        status = atlas / "STATUS.md"
        status.write_text(status.read_text(encoding="utf-8").replace("never appended)_\n", f"never appended)_\n\n### {_SPEC} — IN REVIEW\n- **Next:** close\n"), encoding="utf-8", newline="\n")
        backlog = atlas / "BACKLOG.md"
        backlog.write_text(backlog.read_text(encoding="utf-8").replace(f"- {_SPEC}", "- SPEC_0002_OTHER"), encoding="utf-8", newline="\n")

        assert main(["sync"]) == 0

        out = _out(capsys)
        assert "started:" not in path.read_text(encoding="utf-8")
    assert f"STATUS.md: {_SPEC} out of Active" in out
    assert f"{_SPEC}.md is at the root but in neither the backlog nor Active" in out


def test_return_1_when_the_atlas_cannot_be_read(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        (atlas / "_settings/atlas.toml").write_text("sources = 3\n", encoding="utf-8")

        assert main(["sync"]) == 1

        assert "doctor\n  Cannot read _settings/atlas.toml" in _out(capsys)


def test_label_in_check_mode_what_it_would_fix(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        (atlas / "_archived" / "SPEC_0002_OLD.md").write_text("# SPEC_0002_OLD\ncreated: 2026-01-01\n\n## What\nx\n", encoding="utf-8", newline="\n")

        assert main(["sync", "--check"]) == 1

        assert "SPEC_0002_OLD: archived without closed: (sync would fix it)" in _out(capsys)
