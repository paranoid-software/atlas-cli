import json
from pathlib import Path

import pytest

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext

_TRACKED = (
    "_settings/atlas.toml",
    ".vscode/settings.json",
    ".claude/settings.local.json",
)
_REMINDER = "Remove the orientation block of log-daemon from CLAUDE.md §1.\n"


def _init(context: EphemeralAtlasContext, monkeypatch) -> Path:
    monkeypatch.chdir(context.atlas)
    assert main(["init"]) == 0
    return context.atlas


def _link(context: EphemeralAtlasContext, *names: str) -> None:
    for name in names:
        assert main(["link", name, str(context.source(name))]) == 0


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _snapshot(atlas: Path) -> dict[str, bytes]:
    return {path: (atlas / path).read_bytes() for path in _TRACKED}


def _unlink(name: str, capsys) -> tuple[int, str]:
    capsys.readouterr()
    code = main(["unlink", name])
    return code, capsys.readouterr().out


def _doctor(capsys) -> str:
    capsys.readouterr()
    main(["doctor"])
    return capsys.readouterr().out


def test_drop_a_linked_source_and_leave_the_rest_as_it_was(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"], plain_sources=["atlas", "notes"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "atlas", "log-daemon", "notes")
        _write(
            atlas / "_settings/atlas.toml",
            "version = 1\n"
            "\n"
            "[plugins]\n"
            "\n"
            "# Sources this Atlas maps.\n"
            "[sources.atlas]\n"
            "\n"
            "[sources.log-daemon]\n"
            f'remote = "{context.origin("log-daemon")}"\n'
            "# kept with notes\n"
            "[sources.notes]\n",
        )
        source = context.source("log-daemon")

        code, out = _unlink("log-daemon", capsys)

        assert code == 0
        assert (atlas / "_settings/atlas.toml").read_text(encoding="utf-8") == (
            "version = 1\n"
            "\n"
            "[plugins]\n"
            "\n"
            "# Sources this Atlas maps.\n"
            "[sources.atlas]\n"
            "\n"
            "# kept with notes\n"
            "[sources.notes]\n"
        )
        assert _read_json(atlas / ".vscode/settings.json")["git.scanRepositories"] == ["atlas", "notes"]
        assert _read_json(atlas / ".claude/settings.local.json")["permissions"]["additionalDirectories"] == [
            str(context.source("atlas").resolve()),
            str(context.source("notes").resolve()),
        ]
        assert not (atlas / "log-daemon").exists() and not (atlas / "log-daemon").is_symlink()
        assert (source / "README").read_text(encoding="utf-8") == "log-daemon\n"
        assert (source / ".git").is_dir()
        assert out == (
            f"removed log-daemon -> {source.resolve()}\n"
            "updated _settings/atlas.toml\n"
            "updated .vscode/settings.json\n"
            "updated .claude/settings.local.json\n" + _REMINDER
        )
        assert "log-daemon" not in _doctor(capsys)


@pytest.mark.parametrize(
    "header", ['[sources."log-daemon"]', "[sources.'log-daemon']", "[ sources.log-daemon ]  # main"]
)
def test_drop_a_source_declared_with_a_quoted_key_or_a_comment(monkeypatch, capsys, header):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        _write(atlas / "_settings/atlas.toml", f"version = 1\n\n[plugins]\n\n{header}\n")

        code, _ = _unlink("log-daemon", capsys)

        assert code == 0
        assert (atlas / "_settings/atlas.toml").read_text(encoding="utf-8") == "version = 1\n\n[plugins]\n"
        assert not (atlas / "log-daemon").is_symlink()


def test_remove_the_target_as_written_and_as_resolved(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        alias = context.root / "alias"
        alias.symlink_to(context.root, target_is_directory=True)
        written = alias / "log-daemon"
        (atlas / "log-daemon").unlink()
        (atlas / "log-daemon").symlink_to(written, target_is_directory=True)
        claude_path = atlas / ".claude/settings.local.json"
        claude = _read_json(claude_path)
        claude["permissions"]["additionalDirectories"] = ["/kept/elsewhere", str(written), str(written.resolve())]
        _write(claude_path, json.dumps(claude))

        code, out = _unlink("log-daemon", capsys)

        assert code == 0
        assert _read_json(claude_path)["permissions"]["additionalDirectories"] == ["/kept/elsewhere"]
        assert f"removed log-daemon -> {written}\n" in out
        assert context.source("log-daemon").is_dir()


def test_keep_the_directory_another_source_still_points_at(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        assert main(["link", "daemon-docs", str(context.source("log-daemon"))]) == 0

        code, _ = _unlink("log-daemon", capsys)

        assert code == 0
        assert _read_json(atlas / ".claude/settings.local.json")["permissions"]["additionalDirectories"] == [
            str(context.source("log-daemon").resolve())
        ]
        assert (atlas / "daemon-docs").is_symlink()


def test_clean_a_declared_source_that_has_no_symlink(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        (atlas / "log-daemon").unlink()

        code, out = _unlink("log-daemon", capsys)

        assert code == 0
        assert (atlas / "_settings/atlas.toml").read_text(encoding="utf-8") == "version = 1\n\n[plugins]\n"
        assert _read_json(atlas / ".vscode/settings.json")["git.scanRepositories"] == []
        assert out == "updated _settings/atlas.toml\nupdated .vscode/settings.json\n" + _REMINDER
        assert "log-daemon" not in _doctor(capsys)


def test_remove_a_broken_symlink_and_its_written_target(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        gone = context.root / "gone" / "log-daemon"
        (atlas / "log-daemon").unlink()
        (atlas / "log-daemon").symlink_to(gone, target_is_directory=True)
        claude_path = atlas / ".claude/settings.local.json"
        claude = _read_json(claude_path)
        claude["permissions"]["additionalDirectories"].append(str(gone))
        _write(claude_path, json.dumps(claude))

        code, out = _unlink("log-daemon", capsys)

        assert code == 0
        assert not (atlas / "log-daemon").is_symlink()
        assert str(gone) not in _read_json(claude_path)["permissions"]["additionalDirectories"]
        assert f"removed log-daemon -> {gone}\n" in out
        assert "log-daemon" not in _doctor(capsys)


def test_remove_an_undeclared_symlink_and_its_settings(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        _write(atlas / "_settings/atlas.toml", "version = 1\n\n[plugins]\n")

        code, out = _unlink("log-daemon", capsys)

        assert code == 0
        assert (atlas / "_settings/atlas.toml").read_text(encoding="utf-8") == "version = 1\n\n[plugins]\n"
        assert _read_json(atlas / ".vscode/settings.json")["git.scanRepositories"] == []
        assert _read_json(atlas / ".claude/settings.local.json")["permissions"]["additionalDirectories"] == []
        assert not (atlas / "log-daemon").is_symlink()
        assert "updated _settings/atlas.toml" not in out
        assert "log-daemon" not in _doctor(capsys)


def test_refuse_when_the_folder_is_not_an_atlas(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        monkeypatch.chdir(context.atlas)
        (context.atlas / "log-daemon").symlink_to(context.source("log-daemon"), target_is_directory=True)

        code, out = _unlink("log-daemon", capsys)

        assert code == 1
        assert (context.atlas / "log-daemon").is_symlink()
        assert "not an Atlas" in out
        assert "nothing was changed" in out


@pytest.mark.parametrize("name", ["notes", "LOG-DAEMON"])
def test_refuse_a_name_that_is_not_a_source(monkeypatch, capsys, name):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        before = _snapshot(atlas)

        code, out = _unlink(name, capsys)

        assert code == 1
        assert _snapshot(atlas) == before
        assert (atlas / "log-daemon").is_symlink()
        assert "not a source of this Atlas" in out
        assert "nothing was changed" in out


@pytest.mark.parametrize("kind", ["file", "folder"])
def test_refuse_a_name_that_is_not_a_symlink(monkeypatch, capsys, kind):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        (atlas / "log-daemon").unlink()
        if kind == "file":
            _write(atlas / "log-daemon", "keep me\n")
        else:
            (atlas / "log-daemon").mkdir()
            _write(atlas / "log-daemon" / "README", "keep me\n")
        before = _snapshot(atlas)

        code, out = _unlink("log-daemon", capsys)

        assert code == 1
        assert _snapshot(atlas) == before
        kept = atlas / "log-daemon" if kind == "file" else atlas / "log-daemon" / "README"
        assert kept.read_text(encoding="utf-8") == "keep me\n"
        assert "not a symlink" in out
        assert "nothing was changed" in out


@pytest.mark.parametrize(
    ("unreadable", "content"),
    [
        ("_settings/atlas.toml", "version = [\n"),
        (".vscode/settings.json", "{ not json"),
        (".claude/settings.local.json", "{ not json"),
        (".claude/settings.local.json", "[]"),
    ],
)
def test_refuse_an_unreadable_settings_file_and_change_nothing(monkeypatch, capsys, unreadable, content):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as context:
        atlas = _init(context, monkeypatch)
        _link(context, "log-daemon")
        _write(atlas / unreadable, content)
        before = _snapshot(atlas)

        code, out = _unlink("log-daemon", capsys)

        assert code == 1
        assert _snapshot(atlas) == before
        assert (atlas / "log-daemon").is_symlink()
        assert "nothing was changed" in out
