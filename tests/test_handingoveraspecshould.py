from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext

_SPEC = "SPEC_0001_LOGS_ROTATE"
_RULES = "# Rules\n- **Tests:** name them after the user's action.\n"
_SECTION_5 = "- **Branches:** SPEC branches start from `develop`.\n"


def _atlas(world: EphemeralAtlasContext, monkeypatch, capsys, plugin: str | None = None, start: bool = True) -> Path:
    atlas = world.atlas
    monkeypatch.chdir(atlas)
    assert main(["init"]) == 0
    if plugin:
        assert main(["plugin", "add", "coding-rules", plugin]) == 0
    assert main(["spec", "new", "LOGS_ROTATE"]) == 0
    path = atlas / f"{_SPEC}.md"
    path.write_text(
        "# SPEC_0001_LOGS_ROTATE\ncreated: 2026-01-01\nrepos: log-daemon\n\n## What\nRotate the logs.\n\n"
        "## Acceptance\n- Old logs go.\n\n## Out of scope\n- Compression.\n\n## Plan\n1. The rotation,\n   with its tests.\n2. The docs.\n",
        encoding="utf-8", newline="\n",
    )
    claude = atlas / "AGENTS.md"
    claude.write_text(claude.read_text(encoding="utf-8").replace("- _(empty — fill in as conventions get decided.)_\n", _SECTION_5), encoding="utf-8", newline="\n")
    if start:
        assert main(["spec", "start", _SPEC]) == 0
    capsys.readouterr()
    return atlas


def _brief(capsys, *args: str) -> tuple[int, str]:
    code = main(["handover", _SPEC, *args])
    return code, capsys.readouterr().out


def test_build_the_brief_from_the_spec_the_block_and_the_conventions(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch, capsys, plugin="file:RULES.md")
        (atlas / "RULES.md").write_text(_RULES, encoding="utf-8", newline="\n")

        code, out = _brief(capsys)

    assert code == 0
    order = ["## What\nRotate the logs.", "## Acceptance\n- Old logs go.", "## Out of scope\n- Compression.", "## Plan\n1. The rotation,",
             "## Repos and mode\nRepos: log-daemon\nBranch in each: `spec/0001-logs-rotate`\nMode:", "## Where it stands\n- Done: —\n- Next: step 1",
             "## This Atlas's conventions\n- **Branches:**", "## Coding rules\n# Rules\n- **Tests:**", "## How to work", "## Report expected"]
    positions = [out.index(piece) for piece in order]
    assert positions == sorted(positions)
    assert "never implement around it" in out and "install nothing" in out and "Leave the work staged" in out
    assert "Claude" not in out


