import json
import os
from importlib.resources import files
from pathlib import Path

from atlas_cli.cli import main

_MACHINERY = (
    "atlas-fetch.sh",
    "hooks/session-orient.sh",
    "hooks/atlas-sync-reminder.sh",
    "hooks/skill-reminder-workspace-baseline.sh",
    "commands/atlas-init.md",
    "commands/atlas-sync.md",
    "skills/workspace-baseline/SKILL.md",
)


def _config_folder(tmp_path: Path, monkeypatch) -> Path:
    folder = tmp_path / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(folder))
    return folder


def _packaged(name: str) -> bytes:
    return files("atlas_cli").joinpath("machinery", "claude", name).read_bytes()


def _commands(settings: dict, event: str) -> list[str]:
    return [hook["command"] for entry in settings["hooks"][event] for hook in entry["hooks"]]


def test_install_the_machinery_on_a_first_run(tmp_path, monkeypatch, capsys):
    folder = _config_folder(tmp_path, monkeypatch)

    assert main(["setup", "claude"]) == 0

    for name in _MACHINERY:
        assert (folder / name).read_bytes() == _packaged(name), name
    for name in (name for name in _MACHINERY if name.endswith(".sh")):
        assert os.access(folder / name, os.X_OK), name
    assert (folder / "atlas-source").read_text(encoding="utf-8") == "https://atlas.paranoid.software\n"
    assert capsys.readouterr().out.splitlines() == [
        *(f"installed {name}" for name in _MACHINERY),
        "created atlas-source",
        "wired SessionStart",
        "wired Stop",
        "wired UserPromptSubmit",
    ]


def test_wire_each_hook_to_the_installed_script(tmp_path, monkeypatch):
    folder = _config_folder(tmp_path, monkeypatch)

    main(["setup", "claude"])

    settings = json.loads((folder / "settings.json").read_text(encoding="utf-8"))
    base = folder.resolve()
    assert _commands(settings, "SessionStart") == [f'bash "{base}/hooks/session-orient.sh"']
    assert _commands(settings, "Stop") == [f'bash "{base}/hooks/atlas-sync-reminder.sh"']
    assert _commands(settings, "UserPromptSubmit") == [
        f'bash "{base}/hooks/skill-reminder-workspace-baseline.sh"'
    ]


def test_change_nothing_on_a_second_run(tmp_path, monkeypatch, capsys):
    folder = _config_folder(tmp_path, monkeypatch)
    main(["setup", "claude"])
    settings_before = (folder / "settings.json").read_bytes()
    capsys.readouterr()

    assert main(["setup", "claude"]) == 0

    assert (folder / "settings.json").read_bytes() == settings_before
    assert capsys.readouterr().out.splitlines() == [
        *(f"unchanged {name}" for name in _MACHINERY),
        "kept atlas-source",
        "already wired SessionStart",
        "already wired Stop",
        "already wired UserPromptSubmit",
    ]


def test_replace_a_machinery_file_that_differs(tmp_path, monkeypatch, capsys):
    folder = _config_folder(tmp_path, monkeypatch)
    (folder / "hooks").mkdir(parents=True)
    (folder / "hooks/session-orient.sh").write_text("echo old\n", encoding="utf-8")

    main(["setup", "claude"])

    assert (folder / "hooks/session-orient.sh").read_bytes() == _packaged("hooks/session-orient.sh")
    assert "replaced hooks/session-orient.sh" in capsys.readouterr().out.splitlines()


