import json
import tomllib

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext


def test_repoint_the_symlink_and_refresh_the_remote(monkeypatch):
    with EphemeralAtlasContext(git_sources=["old-atlas-cli", "new-atlas-cli"], plain_sources=["atlas"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["workbench", "add", "claude"]) == 0
        kept = world.source("atlas")
        current = world.source("old-atlas-cli")
        moved = world.source("new-atlas-cli")
        assert main(["link", "atlas", str(kept)]) == 0
        assert main(["link", "atlas-cli", str(current)]) == 0
        claude_path = atlas / ".claude/settings.local.json"
        claude = json.loads(claude_path.read_text(encoding="utf-8"))
        claude["permissions"]["allow"] = ["Bash(ls:*)"]
        claude["permissions"]["additionalDirectories"].insert(0, "/kept/elsewhere")
        claude_path.write_text(json.dumps(claude), encoding="utf-8")
        before = (atlas / "_settings/atlas.toml").read_text(encoding="utf-8")

        assert main(["link", "atlas-cli", "../new-atlas-cli"]) == 0

        assert (atlas / "atlas-cli").readlink() == moved.resolve()
        after = (atlas / "_settings/atlas.toml").read_text(encoding="utf-8")
        assert before.split("[sources.atlas-cli]")[0] == after.split("[sources.atlas-cli]")[0]
        settings = tomllib.loads(after)
        assert settings["sources"]["atlas"] == {}
        assert settings["sources"]["atlas-cli"] == {"remote": world.origin("new-atlas-cli")}
        vscode = json.loads((atlas / ".vscode/settings.json").read_text(encoding="utf-8"))
        assert vscode["git.scanRepositories"] == ["atlas", "atlas-cli"]
        claude = json.loads(claude_path.read_text(encoding="utf-8"))
        assert claude["permissions"]["allow"] == ["Bash(ls:*)"]
        assert claude["permissions"]["additionalDirectories"] == ["/kept/elsewhere", str(kept.resolve()), str(moved.resolve())]
        assert str(current.resolve()) not in claude["permissions"]["additionalDirectories"]


def test_create_the_symlink_when_the_declaration_has_none(monkeypatch):
    with EphemeralAtlasContext(git_sources=["old-log-daemon", "new-log-daemon"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["workbench", "add", "claude"]) == 0
        current = world.source("old-log-daemon")
        moved = world.source("new-log-daemon")
        assert main(["link", "log-daemon", str(current)]) == 0
        (atlas / "log-daemon").unlink()

        assert main(["link", "log-daemon", str(moved)]) == 0

        assert (atlas / "log-daemon").readlink() == moved.resolve()
        settings = tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))
        assert settings["sources"]["log-daemon"] == {"remote": world.origin("new-log-daemon")}
        claude = json.loads((atlas / ".claude/settings.local.json").read_text(encoding="utf-8"))
        assert claude["permissions"]["additionalDirectories"] == [str(current.resolve()), str(moved.resolve())]


def test_repoint_a_dangling_symlink(monkeypatch):
    with EphemeralAtlasContext(git_sources=["old-log-daemon", "new-log-daemon"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["workbench", "add", "claude"]) == 0
        current = world.source("old-log-daemon")
        moved = world.source("new-log-daemon")
        assert main(["link", "log-daemon", str(current)]) == 0
        (atlas / "log-daemon").unlink()
        (atlas / "log-daemon").symlink_to(world.root / "gone")

        assert main(["link", "log-daemon", str(moved)]) == 0

        assert (atlas / "log-daemon").readlink() == moved.resolve()
        claude = json.loads((atlas / ".claude/settings.local.json").read_text(encoding="utf-8"))
        assert claude["permissions"]["additionalDirectories"] == [str(current.resolve()), str(moved.resolve())]


def test_drop_the_remote_when_the_new_path_is_not_a_git_repo(monkeypatch):
    with EphemeralAtlasContext(git_sources=["old-notes"], plain_sources=["new-notes"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["workbench", "add", "claude"]) == 0
        current = world.source("old-notes")
        moved = world.source("new-notes")
        assert main(["link", "notes", str(current)]) == 0

        assert main(["link", "notes", str(moved)]) == 0

        assert (atlas / "notes").readlink() == moved.resolve()
        text = (atlas / "_settings/atlas.toml").read_text(encoding="utf-8")
        assert "remote" not in text
        settings = tomllib.loads(text)
        assert settings["sources"]["notes"] == {}


def test_refuse_to_rebind_over_a_real_file(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["old-log-daemon", "new-log-daemon"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["workbench", "add", "claude"]) == 0
        current = world.source("old-log-daemon")
        moved = world.source("new-log-daemon")
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


def test_refuse_a_missing_path_and_leave_the_symlink(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["old-log-daemon"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["workbench", "add", "claude"]) == 0
        current = world.source("old-log-daemon")
        assert main(["link", "log-daemon", str(current)]) == 0
        before = (atlas / "_settings/atlas.toml").read_bytes()
        capsys.readouterr()

        assert main(["link", "log-daemon", str(world.root / "missing")]) == 1

        assert (atlas / "log-daemon").readlink() == current.resolve()
        assert (atlas / "_settings/atlas.toml").read_bytes() == before
        assert "nothing was changed" in capsys.readouterr().out
