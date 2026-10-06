import json
import subprocess
import tomllib
from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext


def _build_v0_atlas(context: EphemeralAtlasContext, monkeypatch, sources: list[str]) -> Path:
    atlas = context.atlas
    (atlas / "CLAUDE.md").write_text("# acme\n", encoding="utf-8")
    (atlas / "STATUS.md").write_text("# acme — STATUS\n", encoding="utf-8")
    for name in sources:
        (atlas / name).symlink_to(context.source(name), target_is_directory=True)
    monkeypatch.chdir(atlas)
    return atlas


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(folder)): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _settings(atlas: Path) -> dict:
    return tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_print_the_plan_and_change_nothing(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"], plain_sources=["notes"]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, ["log-daemon", "notes"])
        (atlas / "COCO_CANDIDATES.md").write_text("staged\n", encoding="utf-8")
        before = _snapshot(atlas)

        assert main(["migrate"]) == 0

        assert _snapshot(atlas) == before
        assert capsys.readouterr().out.splitlines() == [
            "create _settings/atlas.toml",
            f"declare log-daemon ({context.origin('log-daemon')})",
            "declare notes (not git)",
            "complete .vscode/settings.json",
            "complete .claude/settings.local.json",
            "create .gitignore",
            "declare coding-rules (mcp:coco)",
            "rename COCO_CANDIDATES.md -> CODING_RULES_CANDIDATES.md",
            "create CODING_RULES_DEVIATIONS.md",
            "Run `atlas migrate --apply` to apply this plan.",
        ]


def test_declare_every_symlink_as_a_source_with_its_remote_when_it_has_one(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"], plain_sources=["notes"]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, ["log-daemon", "notes"])

        assert main(["migrate", "--apply"]) == 0

        settings = _settings(atlas)
        assert settings["version"] == 1
        assert settings["plugins"] == {}
        assert settings["sources"] == {
            "log-daemon": {"remote": context.origin("log-daemon")},
            "notes": {},
        }
        out = capsys.readouterr().out.splitlines()
        assert out[:3] == [
            "created _settings/atlas.toml",
            f"declared log-daemon ({context.origin('log-daemon')})",
            "declared notes (not git)",
        ]
        assert main(["doctor"]) == 0


def test_complete_the_settings_and_keep_what_they_already_hold(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"], plain_sources=["notes"]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, ["log-daemon", "notes"])
        (atlas / ".vscode").mkdir()
        (atlas / ".vscode/settings.json").write_text(
            json.dumps({"editor.tabSize": 2, "git.scanRepositories": ["log-daemon"]}), encoding="utf-8"
        )
        (atlas / ".claude").mkdir()
        (atlas / ".claude/settings.local.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(ls:*)"], "additionalDirectories": ["/opt/shared"]}}),
            encoding="utf-8",
        )

        assert main(["migrate", "--apply"]) == 0

        vscode = _json(atlas / ".vscode/settings.json")
        assert vscode == {
            "editor.tabSize": 2,
            "git.scanRepositories": ["log-daemon", "notes"],
            "git.autoRepositoryDetection": True,
        }
        claude = _json(atlas / ".claude/settings.local.json")
        assert claude["permissions"] == {
            "allow": ["Bash(ls:*)"],
            "additionalDirectories": [
                "/opt/shared",
                str(context.source("log-daemon").resolve()),
                str(context.source("notes").resolve()),
            ],
        }


def test_create_the_settings_when_there_are_none(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["notes"]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, ["notes"])

        assert main(["migrate", "--apply"]) == 0

        assert _json(atlas / ".vscode/settings.json") == {
            "git.autoRepositoryDetection": True,
            "git.scanRepositories": ["notes"],
        }
        assert _json(atlas / ".claude/settings.local.json") == {
            "permissions": {"allow": [], "additionalDirectories": [str(context.source("notes").resolve())]},
        }


