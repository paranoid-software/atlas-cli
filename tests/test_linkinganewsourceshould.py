import json
import subprocess
import tomllib
from pathlib import Path

import pytest

from atlas_cli.cli import main

_TRACKED = (
    "_settings/atlas.toml",
    ".vscode/settings.json",
    ".claude/settings.local.json",
)


def _atlas(tmp_path: Path, monkeypatch) -> Path:
    atlas = tmp_path / "acme"
    atlas.mkdir()
    monkeypatch.chdir(atlas)
    assert main(["init"]) == 0
    return atlas


def _source(folder: Path, *, git: bool = False, origin: str | None = None) -> Path:
    folder.mkdir(parents=True)
    if git or origin is not None:
        subprocess.run(["git", "-C", str(folder), "init", "-q"], check=True)
    if origin is not None:
        subprocess.run(["git", "-C", str(folder), "remote", "add", "origin", origin], check=True)
    return folder


def _snapshot(atlas: Path) -> dict[str, bytes]:
    return {path: (atlas / path).read_bytes() for path in _TRACKED}


def test_declare_a_new_git_source_and_point_the_symlink_at_it(tmp_path, monkeypatch):
    atlas = _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "elsewhere" / "log-daemon", origin="git@github.com:me/log-daemon.git")

    assert main(["link", "log-daemon", str(source)]) == 0

    link = atlas / "log-daemon"
    assert link.is_symlink()
    assert link.readlink() == source.resolve()
    settings = tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))
    assert settings["version"] == 1
    assert settings["plugins"] == {}
    assert settings["sources"]["log-daemon"] == {"remote": "git@github.com:me/log-daemon.git"}
    vscode = json.loads((atlas / ".vscode/settings.json").read_text(encoding="utf-8"))
    assert vscode["git.scanRepositories"] == ["log-daemon"]
    assert vscode["git.autoRepositoryDetection"] is True
    claude = json.loads((atlas / ".claude/settings.local.json").read_text(encoding="utf-8"))
    assert claude["permissions"]["additionalDirectories"] == [str(source.resolve())]
    assert subprocess.run(
        ["git", "-C", str(source), "status", "--porcelain"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout == ""


def test_declare_a_source_that_is_not_a_git_repo(tmp_path, monkeypatch):
    atlas = _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "notes")

    assert main(["link", "notes", str(source)]) == 0

    settings = tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))
    assert settings["sources"]["notes"] == {}


def test_declare_a_git_source_that_has_no_origin(tmp_path, monkeypatch):
    atlas = _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "scratch", git=True)

    assert main(["link", "scratch", str(source)]) == 0

    settings = tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))
    assert settings["sources"]["scratch"] == {}
    assert (atlas / "scratch").is_symlink()


def test_store_a_relative_path_as_absolute(tmp_path, monkeypatch):
    atlas = _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "elsewhere" / "log-daemon", origin="git@github.com:me/log-daemon.git")

    assert main(["link", "log-daemon", "../elsewhere/log-daemon"]) == 0

    assert (atlas / "log-daemon").readlink().is_absolute()
    claude = json.loads((atlas / ".claude/settings.local.json").read_text(encoding="utf-8"))
    assert claude["permissions"]["additionalDirectories"] == [str(source.resolve())]


def test_keep_existing_editor_and_claude_settings(tmp_path, monkeypatch):
    atlas = _atlas(tmp_path, monkeypatch)
    vscode_path = atlas / ".vscode/settings.json"
    vscode = json.loads(vscode_path.read_text(encoding="utf-8"))
    vscode["editor.tabSize"] = 4
    vscode_path.write_text(json.dumps(vscode), encoding="utf-8")
    claude_path = atlas / ".claude/settings.local.json"
    claude = json.loads(claude_path.read_text(encoding="utf-8"))
    claude["permissions"]["allow"] = ["Bash(ls:*)"]
    claude_path.write_text(json.dumps(claude), encoding="utf-8")
    source = _source(tmp_path / "log-daemon")

    assert main(["link", "log-daemon", str(source)]) == 0

    vscode = json.loads(vscode_path.read_text(encoding="utf-8"))
    assert vscode["editor.tabSize"] == 4
    assert vscode["git.scanRepositories"] == ["log-daemon"]
    claude = json.loads(claude_path.read_text(encoding="utf-8"))
    assert claude["permissions"]["allow"] == ["Bash(ls:*)"]
    assert claude["permissions"]["additionalDirectories"] == [str(source.resolve())]


