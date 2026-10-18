import json
import shutil
import subprocess
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


def _context(atlas: Path) -> str:
    result = subprocess.run(
        ["bash", str(_HOOK)],
        cwd=atlas,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


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
        assert "CLAUDE.md at the Atlas root is this project's orientation" in stores
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
