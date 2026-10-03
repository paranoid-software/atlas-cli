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


def _source(folder: Path, *, git: bool = False, origin: str | None = None) -> Path:
    folder.mkdir(parents=True)
    if git or origin is not None:
        subprocess.run(["git", "-C", str(folder), "init", "-q"], check=True)
    if origin is not None:
        subprocess.run(["git", "-C", str(folder), "remote", "add", "origin", origin], check=True)
    return folder


def test_repoint_the_symlink_and_refresh_the_remote(tmp_path, monkeypatch):
    atlas = _atlas(tmp_path, monkeypatch)
    kept = _source(tmp_path / "atlas")
    current = _source(tmp_path / "old" / "atlas-cli", origin="git@github.com:me/old.git")
    moved = _source(tmp_path / "new" / "atlas-cli", origin="git@github.com:me/new.git")
    assert main(["link", "atlas", str(kept)]) == 0
    assert main(["link", "atlas-cli", str(current)]) == 0
    claude_path = atlas / ".claude/settings.local.json"
    claude = json.loads(claude_path.read_text(encoding="utf-8"))
    claude["permissions"]["allow"] = ["Bash(ls:*)"]
    claude["permissions"]["additionalDirectories"].insert(0, "/kept/elsewhere")
    claude_path.write_text(json.dumps(claude), encoding="utf-8")
    before = (atlas / "_settings/atlas.toml").read_text(encoding="utf-8")

    assert main(["link", "atlas-cli", "../new/atlas-cli"]) == 0

    assert (atlas / "atlas-cli").readlink() == moved.resolve()
    after = (atlas / "_settings/atlas.toml").read_text(encoding="utf-8")
    assert before.split("[sources.atlas-cli]")[0] == after.split("[sources.atlas-cli]")[0]
    settings = tomllib.loads(after)
    assert settings["sources"]["atlas"] == {}
    assert settings["sources"]["atlas-cli"] == {"remote": "git@github.com:me/new.git"}
    vscode = json.loads((atlas / ".vscode/settings.json").read_text(encoding="utf-8"))
    assert vscode["git.scanRepositories"] == ["atlas", "atlas-cli"]
    claude = json.loads(claude_path.read_text(encoding="utf-8"))
    assert claude["permissions"]["allow"] == ["Bash(ls:*)"]
    assert claude["permissions"]["additionalDirectories"] == ["/kept/elsewhere", str(kept.resolve()), str(moved.resolve())]
    assert str(current.resolve()) not in claude["permissions"]["additionalDirectories"]


def test_create_the_symlink_when_the_declaration_has_none(tmp_path, monkeypatch):
    atlas = _atlas(tmp_path, monkeypatch)
    current = _source(tmp_path / "old" / "log-daemon", origin="git@github.com:me/old.git")
    moved = _source(tmp_path / "new" / "log-daemon", origin="git@github.com:me/new.git")
    assert main(["link", "log-daemon", str(current)]) == 0
    (atlas / "log-daemon").unlink()

    assert main(["link", "log-daemon", str(moved)]) == 0

    assert (atlas / "log-daemon").readlink() == moved.resolve()
    settings = tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))
    assert settings["sources"]["log-daemon"] == {"remote": "git@github.com:me/new.git"}
    claude = json.loads((atlas / ".claude/settings.local.json").read_text(encoding="utf-8"))
    assert claude["permissions"]["additionalDirectories"] == [str(current.resolve()), str(moved.resolve())]


def test_repoint_a_dangling_symlink(tmp_path, monkeypatch):
    atlas = _atlas(tmp_path, monkeypatch)
    current = _source(tmp_path / "old" / "log-daemon", origin="git@github.com:me/old.git")
    moved = _source(tmp_path / "new" / "log-daemon", origin="git@github.com:me/new.git")
    assert main(["link", "log-daemon", str(current)]) == 0
    (atlas / "log-daemon").unlink()
    (atlas / "log-daemon").symlink_to(tmp_path / "gone")

    assert main(["link", "log-daemon", str(moved)]) == 0

    assert (atlas / "log-daemon").readlink() == moved.resolve()
    claude = json.loads((atlas / ".claude/settings.local.json").read_text(encoding="utf-8"))
    assert claude["permissions"]["additionalDirectories"] == [str(current.resolve()), str(moved.resolve())]


def test_drop_the_remote_when_the_new_path_is_not_a_git_repo(tmp_path, monkeypatch):
    atlas = _atlas(tmp_path, monkeypatch)
    current = _source(tmp_path / "old" / "notes", origin="git@github.com:me/notes.git")
    moved = _source(tmp_path / "new" / "notes")
    assert main(["link", "notes", str(current)]) == 0

    assert main(["link", "notes", str(moved)]) == 0

    assert (atlas / "notes").readlink() == moved.resolve()
    text = (atlas / "_settings/atlas.toml").read_text(encoding="utf-8")
    assert "remote" not in text
    settings = tomllib.loads(text)
    assert settings["sources"]["notes"] == {}


def test_refuse_to_rebind_over_a_real_file(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    current = _source(tmp_path / "old" / "log-daemon", origin="git@github.com:me/old.git")
    moved = _source(tmp_path / "new" / "log-daemon", origin="git@github.com:me/new.git")
    assert main(["link", "log-daemon", str(current)]) == 0
    (atlas / "log-daemon").unlink()
    (atlas / "log-daemon").write_text("keep me", encoding="utf-8")
    before = {
        "toml": (atlas / "_settings/atlas.toml").read_bytes(),
        "vscode": (atlas / ".vscode/settings.json").read_bytes(),
        "claude": (atlas / ".claude/settings.local.json").read_bytes(),
    }

    assert main(["link", "log-daemon", str(moved)]) == 1

    assert (atlas / "log-daemon").read_text(encoding="utf-8") == "keep me"
    assert (atlas / "_settings/atlas.toml").read_bytes() == before["toml"]
    assert (atlas / ".vscode/settings.json").read_bytes() == before["vscode"]
    assert (atlas / ".claude/settings.local.json").read_bytes() == before["claude"]
    out = capsys.readouterr().out
    assert "already exists" in out
    assert "nothing was changed" in out


def test_refuse_a_missing_path_and_leave_the_symlink(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    current = _source(tmp_path / "old" / "log-daemon", origin="git@github.com:me/old.git")
    assert main(["link", "log-daemon", str(current)]) == 0
    before = (atlas / "_settings/atlas.toml").read_bytes()
    capsys.readouterr()

    assert main(["link", "log-daemon", str(tmp_path / "missing")]) == 1

    assert (atlas / "log-daemon").readlink() == current.resolve()
    assert (atlas / "_settings/atlas.toml").read_bytes() == before
    assert "nothing was changed" in capsys.readouterr().out