def test_create_the_gitignore_whitelist_when_there_is_none(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, [])

        assert main(["migrate", "--apply"]) == 0

        assert (atlas / ".gitignore").read_text(encoding="utf-8").startswith("/*\n!/*.md\n")


def test_keep_an_existing_gitignore(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, [])
        (atlas / ".gitignore").write_text("*.log\n", encoding="utf-8")

        assert main(["migrate", "--apply"]) == 0

        assert (atlas / ".gitignore").read_text(encoding="utf-8") == "*.log\n"
        assert "kept .gitignore" in capsys.readouterr().out.splitlines()


def test_move_the_coco_files_to_the_coding_rules_plugin_keeping_their_content(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, [])
        (atlas / "COCO_CANDIDATES.md").write_text("staged rule — ñ\n", encoding="utf-8")
        (atlas / "DEVIATIONS.md").write_text("deviation in force\n", encoding="utf-8")

        assert main(["migrate", "--apply"]) == 0

        assert _settings(atlas)["plugins"] == {"coding-rules": {"source": "mcp:coco"}}
        assert (atlas / "CODING_RULES_CANDIDATES.md").read_text(encoding="utf-8") == "staged rule — ñ\n"
        assert (atlas / "CODING_RULES_DEVIATIONS.md").read_text(encoding="utf-8") == "deviation in force\n"
        assert not (atlas / "COCO_CANDIDATES.md").exists()
        assert not (atlas / "DEVIATIONS.md").exists()
        out = capsys.readouterr().out.splitlines()
        assert out[-3:] == [
            "declared coding-rules (mcp:coco)",
            "renamed COCO_CANDIDATES.md -> CODING_RULES_CANDIDATES.md",
            "renamed DEVIATIONS.md -> CODING_RULES_DEVIATIONS.md",
        ]


def test_create_the_missing_deviations_file_from_the_plugin_template(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, [])
        (atlas / "COCO_CANDIDATES.md").write_text("staged\n", encoding="utf-8")

        assert main(["migrate", "--apply"]) == 0

        deviations = (atlas / "CODING_RULES_DEVIATIONS.md").read_text(encoding="utf-8")
        assert deviations.startswith("# Coding rules — deviations")


def test_leave_deviations_without_coco_candidates_and_say_the_plugin_needs_a_source(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, [])
        (atlas / "DEVIATIONS.md").write_text("deviation in force\n", encoding="utf-8")

        assert main(["migrate", "--apply"]) == 0

        assert (atlas / "DEVIATIONS.md").read_text(encoding="utf-8") == "deviation in force\n"
        assert not (atlas / "CODING_RULES_DEVIATIONS.md").exists()
        assert _settings(atlas)["plugins"] == {}
        assert (
            "note: DEVIATIONS.md needs a coding-rules source (atlas plugin add coding-rules <source>)"
            in capsys.readouterr().out.splitlines()
        )


