import subprocess
from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext

_STATUS_HEAD = "# acme — STATUS (living)\n\n## Active\n"
_STATUS_TAIL = "\n## Recently closed\n- SPEC_0001_START → _archived/ (2026-10-01)\n"


def _init(context: EphemeralAtlasContext, monkeypatch) -> Path:
    monkeypatch.chdir(context.atlas)
    assert main(["init"]) == 0
    return context.atlas


def _link(context: EphemeralAtlasContext, *names: str) -> None:
    for name in names:
        assert main(["link", name, str(context.source(name))]) == 0


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _git(source: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(source), *args], check=True, capture_output=True)


def _status(capsys) -> str:
    capsys.readouterr()
    assert main(["status"]) == 0
    return capsys.readouterr().out


def test_list_the_active_specs_with_their_lines(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(atlas / "SPEC_0002_FIRST.md", "# SPEC_0002_FIRST\nrepos: atlas\n")
        _write(atlas / "SPEC_0003_SECOND.md", "# SPEC_0003_SECOND\nrepos: atlas\n")
        _write(
            atlas / "STATUS.md",
            _STATUS_HEAD
            + "\n### SPEC_0002_FIRST — IN PROGRESS\n"
            + "- **Done:** step 1.\n"
            + "- **Next:** step 2.\n"
            + "- loose note\n"
            + "\n### SPEC_0003_SECOND — PAUSED\n"
            + "- **Paused:** waiting.\n"
            + "- **Blocked:** on review.\n"
            + _STATUS_TAIL,
        )

        out = _status(capsys)

    assert out.split("Sources\n")[0] == (
        "SPECs\n"
        "  SPEC_0002_FIRST — IN PROGRESS\n"
        "    - **Done:** step 1.\n"
        "    - **Next:** step 2.\n"
        "  SPEC_0003_SECOND — PAUSED\n"
        "    - **Paused:** waiting.\n"
        "    - **Blocked:** on review.\n"
    )


def test_flag_a_spec_listed_in_more_than_one_place(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(atlas / "SPEC_0012_X.md", "# SPEC_0012_X\nrepos: atlas\n")
        _write(atlas / "BACKLOG.md", "# acme — BACKLOG\n\n## Open\n- SPEC_0012_X — something\n")
        _write(atlas / "STATUS.md", _STATUS_HEAD + "\n### SPEC_0012_X — IN PROGRESS\n" + _STATUS_TAIL)

        out = _status(capsys)

    assert "  ! SPEC_0012_X: in the backlog and Active\n" in out


def test_flag_a_spec_that_is_also_archived(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(atlas / "SPEC_0012_X.md", "# SPEC_0012_X\nrepos: atlas\n")
        _write(atlas / "_archived" / "SPEC_0012_X.md", "# SPEC_0012_X\nrepos: atlas\n")
        _write(atlas / "STATUS.md", _STATUS_HEAD + "\n### SPEC_0012_X — IN PROGRESS\n" + _STATUS_TAIL)

        out = _status(capsys)

    assert "  ! SPEC_0012_X: in Active and _archived/\n" in out


def test_flag_a_root_spec_in_neither_the_backlog_nor_active(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(atlas / "SPEC_0013_Y.md", "# SPEC_0013_Y\nrepos: atlas\n")

        out = _status(capsys)

    assert out.split("Sources\n")[0] == (
        "SPECs\n"
        "  ! SPEC_0013_Y: at the root but in neither the backlog nor Active\n"
    )


def test_flag_an_active_spec_whose_file_is_not_at_the_root(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(atlas / "STATUS.md", _STATUS_HEAD + "\n### SPEC_0014_Z — IN PROGRESS\n" + _STATUS_TAIL)

        out = _status(capsys)

    assert out.split("Sources\n")[0] == (
        "SPECs\n"
        "  SPEC_0014_Z — IN PROGRESS\n"
        "  ! SPEC_0014_Z: in Active but its file is not at the root\n"
    )


def test_flag_a_backlog_spec_whose_file_is_not_at_the_root(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(atlas / "BACKLOG.md", "# acme — BACKLOG\n\n## Open\n- SPEC_0015_W — later\n")

        out = _status(capsys)

    assert "  ! SPEC_0015_W: in the backlog but its file is not at the root\n" in out


def test_ignore_findings_files(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(atlas / "SPEC_0012_X.md", "# SPEC_0012_X\nrepos: atlas\n")
        _write(atlas / "SPEC_0012_FINDINGS.md", "# SPEC_0012 findings\n")
        _write(atlas / "_archived" / "SPEC_0001_FINDINGS.md", "# SPEC_0001 findings\n")
        _write(atlas / "STATUS.md", _STATUS_HEAD + "\n### SPEC_0012_X — IN PROGRESS\n" + _STATUS_TAIL)

        out = _status(capsys)

    assert out.split("Sources\n")[0] == "SPECs\n  SPEC_0012_X — IN PROGRESS\n"


def test_say_a_source_is_on_the_active_specs_branch(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["atlas-cli"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "atlas-cli")
        _git(context.source("atlas-cli"), "switch", "-q", "-c", "spec/0008-cli-status")
        _write(atlas / "SPEC_0008_CLI_STATUS.md", "# SPEC_0008_CLI_STATUS\nrepos: atlas-cli, atlas\n")
        _write(atlas / "STATUS.md", _STATUS_HEAD + "\n### SPEC_0008_CLI_STATUS — IN PROGRESS\n" + _STATUS_TAIL)

        out = _status(capsys)

    assert "Sources\n  atlas-cli: spec/0008-cli-status, 0 changed — on SPEC_0008's branch\nPaused\n" in out


def test_say_a_source_is_not_on_the_active_specs_branch(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["atlas-cli"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "atlas-cli")
        _write(atlas / "SPEC_0008_CLI_STATUS.md", "# SPEC_0008_CLI_STATUS\nrepos: atlas, atlas-cli\n")
        _write(atlas / "STATUS.md", _STATUS_HEAD + "\n### SPEC_0008_CLI_STATUS — IN PROGRESS\n" + _STATUS_TAIL)

        out = _status(capsys)

    assert "  atlas-cli: main, 0 changed — not on SPEC_0008's branch (spec/0008-…)\n" in out


def test_leave_out_the_branch_check_for_a_source_no_active_spec_touches(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["atlas-cli"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "atlas-cli")
        _write(atlas / "SPEC_0008_CLI_STATUS.md", "# SPEC_0008_CLI_STATUS\nrepos: atlas\n")
        _write(atlas / "STATUS.md", _STATUS_HEAD + "\n### SPEC_0008_CLI_STATUS — IN PROGRESS\n" + _STATUS_TAIL)

        out = _status(capsys)

    assert "  atlas-cli: main, 0 changed\n" in out


def test_count_staged_unstaged_and_untracked_changes(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["atlas-cli"]) as context:
        _init(context, monkeypatch)
        _link(context, "atlas-cli")
        source = context.source("atlas-cli")
        (source / "README").write_text("changed\n", encoding="utf-8")
        (source / "staged.txt").write_text("staged\n", encoding="utf-8")
        _git(source, "add", "staged.txt")
        (source / "untracked.txt").write_text("untracked\n", encoding="utf-8")

        out = _status(capsys)

    assert "Sources\n  atlas-cli: main, 3 changed\nPaused\n" in out


def test_say_a_source_is_not_a_git_repo(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["docs"]) as context:
        _init(context, monkeypatch)
        _link(context, "docs")

        out = _status(capsys)

    assert "Sources\n  docs: not a git repo\nPaused\n" in out


def test_report_a_missing_source(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        (atlas / "log-daemon").unlink()

        out = _status(capsys)

    assert "Sources\n  log-daemon: missing\nPaused\n" in out


def test_report_a_broken_source(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["old"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "old")
        (atlas / "old").unlink()
        (atlas / "old").symlink_to(context.root / "gone")

        out = _status(capsys)

    assert "Sources\n  old: broken\nPaused\n" in out


def test_list_sources_in_declaration_order(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["zeta", "alpha"], plain_sources=["docs"]) as context:
        _init(context, monkeypatch)
        _link(context, "zeta", "docs", "alpha")

        out = _status(capsys)

    assert "Sources\n  zeta: main, 0 changed\n  docs: not a git repo\n  alpha: main, 0 changed\nPaused\n" in out


def test_list_a_paused_stash(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["atlas-cli"]) as context:
        _init(context, monkeypatch)
        _link(context, "atlas-cli")
        source = context.source("atlas-cli")
        (source / "README").write_text("paused work\n", encoding="utf-8")
        _git(source, "stash", "push", "-m", "SPEC_0007 paused")
        (source / "README").write_text("other work\n", encoding="utf-8")
        _git(source, "stash", "push", "-m", "just a stash")

        out = _status(capsys)

    assert out.endswith("Paused\n  atlas-cli: stash@{1} — SPEC_0007\n")


def test_print_none_in_every_empty_section(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        _init(context, monkeypatch)

        out = _status(capsys)

    assert out == "SPECs\n  (none)\nSources\n  (none)\nPaused\n  (none)\n"


def test_write_nothing(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["atlas-cli"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "atlas-cli")
        _write(atlas / "STATUS.md", _STATUS_HEAD + "\n### SPEC_0014_Z — IN PROGRESS\n" + _STATUS_TAIL)
        before = {
            str(path): path.read_bytes() for path in atlas.rglob("*") if path.is_file() and not path.is_symlink()
        }

        _status(capsys)

        after = {
            str(path): path.read_bytes() for path in atlas.rglob("*") if path.is_file() and not path.is_symlink()
        }

    assert after == before


def test_refuse_when_the_folder_is_not_an_atlas(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["status"]) == 1

    assert capsys.readouterr().out == "This folder is not an Atlas (no _settings/atlas.toml).\n"
    assert list(tmp_path.iterdir()) == []
