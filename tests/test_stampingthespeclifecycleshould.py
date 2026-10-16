from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext

_STATUS_HEAD = "# acme — STATUS (living)\n\n## Active\n"
_STATUS_TAIL = "\n## Recently closed\n- SPEC_0001_START → _archived/ (2026-10-01)\n"


def _init(context: EphemeralAtlasContext, monkeypatch) -> Path:
    monkeypatch.chdir(context.atlas)
    assert main(["init"]) == 0
    return context.atlas


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _status(capsys) -> str:
    capsys.readouterr()
    assert main(["status"]) == 0
    return capsys.readouterr().out


def _spec_warnings(out: str) -> list[str]:
    section = out.split("Sources\n")[0]
    return [line for line in section.splitlines() if line.startswith("  !")]


def test_flag_an_active_spec_without_started(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(atlas / "SPEC_0002_FIRST.md", "# SPEC_0002_FIRST\ncreated: 2026-10-16\nrepos: atlas\n")
        _write(atlas / "STATUS.md", _STATUS_HEAD + "\n### SPEC_0002_FIRST — IN PROGRESS\n" + _STATUS_TAIL)

        out = _status(capsys)

    assert _spec_warnings(out) == ["  ! SPEC_0002_FIRST: in Active without started:"]


def test_say_nothing_about_an_active_spec_with_started(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(
            atlas / "SPEC_0002_FIRST.md",
            "# SPEC_0002_FIRST\ncreated: 2026-10-16\nstarted: 2026-10-16\nrepos: atlas\n",
        )
        _write(atlas / "STATUS.md", _STATUS_HEAD + "\n### SPEC_0002_FIRST — IN PROGRESS\n" + _STATUS_TAIL)

        out = _status(capsys)

    assert _spec_warnings(out) == []


def test_count_the_archived_specs_without_closed(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(atlas / "_archived" / "SPEC_0002_ONE.md", "# SPEC_0002_ONE\ncreated: 2026-10-01\nrepos: atlas\n")
        _write(atlas / "_archived" / "SPEC_0003_TWO.md", "# SPEC_0003_TWO\ncreated: 2026-10-01\nrepos: atlas\n")
        _write(
            atlas / "_archived" / "SPEC_0004_THREE.md",
            "# SPEC_0004_THREE\ncreated: 2026-10-01\nclosed: 2026-10-02\nrepos: atlas\n",
        )

        out = _status(capsys)

    assert _spec_warnings(out) == ["  ! 2 archived SPECs without closed:"]


def test_say_one_archived_spec_without_closed(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(atlas / "_archived" / "SPEC_0002_ONE.md", "# SPEC_0002_ONE\ncreated: 2026-10-01\nrepos: atlas\n")

        out = _status(capsys)

    assert _spec_warnings(out) == ["  ! 1 archived SPEC without closed:"]


def test_ignore_findings_files_in_the_archive(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(
            atlas / "_archived" / "SPEC_0002_ONE.md",
            "# SPEC_0002_ONE\ncreated: 2026-10-01\nclosed: 2026-10-02\nrepos: atlas\n",
        )
        _write(atlas / "_archived" / "SPEC_0002_FINDINGS.md", "# SPEC_0002 — findings\n")

        out = _status(capsys)

    assert _spec_warnings(out) == []


def test_flag_a_stamp_that_is_not_a_date(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(
            atlas / "SPEC_0002_FIRST.md",
            "# SPEC_0002_FIRST\ncreated: 2026-10-16\nstarted: yesterday\nrepos: atlas\n",
        )
        _write(atlas / "STATUS.md", _STATUS_HEAD + "\n### SPEC_0002_FIRST — IN PROGRESS\n" + _STATUS_TAIL)

        out = _status(capsys)

    assert _spec_warnings(out) == ["  ! SPEC_0002_FIRST: started: is not a date"]


def test_ignore_a_stamp_written_below_the_header(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(
            atlas / "_archived" / "SPEC_0002_ONE.md",
            "# SPEC_0002_ONE\ncreated: 2026-10-01\nrepos: atlas\n\n## What\nclosed: not-a-date\n",
        )

        out = _status(capsys)

    assert _spec_warnings(out) == ["  ! 1 archived SPEC without closed:"]


def test_say_nothing_when_every_spec_is_stamped(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _init(context, monkeypatch)
        _write(
            atlas / "SPEC_0002_FIRST.md",
            "# SPEC_0002_FIRST\ncreated: 2026-10-16\nstarted: 2026-10-16\nrepos: atlas\n",
        )
        _write(
            atlas / "_archived" / "SPEC_0001_DONE.md",
            "# SPEC_0001_DONE\ncreated: 2026-10-01\nclosed: 2026-10-02\nrepos: atlas\n",
        )
        _write(atlas / "STATUS.md", _STATUS_HEAD + "\n### SPEC_0002_FIRST — IN PROGRESS\n" + _STATUS_TAIL)

        out = _status(capsys)

    assert _spec_warnings(out) == []
