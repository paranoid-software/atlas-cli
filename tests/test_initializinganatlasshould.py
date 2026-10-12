import json
import tomllib
from datetime import date
from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext


def _files_under(folder: Path) -> set[str]:
    return {str(path.relative_to(folder)) for path in folder.rglob("*") if path.is_file()}


def test_create_the_base_set_and_nothing_else(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert main(["init"]) == 0

    assert _files_under(tmp_path) == {
        "CLAUDE.md",
        "STATUS.md",
        "BACKLOG.md",
        "_archived/README.md",
        "_settings/atlas.toml",
        ".claude/settings.local.json",
        ".vscode/settings.json",
        ".gitignore",
    }


def test_start_with_no_sources_and_no_plugins(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    main(["init"])

    settings = tomllib.loads((tmp_path / "_settings/atlas.toml").read_text(encoding="utf-8"))
    assert settings == {"version": 1, "plugins": {}}
    claude = json.loads((tmp_path / ".claude/settings.local.json").read_text(encoding="utf-8"))
    assert claude == {"permissions": {"allow": [], "additionalDirectories": []}}
    vscode = json.loads((tmp_path / ".vscode/settings.json").read_text(encoding="utf-8"))
    assert vscode == {"git.autoRepositoryDetection": True, "git.scanRepositories": []}


def test_ignore_everything_but_the_atlas_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    main(["init"])

    assert (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines() == [
        "/*",
        "!/*.md",
        "!/_*/",
        "!/.vscode/",
        "!/.gitignore",
    ]


def test_name_the_atlas_after_its_folder(tmp_path, monkeypatch):
    folder = tmp_path / "log-daemon"
    folder.mkdir()
    monkeypatch.chdir(folder)

    main(["init"])

    assert (folder / "CLAUDE.md").read_text(encoding="utf-8").startswith("# log-daemon Atlas")
    assert (folder / "STATUS.md").read_text(encoding="utf-8").startswith("# log-daemon — STATUS")


def test_date_the_status_with_today(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    main(["init"])

    assert f"_Last updated: {date.today().isoformat()}_" in (tmp_path / "STATUS.md").read_text(encoding="utf-8")


def test_write_the_same_files_on_every_run(tmp_path, monkeypatch):
    first, second = tmp_path / "acme", tmp_path / "other" / "acme"
    for folder in (first, second):
        folder.mkdir(parents=True)
        monkeypatch.chdir(folder)
        main(["init"])

    for path in _files_under(first):
        assert (first / path).read_bytes() == (second / path).read_bytes(), path


def test_write_utf8_with_unix_line_endings(tmp_path, monkeypatch):
    folder = tmp_path / "señal"
    folder.mkdir()
    monkeypatch.chdir(folder)

    main(["init"])

    for path in _files_under(folder):
        assert b"\r\n" not in (folder / path).read_bytes(), path
    assert (folder / "CLAUDE.md").read_bytes().startswith("# señal Atlas".encode("utf-8"))


def test_keep_what_an_existing_claude_settings_already_allows(tmp_path, monkeypatch):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/settings.local.json").write_text(
        '{"permissions": {"allow": ["Bash(ls:*)"]}}', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    assert main(["init"]) == 0

    claude = json.loads((tmp_path / ".claude/settings.local.json").read_text(encoding="utf-8"))
    assert claude == {"permissions": {"allow": ["Bash(ls:*)"], "additionalDirectories": []}}


def test_turn_on_repository_detection_in_existing_vscode_settings(tmp_path, monkeypatch):
    (tmp_path / ".vscode").mkdir()
    (tmp_path / ".vscode/settings.json").write_text(
        '{"editor.tabSize": 4, "git.autoRepositoryDetection": "openEditors"}', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    assert main(["init"]) == 0

    vscode = json.loads((tmp_path / ".vscode/settings.json").read_text(encoding="utf-8"))
    assert vscode == {
        "editor.tabSize": 4,
        "git.autoRepositoryDetection": True,
        "git.scanRepositories": [],
    }


def test_keep_an_existing_gitignore_and_ask_to_check_it(tmp_path, monkeypatch, capsys):
    (tmp_path / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["init"]) == 0

    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == "node_modules/\n"
    assert "Check that the existing .gitignore" in capsys.readouterr().out


def test_refuse_unreadable_claude_settings_and_change_nothing(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/settings.local.json").write_text("{ not json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["init"]) == 1

    assert _files_under(tmp_path) == {".claude/settings.local.json"}
    assert "nothing was changed" in capsys.readouterr().out


def test_refuse_a_folder_that_is_already_an_atlas(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["init"])
    (tmp_path / "STATUS.md").write_text("work in progress", encoding="utf-8")
    capsys.readouterr()

    assert main(["init"]) == 1

    assert (tmp_path / "STATUS.md").read_text(encoding="utf-8") == "work in progress"
    assert "already an Atlas" in capsys.readouterr().out


def test_suggest_migrate_for_an_atlas_without_settings(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("an Atlas from before _settings/", encoding="utf-8")

    assert main(["init"]) == 1

    assert not (tmp_path / "_settings").exists()
    assert "atlas migrate" in capsys.readouterr().out


def test_leave_existing_sources_untouched(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as world:
        atlas = world.atlas
        (atlas / "log-daemon").symlink_to(world.source("log-daemon"))
        monkeypatch.chdir(atlas)

        assert main(["init"]) == 0

        assert (atlas / "log-daemon").is_symlink()
