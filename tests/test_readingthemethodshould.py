import http.server
import socket
import threading
from contextlib import contextmanager
from pathlib import Path

from atlas_cli.cli import main

_INDEX = """# Atlas

## The framework
- [Method overview](method/README.md): Reading order.
- [The Atlas model](method/01-the-atlas.md): The model.
- [The stores model](method/02-stores-model.md): The stores.

## Full text
- [llms-full.txt](llms-full.txt): Everything.
"""


def _clone(root: Path) -> Path:
    clone = root / "framework"
    (clone / "method").mkdir(parents=True)
    (clone / "method" / "README.md").write_text("# The Atlas method\n\nReading order.\n", encoding="utf-8")
    (clone / "method" / "01-the-atlas.md").write_text("# The Atlas\n\nThe model.\n", encoding="utf-8")
    (clone / "method" / "02-stores-model.md").write_text("# The stores model\n\nThe stores.\n", encoding="utf-8")
    return clone


def _site(root: Path) -> Path:
    site = root / "site"
    (site / "method").mkdir(parents=True)
    (site / "llms.txt").write_text(_INDEX, encoding="utf-8")
    (site / "llms-full.txt").write_text("# Atlas\n\nEverything, concatenated.\n", encoding="utf-8")
    (site / "method" / "01-the-atlas.md").write_text("# The Atlas\n\nThe model, served.\n", encoding="utf-8")
    (site / "method" / "02-stores-model.md").write_text("# The stores model\n\nThe stores, served.\n", encoding="utf-8")
    return site


@contextmanager
def _served(folder: Path):
    handler = type("Quiet", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *args: None})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), lambda *args, **kwargs: handler(*args, directory=str(folder), **kwargs))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _configured(tmp_path: Path, monkeypatch) -> Path:
    folder = tmp_path / "atlas-config"
    monkeypatch.setenv("ATLAS_CONFIG_DIR", str(folder))
    return folder


def _out(capsys) -> str:
    return capsys.readouterr().out


def test_print_the_index_of_a_local_clone(tmp_path, monkeypatch, capsys):
    folder = _configured(tmp_path, monkeypatch)
    clone = _clone(tmp_path)
    assert main(["method", "--source", str(clone)]) == 0
    assert (folder / "source").read_text(encoding="utf-8") == f"{clone}\n"
    capsys.readouterr()

    assert main(["method"]) == 0

    assert _out(capsys) == "# The Atlas method\n\nReading order.\n"


def test_print_one_page_by_name_or_number(tmp_path, monkeypatch, capsys):
    _configured(tmp_path, monkeypatch)
    assert main(["method", "--source", str(_clone(tmp_path))]) == 0
    for wanted in ("02", "2", "02-stores-model", "method/02-stores-model.md"):
        capsys.readouterr()

        assert main(["method", wanted]) == 0, wanted

        assert _out(capsys) == "# The stores model\n\nThe stores.\n", wanted


def test_print_the_whole_framework_of_a_clone_in_order(tmp_path, monkeypatch, capsys):
    _configured(tmp_path, monkeypatch)
    assert main(["method", "--source", str(_clone(tmp_path))]) == 0
    capsys.readouterr()

    assert main(["method", "--full"]) == 0

    out = _out(capsys)
    assert out.index("Reading order.") < out.index("The model.") < out.index("The stores.")


def test_read_the_site_through_its_endpoints(tmp_path, monkeypatch, capsys):
    _configured(tmp_path, monkeypatch)
    with _served(_site(tmp_path)) as url:
        assert main(["method", "--source", url]) == 0
        capsys.readouterr()
        assert main(["method"]) == 0
        index = _out(capsys)
        assert main(["method", "01"]) == 0
        page = _out(capsys)
        assert main(["method", "--full"]) == 0
        full = _out(capsys)

    assert index == _INDEX
    assert page == "# The Atlas\n\nThe model, served.\n"
    assert full == "# Atlas\n\nEverything, concatenated.\n"


def test_refuse_a_page_the_framework_does_not_have(tmp_path, monkeypatch, capsys):
    _configured(tmp_path, monkeypatch)
    assert main(["method", "--source", str(_clone(tmp_path))]) == 0
    capsys.readouterr()

    assert main(["method", "09"]) == 1

    assert _out(capsys) == "The framework has no page '09'; the pages are 01-the-atlas, 02-stores-model.\n"


def test_say_so_in_one_line_when_the_source_cannot_be_reached(tmp_path, monkeypatch, capsys):
    _configured(tmp_path, monkeypatch)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    assert main(["method", "--source", f"http://127.0.0.1:{port}"]) == 0
    capsys.readouterr()

    assert main(["method"]) == 1

    lines = _out(capsys).splitlines()
    assert len(lines) == 1
    assert lines[0].startswith(f"The framework source http://127.0.0.1:{port} could not be reached")
    assert "atlas method --source" in lines[0]


def test_read_the_official_site_without_a_setting(tmp_path, monkeypatch):
    _configured(tmp_path, monkeypatch)
    from atlas_cli.commands.method import read_source

    assert read_source() == "https://atlas.paranoid.software"


def test_send_every_session_to_atlas_method(monkeypatch, capsys):
    from tests.ephemeralatlascontext import EphemeralAtlasContext

    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["plugin", "add", "coding-rules", "mcp:coco"]) == 0
        capsys.readouterr()

        assert main(["orient"]) == 0

        out = _out(capsys)
    assert "run `atlas method` for the index, then `atlas method <page>` for the piece you need" in out
    assert "atlas-fetch" not in out and "~/.claude" not in out
    assert "Where the workbench has a gate (Claude Code does), the first code edit of a session is blocked" in out


def test_name_atlas_method_in_every_machinery_text():
    from importlib.resources import files

    machinery = files("atlas_cli").joinpath("machinery", "claude")
    texts = {
        "hooks/skill-reminder-workspace-baseline.sh", "hooks/session-orient.sh", "commands/atlas-init.md",
        "commands/atlas-sync.md", "skills/workspace-baseline/SKILL.md",
    }
    for name in texts:
        text = machinery.joinpath(*name.split("/")).read_text(encoding="utf-8")
        assert "atlas-source" not in text and "atlas-fetch" not in text, name
    assert "atlas workbench add claude" in machinery.joinpath("commands", "atlas-init.md").read_text(encoding="utf-8")