def test_hand_over_one_step_with_the_plan_for_context(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        _atlas(world, monkeypatch, capsys)

        code, out = _brief(capsys, "--step", "2")

    assert code == 0
    assert "step 2" in out.splitlines()[0]
    assert "## The step\n2. The docs.\n\nThe whole Plan, for context:\n1. The rotation,\n   with its tests.\n2. The docs." in out
    assert "Branch in each: `spec/0001-logs-rotate`" in out
    assert "## Plan\n" not in out


def test_refuse_a_step_the_plan_does_not_have(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        _atlas(world, monkeypatch, capsys)

        code, out = _brief(capsys, "--step", "7")

    assert code == 1
    assert out == f"{_SPEC} has no step 7 in its Plan.\n"


def test_leave_a_slot_for_rules_the_cli_cannot_query(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        _atlas(world, monkeypatch, capsys, plugin="mcp:coco")

        code, out = _brief(capsys)

    assert code == 0
    assert "## Coding rules\nThe rules come from `mcp:coco`, which this command cannot query.\n<<the principal pastes here" in out


def test_take_the_recalled_rules_from_a_file(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch, capsys, plugin="mcp:coco")
        recalled = atlas.parent / "recalled.md"
        recalled.write_text("- [abc123] Tests read as user scenarios.\n", encoding="utf-8", newline="\n")

        code, out = _brief(capsys, "--rules", str(recalled))

    assert code == 0
    assert "## Coding rules\n- [abc123] Tests read as user scenarios." in out
    assert "<<the principal pastes here" not in out


def test_say_so_without_a_coding_rules_source(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        _atlas(world, monkeypatch, capsys)

        code, out = _brief(capsys)

    assert code == 0
    assert "## Coding rules\nThis Atlas declares no coding-rules source." in out


def test_carry_the_candidate_rules_in_force(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch, capsys, plugin="file:RULES.md")
        (atlas / "RULES.md").write_text(_RULES, encoding="utf-8", newline="\n")
        candidates = atlas / "CODING_RULES_CANDIDATES.md"
        candidates.write_text(candidates.read_text(encoding="utf-8").replace("## Open\n_(empty)_\n", "## Open\n- **Candidate:** keep helpers in tests/.\n"), encoding="utf-8", newline="\n")

        code, out = _brief(capsys)

    assert code == 0
    assert "### Candidate rules of this Atlas, not yet in the source" in out and "keep helpers in tests/" in out
    assert "### Deviations in force" not in out


def test_refuse_a_spec_that_is_not_active_unless_told(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        _atlas(world, monkeypatch, capsys, start=False)

        code, out = _brief(capsys)
        assert code == 1
        assert out == f"{_SPEC} is not in STATUS.md Active (--any to hand it over anyway).\n"

        code, out = _brief(capsys, "--any")

    assert code == 0
    assert "## Where it stands" not in out


def test_write_the_brief_to_a_file(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch, capsys)
        target = atlas.parent / "brief.md"

        code, out = _brief(capsys, "--out", str(target))

        text = target.read_text(encoding="utf-8")
    assert code == 0
    assert out == f"wrote {target}\n"
    assert text.startswith(f"# Hand-over: {_SPEC}")


def test_refuse_a_spec_it_does_not_know(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        _atlas(world, monkeypatch, capsys)

        code = main(["handover", "SPEC_0009_NOWHERE"])

    assert code == 1
    assert capsys.readouterr().out == "SPEC_0009_NOWHERE is not a SPEC of this Atlas.\n"


def test_refuse_outside_an_atlas(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["handover", _SPEC]) == 1

    assert "not an Atlas" in capsys.readouterr().out


def test_keep_a_step_s_own_lines_and_accept_parenthesis_numbering(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch, capsys)
        path = atlas / f"{_SPEC}.md"
        text = path.read_text(encoding="utf-8").split("## Plan")[0] + "## Plan\n1) First step.\n   - sub a\n   - sub b\n2) Second step\n   continued here.\n\n   A paragraph of step 2.\n"
        path.write_text(text, encoding="utf-8", newline="\n")

        code, first = _brief(capsys, "--step", "1")
        assert code == 0
        code, second = _brief(capsys, "--step", "2")

    assert "## The step\n1) First step.\n   - sub a\n   - sub b\n\nThe whole Plan" in first
    assert "## The step\n2) Second step\n   continued here.\n\n   A paragraph of step 2.\n\nThe whole Plan" in second


def test_keep_conventions_written_as_prose(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch, capsys)
        claude = atlas / "AGENTS.md"
        claude.write_text(claude.read_text(encoding="utf-8").replace(_SECTION_5, "We always branch from develop.\nA list never ends at `_(empty)_`.\n"), encoding="utf-8", newline="\n")

        code, out = _brief(capsys)

    assert code == 0
    assert "## This Atlas's conventions\nWe always branch from develop.\nA list never ends at `_(empty)_`." in out
    assert "_Rules that apply" not in out


def test_say_none_when_section_5_is_the_template_s(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch, capsys)
        claude = atlas / "AGENTS.md"
        claude.write_text(claude.read_text(encoding="utf-8").replace(_SECTION_5, "- _(empty — fill in as conventions get decided.)_\n"), encoding="utf-8", newline="\n")

        _code, out = _brief(capsys)

    assert "## This Atlas's conventions\n_(none declared)_" in out


def test_refuse_a_rules_file_it_cannot_read_and_an_output_it_cannot_write(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch, capsys, plugin="mcp:coco")

        code, out = _brief(capsys, "--rules", str(atlas.parent / "missing.md"))
        assert code == 1
        assert out.startswith("Cannot read ") and "missing.md" in out

        code, out = _brief(capsys, "--out", str(atlas.parent / "no-such-folder" / "brief.md"))

    assert code == 1
    assert out.startswith("Cannot write ")


def test_leave_out_a_rules_file_that_escapes_the_atlas(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch, capsys, plugin="file:RULES.md")
        (atlas.parent / "outside.md").write_text("secret\n", encoding="utf-8")
        toml = atlas / "_settings/atlas.toml"
        toml.write_text(toml.read_text(encoding="utf-8").replace('source = "file:RULES.md"', 'source = "file:../outside.md"'), encoding="utf-8", newline="\n")

        code, out = _brief(capsys)

    assert code == 0
    assert "secret" not in out
    assert "The coding-rules file `../outside.md` is outside the Atlas and was not read." in out


def test_say_when_the_recalled_rules_were_not_used(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch, capsys, plugin="file:RULES.md")
        (atlas / "RULES.md").write_text(_RULES, encoding="utf-8", newline="\n")
        recalled = atlas.parent / "recalled.md"
        recalled.write_text("- x\n", encoding="utf-8")

        _code, out = _brief(capsys, "--rules", str(recalled))

    assert "was not used: this Atlas's rules come from file:RULES.md" in out


def test_say_plainly_when_no_default_mode_is_declared(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        _atlas(world, monkeypatch, capsys)

        _code, out = _brief(capsys)

    assert "Mode: not stated (the SPEC has no mode: line and the orientation file declares no default)" in out
