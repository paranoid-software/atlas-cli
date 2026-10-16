import json
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from atlas_cli.cli import main
from atlas_cli.commands.ui import make_server
from tests.ephemeralatlascontext import EphemeralAtlasContext

_FILES = (
    "atlas-fetch.sh",
    "hooks/session-orient.sh",
    "hooks/atlas-sync-reminder.sh",
    "hooks/skill-reminder-workspace-baseline.sh",
    "hooks/coding-rules-gate.sh",
    "commands/atlas-init.md",
    "commands/atlas-sync.md",
    "skills/workspace-baseline/SKILL.md",
)
_EVENTS = ("SessionStart", "Stop", "UserPromptSubmit", "PreToolUse", "PostToolUse")


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


def _get(port: int, path: str) -> tuple[str, bytes]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as response:
        return response.headers["Content-Type"], response.read()


def _machinery(atlas: Path) -> dict:
    with _server(atlas) as port:
        return json.loads(_get(port, "/api/machinery")[1])


def _atlas(world: EphemeralAtlasContext, monkeypatch) -> tuple[Path, Path]:
    config = world.root / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.chdir(world.atlas)
    assert main(["init"]) == 0
    return world.atlas, config


def test_report_the_machinery_missing_before_setup(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas, config = _atlas(world, monkeypatch)

        state = _machinery(atlas)

    assert state["folder"] == str(config)
    assert state["files"] == [{"name": name, "state": "missing"} for name in _FILES]
    assert [(hook["event"], hook["wired"]) for hook in state["hooks"]] == [(event, False) for event in _EVENTS]
    assert state["error"] is None


def test_report_the_machinery_installed_and_wired_after_setup(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas, _config = _atlas(world, monkeypatch)
        assert main(["setup", "claude"]) == 0

        state = _machinery(atlas)

    assert {item["state"] for item in state["files"]} == {"unchanged"}
    assert all(hook["wired"] for hook in state["hooks"])


def test_tell_a_file_that_differs_from_the_package(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas, config = _atlas(world, monkeypatch)
        assert main(["setup", "claude"]) == 0
        (config / "commands/atlas-sync.md").write_text("an older copy\n", encoding="utf-8")

        state = _machinery(atlas)

    assert {item["name"]: item["state"] for item in state["files"]}["commands/atlas-sync.md"] == "differs"


def test_report_settings_it_cannot_read_without_failing(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas, config = _atlas(world, monkeypatch)
        config.mkdir()
        (config / "settings.json").write_text("{ not json", encoding="utf-8")

        state = _machinery(atlas)

    assert "Cannot read" in state["error"]
    assert not any(hook["wired"] for hook in state["hooks"])


def test_serve_the_vendored_libraries_as_javascript(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas, _config = _atlas(world, monkeypatch)
        with _server(atlas) as port:
            served = {name: _get(port, f"/static/{name}") for name in ("jquery.min.js", "plugster.js", "minisearch.js")}

    for name, (content_type, body) in served.items():
        assert content_type == "application/javascript; charset=utf-8", name
        assert len(body) > 10_000, name
    assert served["plugster.js"][1].rstrip().endswith(b"export { Plugster };")
    assert b"export { MiniSearch as default }" in served["minisearch.js"][1]


def test_report_settings_it_is_not_allowed_to_read_without_failing(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas, config = _atlas(world, monkeypatch)
        config.mkdir()
        settings = config / "settings.json"
        settings.write_text("{}", encoding="utf-8")
        settings.chmod(0)
        try:
            state = _machinery(atlas)
        finally:
            settings.chmod(0o644)

    assert "Cannot read" in state["error"]


def test_write_nothing_in_the_machinery_folder_while_serving(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas, config = _atlas(world, monkeypatch)
        assert main(["setup", "claude"]) == 0
        before = {str(path): path.read_bytes() for path in sorted(config.rglob("*")) if path.is_file()}

        with _server(atlas) as port:
            for path in ("/api/machinery", "/api/version", "/api/doctor", "/api/status", "/api/corpus"):
                _get(port, path)

        assert {str(path): path.read_bytes() for path in sorted(config.rglob("*")) if path.is_file()} == before
