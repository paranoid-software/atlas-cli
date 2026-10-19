import json
import os
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import pytest

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="session-orient.sh needs jq (a README prerequisite)")

_HOOK = files("atlas_cli").joinpath("machinery", "claude", "hooks", "session-orient.sh")

_CANDIDATE = """- **Candidate:** Name test files after the user's action.
- **Why it generalizes:** every project has users.
- **Source:** SPEC_0001.
"""


def _run_hook(atlas: Path, path: str | None = None) -> subprocess.CompletedProcess:
    # The hook calls whatever `atlas` is on PATH: the one of this environment, not the machine's.
    env = {**os.environ, "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}" if path is None else path}
    return subprocess.run(["bash", str(_HOOK)], cwd=atlas, capture_output=True, text=True, encoding="utf-8", check=True, env=env)


def _context(atlas: Path) -> str:
    return json.loads(_run_hook(atlas).stdout)["hookSpecificOutput"]["additionalContext"]


def _orient(atlas: Path, monkeypatch, capsys) -> tuple[int, str]:
    monkeypatch.chdir(atlas)
    capsys.readouterr()
    code = main(["orient"])
    return code, capsys.readouterr().out.rstrip("\n")


def _stage_candidate(atlas: Path) -> None:
    path = atlas / "CODING_RULES_CANDIDATES.md"
    text = path.read_text(encoding="utf-8").replace("## Open\n_(empty)_\n", f"## Open\n{_CANDIDATE}")
    path.write_text(text, encoding="utf-8", newline="\n")