def test_list_the_planning_files_found_in_a_source_without_touching_them(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"], plain_sources=["notes"]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, ["log-daemon", "notes"])
        source = context.source("log-daemon")
        for name in ("STATUS.md", "BACKLOG.md", "SPEC_0001_START.md", "DRAFT_IDEA.md", "README.md"):
            (source / name).write_text(f"{name}\n", encoding="utf-8")
        (source / "docs").mkdir()
        (source / "docs/SPEC_0002_DEEP.md").write_text("deep\n", encoding="utf-8")
        before = _snapshot(source)

        assert main(["migrate", "--apply"]) == 0

        assert _snapshot(source) == before
        assert capsys.readouterr().out.splitlines()[-1] == (
            "note: log-daemon holds planning files: BACKLOG.md, DRAFT_IDEA.md, SPEC_0001_START.md, STATUS.md"
        )


def test_find_the_atlas_up_to_date_on_a_second_run(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, ["log-daemon"])
        (atlas / "COCO_CANDIDATES.md").write_text("staged\n", encoding="utf-8")
        assert main(["migrate", "--apply"]) == 0
        after_first = _snapshot(atlas)
        capsys.readouterr()

        assert main(["migrate", "--apply"]) == 0

        assert _snapshot(atlas) == after_first
        assert capsys.readouterr().out.splitlines() == ["This Atlas is up to date (model v1)."]


def test_say_a_v1_atlas_is_up_to_date_and_change_nothing(tmp_path, monkeypatch, capsys):
    atlas = tmp_path / "acme"
    atlas.mkdir()
    monkeypatch.chdir(atlas)
    assert main(["init"]) == 0
    before = _snapshot(atlas)
    capsys.readouterr()

    assert main(["migrate"]) == 0

    assert _snapshot(atlas) == before
    assert capsys.readouterr().out.splitlines() == ["This Atlas is up to date (model v1)."]


def test_refuse_a_folder_that_is_not_an_atlas(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["migrate", "--apply"]) == 1

    assert list(tmp_path.iterdir()) == []
    assert capsys.readouterr().out.splitlines() == ["This folder is not an Atlas."]


def test_change_nothing_when_a_file_cannot_be_read(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, [])
        (atlas / "COCO_CANDIDATES.md").write_bytes(b"\xff\xfe not utf-8\n")
        (atlas / ".vscode").mkdir()
        (atlas / ".vscode/settings.json").write_text("{}", encoding="utf-8")
        before = _snapshot(atlas)

        assert main(["migrate", "--apply"]) == 1

        assert _snapshot(atlas) == before
        assert "Cannot read COCO_CANDIDATES.md" in capsys.readouterr().out


def test_declare_a_git_source_without_origin_as_having_no_remote(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, [])
        scratch = context.root / "scratch"
        scratch.mkdir()
        subprocess.run(["git", "init", "-q", str(scratch)], check=True)
        (atlas / "scratch").symlink_to(scratch, target_is_directory=True)

        assert main(["migrate", "--apply"]) == 0

        assert _settings(atlas)["sources"] == {"scratch": {}}
        assert "declared scratch (no remote)" in capsys.readouterr().out.splitlines()


def test_declare_a_broken_symlink_as_broken_and_let_doctor_report_it(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, [])
        (atlas / "gone").symlink_to(context.root / "nowhere", target_is_directory=True)

        assert main(["migrate", "--apply"]) == 0

        assert _settings(atlas)["sources"] == {"gone": {}}
        assert "declared gone (broken)" in capsys.readouterr().out.splitlines()
        assert main(["doctor"]) == 1
        assert capsys.readouterr().out.splitlines()[0].startswith("broken gone")


def test_keep_an_existing_plugin_file_and_leave_the_coco_file_in_place(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as context:
        atlas = _build_v0_atlas(context, monkeypatch, [])
        (atlas / "COCO_CANDIDATES.md").write_text("old staged rule\n", encoding="utf-8")
        (atlas / "CODING_RULES_CANDIDATES.md").write_text("current staged rule\n", encoding="utf-8")

        assert main(["migrate", "--apply"]) == 0

        assert (atlas / "CODING_RULES_CANDIDATES.md").read_text(encoding="utf-8") == "current staged rule\n"
        assert (atlas / "COCO_CANDIDATES.md").read_text(encoding="utf-8") == "old staged rule\n"
        out = capsys.readouterr().out.splitlines()
        assert "kept CODING_RULES_CANDIDATES.md" in out
        assert "note: COCO_CANDIDATES.md left in place because CODING_RULES_CANDIDATES.md already exists" in out


def test_refuse_a_model_version_it_does_not_know_and_change_nothing(tmp_path, monkeypatch, capsys):
    (tmp_path / "_settings").mkdir()
    (tmp_path / "_settings/atlas.toml").write_text("version = 2\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("# acme\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    before = _snapshot(tmp_path)

    assert main(["migrate", "--apply"]) == 1

    assert _snapshot(tmp_path) == before
    assert "declares version 2, a model atlas migrate does not know" in capsys.readouterr().out
