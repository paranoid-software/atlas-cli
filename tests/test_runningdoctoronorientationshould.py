import shlex
from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext

_FILLED_BLOCK = (
    "### log-daemon — core product\n"
    "- **Contributes:** Collects the logs.\n"
    "- **Stack:** Python.\n"
    "- **Cadence:** tagged releases.\n"
)


def _init(context: EphemeralAtlasContext, monkeypatch) -> Path:
    monkeypatch.chdir(context.atlas)
    assert main(["init"]) == 0
    return context.atlas


def _link(context: EphemeralAtlasContext, *names: str) -> None:
    for name in names:
        assert main(["link", name, str(context.source(name))]) == 0


def _write_claude_md(atlas: Path, section_one: str) -> None:
    (atlas / "AGENTS.md").write_text(
        "# acme Atlas — agent instructions\n\n"
        "## 1. What lives here — sources and their purposes\n\n"
        f"{section_one}\n"
        "## 2. How I work in this Atlas\n"
        "- <Atlas-specific tooling notes — environment naming, dev-server entrypoints>\n",
        encoding="utf-8",
        newline="\n",
    )


def _doctor(capsys) -> tuple[int, str]:
    capsys.readouterr()
    code = main(["doctor"])
    return code, capsys.readouterr().out


def test_flag_a_source_with_no_block(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        _write_claude_md(atlas, "_(no sources yet)_\n")

        code, out = _doctor(capsys)

    assert code == 1
    assert out == "ok log-daemon\nunoriented log-daemon\n"


def test_flag_a_block_that_still_carries_placeholders(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        _write_claude_md(
            atlas,
            "### log-daemon — <role: core product | reference | infrastructure | tooling>\n"
            "- **Contributes:** <one paragraph>\n"
            "- **Stack:** Python.\n"
            "- **Cadence:** <how it releases — or \"reference only: read, don't modify\">\n",
        )

        code, out = _doctor(capsys)

    assert code == 1
    assert out == (
        "ok log-daemon\n"
        "placeholder log-daemon: "
        "<role: core product | reference | infrastructure | tooling>, "
        "<one paragraph>, "
        "<how it releases — or \"reference only: read, don't modify\">\n"
    )


def test_say_nothing_about_a_filled_block(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        _write_claude_md(atlas, _FILLED_BLOCK)

        code, out = _doctor(capsys)

    assert code == 0
    assert out == "ok log-daemon\n"


def test_judge_a_block_up_to_the_next_heading_of_the_same_or_higher_level(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon", "notes"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon", "notes")
        _write_claude_md(
            atlas,
            _FILLED_BLOCK
            + "#### Detail\n"
            + "- still log-daemon's block: <left behind>\n"
            + "\n"
            + "### notes — reference\n"
            + "- **Contributes:** Notes.\n"
            + "- **Stack:** Markdown.\n"
            + "- **Cadence:** reference only.\n",
        )

        code, out = _doctor(capsys)

    assert code == 1
    assert out == "ok log-daemon\nplaceholder log-daemon: <left behind>\nok notes\n"


def test_report_a_missing_claude_md_once_and_judge_no_block(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon", "notes"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon", "notes")
        (atlas / "AGENTS.md").unlink()

        code, out = _doctor(capsys)

    assert code == 1
    assert out == "ok log-daemon\nok notes\nmissing AGENTS.md\n"


def test_match_the_block_by_the_exact_name(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["src1"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "src1")
        _write_claude_md(
            atlas,
            "### SRC1 — core product\n"
            "- **Contributes:** The other one.\n"
            "- **Stack:** Python.\n"
            "- **Cadence:** tagged releases.\n",
        )

        code, out = _doctor(capsys)

    assert code == 1
    assert out == "ok src1\nunoriented src1\n"


def test_look_for_the_block_in_section_one_only(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        (atlas / "AGENTS.md").write_text(
            "# acme Atlas — agent instructions\n\n"
            "## 1. What lives here — sources and their purposes\n\n"
            "_(no sources yet)_\n\n"
            "## 3. acme — product / architecture\n\n" + _FILLED_BLOCK,
            encoding="utf-8",
            newline="\n",
        )

        code, out = _doctor(capsys)

    assert code == 1
    assert out == "ok log-daemon\nunoriented log-daemon\n"


def test_print_each_orientation_finding_after_its_source_lines(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon", "notes"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon", "notes")
        (atlas / "notes").unlink()
        _write_claude_md(
            atlas,
            "### log-daemon — core product\n"
            "- **Contributes:** <one paragraph>\n"
            "- **Stack:** Python.\n"
            "- **Cadence:** tagged releases.\n",
        )
        (atlas / "scratch").symlink_to(context.source("log-daemon"), target_is_directory=True)
        target = shlex.quote(str((atlas / "scratch").readlink()))

        code, out = _doctor(capsys)

    assert code == 1
    assert out == (
        "ok log-daemon\n"
        "placeholder log-daemon: <one paragraph>\n"
        "missing notes\n"
        "atlas link notes <path>\n"
        "unoriented notes\n"
        "undeclared scratch\n"
        f"atlas link scratch {target}\n"
    )


def test_take_angle_brackets_in_code_for_code_not_placeholders(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        _write_claude_md(
            atlas,
            "### log-daemon — core product\n"
            "- **Contributes:** Collects the logs; run it with `atlas link <name> <path>`.\n"
            "- **Stack:** Python.\n"
            "- **Cadence:** images tagged `yyyymmdd.<run>`:\n"
            "\n"
            "```\n"
            "### not a heading — <not a placeholder>\n"
            "```\n",
        )

        code, out = _doctor(capsys)

    assert code == 0
    assert out == "ok log-daemon\n"