def test_say_what_each_store_is_for(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0

        context = _context(world.atlas)

        paragraphs = context.split("\n\n")
        assert paragraphs[0].startswith("SESSION START — ")
        stores = paragraphs[1]
        assert stores.startswith("STORES — ")
        assert "AGENTS.md at the Atlas root is this project's orientation" in stores
        assert "CODING_RULES_CANDIDATES.md holds rules this Atlas already applies" in stores
        assert "A source may carry its own rule files" in stores
        assert "the Atlas and the coding rules prevail" in stores


def test_bring_the_candidate_rules_in_force(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["plugin", "add", "coding-rules", "file:RULES.md"]) == 0
        _stage_candidate(world.atlas)

        context = _context(world.atlas)

        block = context.split("=== CODING_RULES_CANDIDATES.md — candidate rules in force here ===\n")[1]
        assert "Name test files after the user's action." in block
        assert context.index("CODING_RULES_CANDIDATES.md — candidate rules") < context.index(
            "CODING_RULES_DEVIATIONS.md — deviations in force"
        )


def test_leave_out_the_candidates_file_when_nothing_is_open(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["plugin", "add", "coding-rules", "file:RULES.md"]) == 0

        context = _context(world.atlas)

        assert "candidate rules in force here" not in context
        assert "=== CODING_RULES_DEVIATIONS.md — deviations in force ===" in context


def test_leave_out_the_candidates_file_when_its_entries_are_under_another_section(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["plugin", "add", "coding-rules", "file:RULES.md"]) == 0
        path = world.atlas / "CODING_RULES_CANDIDATES.md"
        text = path.read_text(encoding="utf-8") + f"\n## Promoted\n{_CANDIDATE}"
        path.write_text(text, encoding="utf-8", newline="\n")

        context = _context(world.atlas)

        assert "candidate rules in force here" not in context


def test_leave_out_the_candidates_file_when_no_plugin_is_declared(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        (world.atlas / "CODING_RULES_CANDIDATES.md").write_text(f"## Open\n{_CANDIDATE}", encoding="utf-8")

        context = _context(world.atlas)

        assert "candidate rules in force here" not in context
        assert "CODING RULES — " not in context


def test_write_a_candidates_file_that_says_candidates_are_in_force(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0

        assert main(["plugin", "add", "coding-rules", "mcp:coco"]) == 0

        text = (world.atlas / "CODING_RULES_CANDIDATES.md").read_text(encoding="utf-8")
        assert "in force in this Atlas from the moment it is written" in text


def test_print_the_same_orientation_the_hook_injects(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        assert main(["plugin", "add", "coding-rules", "file:RULES.md"]) == 0
        _stage_candidate(world.atlas)

        code, printed = _orient(world.atlas, monkeypatch, capsys)
        injected = _context(world.atlas)

    assert code == 0
    assert printed == injected
    assert "=== atlas status — where the Atlas and its sources stand ===" in printed
    assert "=== STATUS.md — current state & next steps (read this first) ===" in printed


def test_orient_without_the_plugin_says_nothing_about_coding_rules(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0

        code, printed = _orient(world.atlas, monkeypatch, capsys)

    assert code == 0
    assert printed.startswith("SESSION START — ")
    assert "CODING RULES — " not in printed


def test_orient_names_the_coding_rules_source(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["plugin", "add", "coding-rules", "mcp:coco"]) == 0

        _code, printed = _orient(world.atlas, monkeypatch, capsys)

    assert 'CODING RULES — this Atlas declares the coding-rules plugin with source "mcp:coco"' in printed
    assert "candidate rules in force here" not in printed
    assert "=== CODING_RULES_DEVIATIONS.md — deviations in force ===" in printed


def test_refuse_to_orient_outside_an_atlas(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    code = main(["orient"])

    assert code == 1
    assert capsys.readouterr().out == "This folder is not an Atlas (no _settings/atlas.toml).\n"
    assert list(tmp_path.iterdir()) == []


def test_point_an_older_atlas_to_migrate_and_still_orient(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        (world.atlas / "STATUS.md").write_text("# acme — STATUS\n\n## Active\n_(none)_\n", encoding="utf-8", newline="\n")

        code, printed = _orient(world.atlas, monkeypatch, capsys)
        injected = _context(world.atlas)

    assert code == 1
    assert printed.startswith("This is an Atlas of the older model")
    assert "run `atlas migrate`" in printed
    assert "SESSION START — " in printed
    assert "=== STATUS.md" in printed
    assert "atlas status" not in printed
    assert injected == printed


def test_stay_silent_outside_an_atlas_and_say_so_without_the_cli(tmp_path):
    assert _run_hook(tmp_path).stdout == ""
    with EphemeralAtlasContext(git_sources=[]) as world:
        (world.atlas / "STATUS.md").write_text("# acme — STATUS\n", encoding="utf-8", newline="\n")
        without_cli = _run_hook(world.atlas, path=f"{Path(shutil.which('jq')).parent}{os.pathsep}/usr/bin:/bin")

    assert "the atlas CLI is not on PATH" in json.loads(without_cli.stdout)["hookSpecificOutput"]["additionalContext"]


def test_say_so_when_the_cli_is_too_old_to_orient(tmp_path):
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "atlas").write_text("#!/usr/bin/env bash\necho \"atlas: error: invalid choice: 'orient'\" >&2\nexit 2\n", encoding="utf-8")
    (stub / "atlas").chmod(0o755)
    with EphemeralAtlasContext(git_sources=[]) as world:
        (world.atlas / "STATUS.md").write_text("# acme — STATUS\n", encoding="utf-8", newline="\n")

        result = _run_hook(world.atlas, path=f"{stub}{os.pathsep}{Path(shutil.which('jq')).parent}{os.pathsep}/usr/bin:/bin")

    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "`atlas orient` printed nothing" in context
    assert "upgrade it" in context


def test_mark_the_coding_rules_source_unreadable_when_the_declaration_is_off(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        toml = world.atlas / "_settings/atlas.toml"
        toml.write_text(toml.read_text(encoding="utf-8") + "\n[plugins.coding-rules]\nsource = \n", encoding="utf-8", newline="\n")

        _code, printed = _orient(world.atlas, monkeypatch, capsys)

    assert 'with source "(unreadable — check [plugins.coding-rules] in _settings/atlas.toml)"' in printed
