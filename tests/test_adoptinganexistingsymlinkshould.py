import json
import subprocess
import tomllib
from pathlib import Path

from atlas_cli.cli import main


def _atlas(tmp_path: Path, monkeypatch) -> Path:
    atlas = tmp_path / "acme"
    atlas.mkdir()
    monkeypatch.chdir(atlas)
    assert main(["init"]) == 0
    return atlas


def _source(folder: Path, *, origin: str | None = None) -> Path:
    folder.mkdir(parents=True)
    if origin is not None:
        subprocess.run(["git", "-C", str(folder), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(folder), "remote", "add", "origin", origin], check=True)
    return folder


def _tracked(atlas: Path) -> dict[str, bytes]:
    return {
        path: (atlas / path).read_bytes()
        for path in (
            "_settings/atlas.toml",
            ".vscode/settings.json",
            ".claude/settings.local.json",
        )
    }


def test_declare_an_existing_symlink_and_point_it_at_the_new_path(tmp_path, monkeypatch):
    atlas = _atlas(tmp_path, monkeypatch)
    current = _source(tmp_path / "old" / "log-daemon", origin="git@github.com:me/old.git")
    moved = _source(tmp_path / "new" / "log-daemon", origin="git@github.com:me/new.git")
    (atlas / "log-daemon").symlink_to(current)
    claude_path = atlas / ".claude/settings.local.json"
    claude = json.loads(claude_path.read_text(encoding="utf-8"))
    claude["permissions"]["allow"] = ["Bash(ls:*)"]
    claude["permissions"]["additionalDirectories"] = [str(current.resolve()), "/kept/elsewhere"]
    claude_path.write_text(json.dumps(claude), encoding="utf-8")

    assert main(["link", "log-daemon", str(moved)]) == 0

    assert (atlas / "log-daemon").readlink() == moved.resolve()
    settings = tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))
    assert settings["version"] == 1
    assert settings["plugins"] == {}
    assert settings["sources"]["log-daemon"] == {"remote": "git@github.com:me/new.git"}
    vscode = json.loads((atlas / ".vscode/settings.json").read_text(encoding="utf-8"))
    assert vscode["git.scanRepositories"] == ["log-daemon"]
    claude = json.loads(claude_path.read_text(encoding="utf-8"))
    assert claude["permissions"]["allow"] == ["Bash(ls:*)"]
    assert claude["permissions"]["additionalDirectories"] == ["/kept/elsewhere", str(moved.resolve())]


def test_declare_an_existing_symlink_that_already_points_at_the_path(tmp_path, monkeypatch):
    atlas = _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "log-daemon", origin="git@github.com:me/log-daemon.git")
    (atlas / "log-daemon").symlink_to(source.resolve())

    assert main(["link", "log-daemon", str(source)]) == 0

    assert (atlas / "log-daemon").readlink() == source.resolve()
    settings = tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))
    assert settings["sources"]["log-daemon"] == {"remote": "git@github.com:me/log-daemon.git"}
    claude = json.loads((atlas / ".claude/settings.local.json").read_text(encoding="utf-8"))
    assert claude["permissions"]["additionalDirectories"] == [str(source.resolve())]


def test_refuse_to_adopt_over_a_real_file(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    (atlas / "log-daemon").write_text("keep me", encoding="utf-8")
    before = _tracked(atlas)
    source = _source(tmp_path / "elsewhere" / "log-daemon", origin="git@github.com:me/log-daemon.git")

    assert main(["link", "log-daemon", str(source)]) == 1

    assert (atlas / "log-daemon").read_text(encoding="utf-8") == "keep me"
    assert _tracked(atlas) == before
    out = capsys.readouterr().out
    assert "already exists" in out
    assert "nothing was changed" in out


def test_refuse_to_adopt_over_a_real_directory(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    (atlas / "log-daemon").mkdir()
    (atlas / "log-daemon" / "keep").write_text("stay", encoding="utf-8")
    before = _tracked(atlas)
    source = _source(tmp_path / "elsewhere" / "log-daemon", origin="git@github.com:me/log-daemon.git")

    assert main(["link", "log-daemon", str(source)]) == 1

    assert (atlas / "log-daemon" / "keep").read_text(encoding="utf-8") == "stay"
    assert not (atlas / "log-daemon").is_symlink()
    assert _tracked(atlas) == before
    assert "nothing was changed" in capsys.readouterr().out
