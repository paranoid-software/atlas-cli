import json
import shutil
import subprocess
import threading
import tomllib
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from atlas_cli.cli import main
from atlas_cli.commands.ui import make_server
from tests.ephemeralatlascontext import EphemeralAtlasContext, orient_sources


def _repo(path: Path, message: str = "Start") -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    (path / "README").write_text(f"{path.name}\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", message], check=True)


def _layout(world: EphemeralAtlasContext) -> Path:
    """my-looky/ holds organizations, each holding repos; one repo sits right under it too."""
    folder = world.source("my-looky")
    _repo(folder / "natural-vitality" / "comercial")
    _repo(folder / "natural-vitality" / "finance")
    _repo(folder / "paranoid-software" / "tools" / "cli")
    _repo(folder / "shared")
    _repo(folder / "natural-vitality" / "comercial" / "vendored")  # inside a repo: not scanned
    (folder / ".venv" / "lib").mkdir(parents=True)
    _repo(folder / "node_modules" / "pkg")
    _repo(folder / "natural-vitality" / "_legacy" / "old")  # a name the declaration rejects: not scanned
    (folder / "elsewhere").symlink_to(folder.parent, target_is_directory=True)  # never through a symlink
    return folder


def _atlas(world: EphemeralAtlasContext, monkeypatch) -> Path:
    monkeypatch.chdir(world.atlas)
    assert main(["init"]) == 0
    assert main(["link", "my-looky", str(world.source("my-looky"))]) == 0
    orient_sources(world.atlas, "my-looky")
    return world.atlas


def _toml(atlas: Path) -> dict:
    return tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))


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


_EXPECTED = ["natural-vitality/comercial", "natural-vitality/finance", "paranoid-software/tools/cli", "shared"]


def test_declare_every_repo_inside_the_folder_by_its_path(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["my-looky"]) as world:
        _layout(world)
        atlas = _atlas(world, monkeypatch)

        repos = _toml(atlas)["sources"]["my-looky"]["repos"]

    assert sorted(repos) == _EXPECTED


def test_scan_the_folder_for_the_editor_settings_too(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["my-looky"]) as world:
        _layout(world)
        atlas = _atlas(world, monkeypatch)

        scanned = json.loads((atlas / ".vscode/settings.json").read_text(encoding="utf-8"))["git.scanRepositories"]

    assert scanned == [f"my-looky/{path}" for path in _EXPECTED]


def test_report_a_deep_repo_that_appeared_after_the_link(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["my-looky"]) as world:
        folder = _layout(world)
        atlas = _atlas(world, monkeypatch)
        _repo(folder / "natural-vitality" / "logistic")
        capsys.readouterr()

        assert main(["doctor"]) == 1

        out = capsys.readouterr().out
        assert out.startswith("ok my-looky\nundeclared my-looky/natural-vitality/logistic\natlas link my-looky ")
        assert main(["link", "my-looky", str(folder)]) == 0
        assert "natural-vitality/logistic" in _toml(atlas)["sources"]["my-looky"]["repos"]


def test_report_a_declared_deep_repo_that_is_missing(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["my-looky"]) as world:
        folder = _layout(world)
        _atlas(world, monkeypatch)
        shutil.rmtree(folder / "paranoid-software")
        capsys.readouterr()

        assert main(["doctor"]) == 1

        assert "missing my-looky/paranoid-software/tools/cli" in capsys.readouterr().out


def test_show_each_deep_repo_in_the_ui_with_its_git(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["my-looky"]) as world:
        _layout(world)
        atlas = _atlas(world, monkeypatch)

        with _server(atlas) as port:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/sources") as response:
                sources = json.loads(response.read().decode("utf-8"))["sources"]

    assert [(s["name"], s["kind"], s["branch"]) for s in sources] == [("my-looky", "folder", None)] + [(f"my-looky/{path}", "repo", "main") for path in _EXPECTED]


def test_name_a_deep_repo_in_status_and_in_a_spec(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["my-looky"]) as world:
        folder = _layout(world)
        atlas = _atlas(world, monkeypatch)
        assert main(["spec", "new", "SALES"]) == 0
        spec = atlas / "SPEC_0001_SALES.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace("repos: <repo-a>, <repo-b>", "repos: my-looky/natural-vitality/comercial"), encoding="utf-8", newline="\n")
        assert main(["spec", "start", "SPEC_0001_SALES"]) == 0
        subprocess.run(["git", "-C", str(folder / "natural-vitality" / "comercial"), "switch", "-q", "-c", "spec/0001-sales"], check=True)
        capsys.readouterr()

        assert main(["status"]) == 0

        out = capsys.readouterr().out
    line = next(line for line in out.splitlines() if line.strip().startswith("my-looky/natural-vitality/comercial:"))
    assert line.strip().startswith("my-looky/natural-vitality/comercial: spec/0001-sales,") and line.endswith("on SPEC_0001's branch")


def test_skip_a_hand_edited_path_that_leaves_the_folder(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["my-looky"]) as world:
        _layout(world)
        atlas = _atlas(world, monkeypatch)
        toml = atlas / "_settings/atlas.toml"
        toml.write_text(toml.read_text(encoding="utf-8") + '\n[sources.my-looky.repos."../outside"]\n[sources.my-looky.repos."/etc"]\n', encoding="utf-8", newline="\n")
        capsys.readouterr()

        assert main(["doctor"]) == 0

        assert capsys.readouterr().out == "ok my-looky\n"


def test_drop_the_folder_with_every_deep_repo(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["my-looky"]) as world:
        _layout(world)
        atlas = _atlas(world, monkeypatch)

        assert main(["unlink", "my-looky"]) == 0

        assert "my-looky" not in _toml(atlas).get("sources", {})
        assert json.loads((atlas / ".vscode/settings.json").read_text(encoding="utf-8"))["git.scanRepositories"] == []


def test_refresh_the_ui_when_a_deep_repo_changes(monkeypatch):
    from atlas_cli.atlascorpus import fingerprint

    with EphemeralAtlasContext(git_sources=[], plain_sources=["my-looky"]) as world:
        folder = _layout(world)
        atlas = _atlas(world, monkeypatch)
        before = fingerprint(atlas)
        subprocess.run(["git", "-C", str(folder / "natural-vitality" / "finance"), "commit", "-q", "--allow-empty", "-m", "Deep work"], check=True)

        assert fingerprint(atlas) != before


def test_read_a_deep_repo_s_commits_in_the_timeline(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["my-looky"]) as world:
        folder = _layout(world)
        atlas = _atlas(world, monkeypatch)
        assert main(["spec", "new", "SALES"]) == 0
        repo = folder / "natural-vitality" / "comercial"
        subprocess.run(["git", "-C", str(repo), "switch", "-q", "-c", "spec/0001-sales"], check=True)
        (repo / "NOTES.md").write_text("work\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "NOTES.md"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "Sales work"], check=True)

        with _server(atlas) as port:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/timeline?days=all") as response:
                events = json.loads(response.read().decode("utf-8"))["events"]

    assert [(e["kind"], e["repo"], e["detail"]) for e in events if e["kind"] == "commit"] == [("commit", "my-looky/natural-vitality/comercial", "Atlas: Sales work")]