def test_add_a_second_source_beside_the_first(tmp_path, monkeypatch):
    atlas = _atlas(tmp_path, monkeypatch)
    first = _source(tmp_path / "atlas")
    second = _source(tmp_path / "atlas-cli", origin="git@github.com:me/atlas-cli.git")

    assert main(["link", "atlas", str(first)]) == 0
    assert main(["link", "atlas-cli", str(second)]) == 0

    settings = tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))
    assert set(settings["sources"]) == {"atlas", "atlas-cli"}
    assert settings["sources"]["atlas-cli"]["remote"] == "git@github.com:me/atlas-cli.git"
    vscode = json.loads((atlas / ".vscode/settings.json").read_text(encoding="utf-8"))
    assert vscode["git.scanRepositories"] == ["atlas", "atlas-cli"]


def test_refuse_when_the_folder_is_not_an_atlas(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    source = _source(tmp_path / "elsewhere" / "log-daemon")

    assert main(["link", "log-daemon", str(source)]) == 1

    assert not (tmp_path / "log-daemon").exists()
    assert not (tmp_path / "_settings").exists()
    out = capsys.readouterr().out
    assert "not an Atlas" in out
    assert "nothing was changed" in out


def test_refuse_a_path_that_does_not_exist(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    before = _snapshot(atlas)

    assert main(["link", "log-daemon", str(tmp_path / "missing")]) == 1

    assert _snapshot(atlas) == before
    assert not (atlas / "log-daemon").exists()
    out = capsys.readouterr().out
    assert "does not exist" in out
    assert "nothing was changed" in out


def test_refuse_a_name_that_already_exists_in_the_atlas(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    (atlas / "log-daemon").write_text("keep me", encoding="utf-8")
    before = _snapshot(atlas)
    source = _source(tmp_path / "elsewhere" / "log-daemon")

    assert main(["link", "log-daemon", str(source)]) == 1

    assert (atlas / "log-daemon").read_text(encoding="utf-8") == "keep me"
    assert _snapshot(atlas) == before
    assert "already exists" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["foo/bar", "..", ".hidden", "_settings", "a\\b"])
def test_refuse_a_name_that_is_not_a_single_segment(tmp_path, monkeypatch, capsys, name):
    atlas = _atlas(tmp_path, monkeypatch)
    before = _snapshot(atlas)
    source = _source(tmp_path / "elsewhere" / "log-daemon")

    assert main(["link", name, str(source)]) == 1

    assert _snapshot(atlas) == before
    out = capsys.readouterr().out
    assert "not a source name" in out
    assert "nothing was changed" in out


def test_refuse_unreadable_toml_and_change_nothing(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    (atlas / "_settings/atlas.toml").write_text("version = [\n", encoding="utf-8")
    before = _snapshot(atlas)
    source = _source(tmp_path / "log-daemon")

    assert main(["link", "log-daemon", str(source)]) == 1

    assert _snapshot(atlas) == before
    assert not (atlas / "log-daemon").exists()
    assert "nothing was changed" in capsys.readouterr().out


def test_refuse_unreadable_claude_settings_and_change_nothing(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    (atlas / ".claude/settings.local.json").write_text("{ not json", encoding="utf-8")
    before = _snapshot(atlas)
    source = _source(tmp_path / "log-daemon")

    assert main(["link", "log-daemon", str(source)]) == 1

    assert _snapshot(atlas) == before
    assert not (atlas / "log-daemon").exists()
    assert "nothing was changed" in capsys.readouterr().out