def test_keep_every_other_setting_and_hook(tmp_path, monkeypatch):
    folder = _config_folder(tmp_path, monkeypatch)
    folder.mkdir()
    (folder / "settings.json").write_text(
        json.dumps(
            {
                "model": "opus",
                "hooks": {
                    "UserPromptSubmit": [
                        {"hooks": [{"type": "command", "command": "bash /x/hooks/git-reminder.sh"}]}
                    ],
                    "PreToolUse": [{"hooks": [{"type": "command", "command": "bash /x/guard.sh"}]}],
                },
            }
        ),
        encoding="utf-8",
    )

    main(["setup", "claude"])

    settings = json.loads((folder / "settings.json").read_text(encoding="utf-8"))
    assert settings["model"] == "opus"
    assert _commands(settings, "PreToolUse") == ["bash /x/guard.sh"]
    assert _commands(settings, "UserPromptSubmit") == [
        "bash /x/hooks/git-reminder.sh",
        f'bash "{folder.resolve()}/hooks/skill-reminder-workspace-baseline.sh"',
    ]


def test_count_a_hook_wired_with_another_path_as_already_wired(tmp_path, monkeypatch, capsys):
    folder = _config_folder(tmp_path, monkeypatch)
    folder.mkdir()
    (folder / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "bash /old/home/.claude/hooks/session-orient.sh"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    main(["setup", "claude"])

    settings = json.loads((folder / "settings.json").read_text(encoding="utf-8"))
    assert _commands(settings, "SessionStart") == ["bash /old/home/.claude/hooks/session-orient.sh"]
    assert "already wired SessionStart" in capsys.readouterr().out.splitlines()


def test_keep_an_existing_atlas_source(tmp_path, monkeypatch, capsys):
    folder = _config_folder(tmp_path, monkeypatch)
    folder.mkdir()
    (folder / "atlas-source").write_text("http://localhost:8088\n", encoding="utf-8")

    main(["setup", "claude"])

    assert (folder / "atlas-source").read_text(encoding="utf-8") == "http://localhost:8088\n"
    assert "kept atlas-source" in capsys.readouterr().out.splitlines()


def test_refuse_unreadable_settings_and_write_nothing(tmp_path, monkeypatch, capsys):
    folder = _config_folder(tmp_path, monkeypatch)
    folder.mkdir()
    (folder / "settings.json").write_text("{ not json", encoding="utf-8")

    assert main(["setup", "claude"]) == 1

    assert sorted(path.name for path in folder.iterdir()) == ["settings.json"]
    assert (folder / "settings.json").read_text(encoding="utf-8") == "{ not json"
    assert "nothing was changed" in capsys.readouterr().out


def test_make_an_unchanged_script_executable_again(tmp_path, monkeypatch, capsys):
    folder = _config_folder(tmp_path, monkeypatch)
    main(["setup", "claude"])
    (folder / "hooks/session-orient.sh").chmod(0o644)
    capsys.readouterr()

    main(["setup", "claude"])

    assert os.access(folder / "hooks/session-orient.sh", os.X_OK)
    assert "unchanged hooks/session-orient.sh" in capsys.readouterr().out.splitlines()


def test_refuse_settings_it_cannot_read_and_write_nothing(tmp_path, monkeypatch, capsys):
    for content in (b'{"hooks": {"Stop": {}}}', b"[1]", b"\xff\xfe not utf-8"):
        folder = tmp_path / str(len(content))
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(folder))
        folder.mkdir()
        (folder / "settings.json").write_bytes(content)

        assert main(["setup", "claude"]) == 1

        assert sorted(path.name for path in folder.iterdir()) == ["settings.json"]
    assert capsys.readouterr().out.count("nothing was changed") == 3


def test_skip_a_hook_entry_it_cannot_read(tmp_path, monkeypatch):
    folder = _config_folder(tmp_path, monkeypatch)
    folder.mkdir()
    (folder / "settings.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": 5}]}}), encoding="utf-8")

    assert main(["setup", "claude"]) == 0

    settings = json.loads((folder / "settings.json").read_text(encoding="utf-8"))
    assert settings["hooks"]["Stop"][0] == {"hooks": 5}
    assert _commands({"hooks": {"Stop": settings["hooks"]["Stop"][1:]}}, "Stop") == [
        f'bash "{folder.resolve()}/hooks/atlas-sync-reminder.sh"'
    ]
