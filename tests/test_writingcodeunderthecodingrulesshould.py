import json
import os
import shutil
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="coding-rules-gate.sh needs jq (a README prerequisite)")

_GATE = files("atlas_cli").joinpath("machinery", "claude", "hooks", "coding-rules-gate.sh")
_SESSION = "session-1"


def _run(atlas: Path, event: str, tool: str, tool_input: dict, env: dict, session: str = _SESSION) -> dict | None:
    payload = {
        "session_id": session,
        "transcript_path": str(atlas / "transcript.jsonl"),
        "cwd": str(atlas),
        "hook_event_name": event,
        "tool_name": tool,
        "tool_input": tool_input,
    }
    result = subprocess.run(
        ["bash", str(_GATE)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def _edit(atlas: Path, path: Path, env: dict, session: str = _SESSION) -> dict | None:
    return _run(atlas, "PreToolUse", "Edit", {"file_path": str(path), "old_string": "a", "new_string": "b"}, env, session)


def _denied(decision: dict | None) -> bool:
    return decision is not None and decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def _env(tmp: Path, **extra: str) -> dict:
    """The environment Claude Code gives the hook, without whatever session runs these tests."""
    env = {key: value for key, value in os.environ.items() if key not in ("CLAUDE_PROJECT_DIR", "ATLAS_CODING_RULES_GATE")}
    return {**env, "TMPDIR": str(tmp), **extra}


def _atlas_with_rules(world: EphemeralAtlasContext, monkeypatch, source: str) -> tuple[Path, dict]:
    monkeypatch.chdir(world.atlas)
    assert main(["init"]) == 0
    assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
    assert main(["plugin", "add", "coding-rules", source]) == 0
    return world.atlas, _env(world.root)


def test_deny_the_first_code_edit_until_the_rules_are_consulted(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:coco")

        decision = _edit(atlas, atlas / "log-daemon" / "README", env)

        assert _denied(decision)
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert 'source "mcp:coco"' in reason
        assert "mcp__coco__" in reason


def test_allow_code_edits_once_the_mcp_source_was_consulted(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:coco")

        assert _run(atlas, "PostToolUse", "mcp__coco__recall", {"query": "logging"}, env) is None

        assert _edit(atlas, atlas / "log-daemon" / "README", env) is None
        assert _edit(atlas, world.source("log-daemon") / "README", env) is None


def test_count_only_the_declared_server_as_consulting_the_rules(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:coco")

        _run(atlas, "PostToolUse", "mcp__other__recall", {"query": "logging"}, env)
        _run(atlas, "PostToolUse", "Read", {"file_path": str(atlas / "CLAUDE.md")}, env)

        assert _denied(_edit(atlas, atlas / "log-daemon" / "README", env))


def test_allow_code_edits_once_the_file_source_was_read(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "file:RULES.md")
        assert _denied(_edit(atlas, atlas / "log-daemon" / "README", env))

        _run(atlas, "PostToolUse", "Read", {"file_path": str(atlas / "RULES.md")}, env)

        assert _edit(atlas, atlas / "log-daemon" / "README", env) is None


def test_keep_each_session_on_its_own(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:coco")
        _run(atlas, "PostToolUse", "mcp__coco__recall", {"query": "logging"}, env, session="session-1")

        assert _denied(_edit(atlas, atlas / "log-daemon" / "README", env, session="session-2"))


def test_always_allow_edits_to_the_atlas_own_files(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:coco")

        for path in ("STATUS.md", "SPEC_0001_X.md", "CODING_RULES_CANDIDATES.md", ".gitignore",
                     "_archived/SPEC_0000_Y.md", "_settings/atlas.toml",
                     ".claude/settings.local.json", ".vscode/settings.json"):
            assert _edit(atlas, atlas / path, env) is None, path


def test_gate_a_markdown_file_inside_a_source(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:coco")

        assert _denied(_edit(atlas, atlas / "log-daemon" / "docs.md", env))


def test_gate_a_notebook_edit(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:coco")

        decision = _run(atlas, "PreToolUse", "NotebookEdit", {"notebook_path": str(atlas / "log-daemon" / "a.ipynb")}, env)

        assert _denied(decision)


def test_allow_everything_in_an_atlas_without_the_plugin(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        env = _env(world.root)

        assert _edit(world.atlas, world.atlas / "log-daemon" / "README", env) is None


def test_allow_everything_outside_an_atlas(tmp_path):
    env = _env(tmp_path)

    assert _edit(tmp_path, tmp_path / "code.py", env) is None


def test_let_the_edit_through_when_jq_is_missing(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:coco")
        bin_without_jq = world.root / "bin"
        bin_without_jq.mkdir()
        for tool in ("bash", "cat", "tr", "grep", "awk", "mkdir"):
            found = shutil.which(tool)
            if found:
                (bin_without_jq / tool).symlink_to(found)
        env = {**env, "PATH": str(bin_without_jq)}

        assert _edit(atlas, atlas / "log-daemon" / "README", env) is None


def test_keep_gating_when_the_agent_works_inside_a_source(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:coco")
        env = {**env, "CLAUDE_PROJECT_DIR": str(atlas)}
        inside = world.source("log-daemon")

        assert _denied(_run(inside, "PreToolUse", "Edit", {"file_path": str(inside / "README")}, env))
        _run(inside, "PostToolUse", "mcp__coco__recall", {"query": "logging"}, env)
        assert _run(inside, "PreToolUse", "Edit", {"file_path": str(inside / "README")}, env) is None


def test_gate_a_path_that_climbs_out_of_an_atlas_folder(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:coco")

        assert _denied(_edit(atlas, Path(f"{atlas}/_settings/../log-daemon/README"), env))


def test_accept_a_file_source_declared_with_a_leading_dot(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "file:./RULES.md")

        _run(atlas, "PostToolUse", "Read", {"file_path": str(atlas / "RULES.md")}, env)

        assert _edit(atlas, atlas / "log-daemon" / "README", env) is None


def test_match_a_server_name_the_way_tool_names_spell_it(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:my.rules")

        _run(atlas, "PostToolUse", "mcp__my_rules__recall", {"query": "logging"}, env)

        assert _edit(atlas, atlas / "log-daemon" / "README", env) is None


def test_let_the_human_turn_the_gate_off(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:coco")

        assert _edit(atlas, atlas / "log-daemon" / "README", {**env, "ATLAS_CODING_RULES_GATE": "off"}) is None


def test_let_a_call_without_a_session_through(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas, env = _atlas_with_rules(world, monkeypatch, "mcp:coco")

        assert _edit(atlas, atlas / "log-daemon" / "README", env, session="") is None
