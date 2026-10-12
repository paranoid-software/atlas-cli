import tomllib
from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext


def _settings(atlas: Path) -> dict:
    return tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))


def test_declare_an_mcp_source(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0

        assert main(["plugin", "add", "coding-rules", "mcp:coco"]) == 0

        assert _settings(atlas)["plugins"] == {"coding-rules": {"source": "mcp:coco"}}


def test_declare_a_file_source(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0

        assert main(["plugin", "add", "coding-rules", "file:CODING_RULES.md"]) == 0

        assert _settings(atlas)["plugins"] == {"coding-rules": {"source": "file:CODING_RULES.md"}}


def test_keep_the_declared_sources_untouched(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0

        assert main(["plugin", "add", "coding-rules", "mcp:coco"]) == 0

        assert list(_settings(atlas)["sources"]) == ["log-daemon"]


def test_create_the_candidates_and_deviations_files(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        capsys.readouterr()

        main(["plugin", "add", "coding-rules", "mcp:coco"])

        candidates = (atlas / "CODING_RULES_CANDIDATES.md").read_text(encoding="utf-8")
        deviations = (atlas / "CODING_RULES_DEVIATIONS.md").read_text(encoding="utf-8")
        assert candidates.startswith("# Coding rules — candidates")
        assert deviations.startswith("# Coding rules — deviations")
        assert capsys.readouterr().out.splitlines() == [
            "declared coding-rules (mcp:coco) in _settings/atlas.toml",
            "created CODING_RULES_CANDIDATES.md",
            "created CODING_RULES_DEVIATIONS.md",
        ]


def test_keep_an_existing_candidates_file(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        (atlas / "CODING_RULES_CANDIDATES.md").write_text("staged rules\n", encoding="utf-8")
        capsys.readouterr()

        assert main(["plugin", "add", "coding-rules", "mcp:coco"]) == 0

        assert (atlas / "CODING_RULES_CANDIDATES.md").read_text(encoding="utf-8") == "staged rules\n"
        assert "kept CODING_RULES_CANDIDATES.md" in capsys.readouterr().out


def test_refuse_a_plugin_already_declared_and_change_nothing(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        main(["plugin", "add", "coding-rules", "mcp:coco"])
        before = (atlas / "_settings/atlas.toml").read_bytes()
        capsys.readouterr()

        assert main(["plugin", "add", "coding-rules", "file:CODING_RULES.md"]) == 1

        assert (atlas / "_settings/atlas.toml").read_bytes() == before
        assert "already declared" in capsys.readouterr().out


def test_refuse_an_unknown_plugin_and_change_nothing(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        before = (atlas / "_settings/atlas.toml").read_bytes()
        capsys.readouterr()

        assert main(["plugin", "add", "time-tracking", "mcp:coco"]) == 1

        assert (atlas / "_settings/atlas.toml").read_bytes() == before
        assert not (atlas / "CODING_RULES_CANDIDATES.md").exists()
        assert "Unknown plugin 'time-tracking'" in capsys.readouterr().out


def test_refuse_a_malformed_source_and_change_nothing(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        before = (atlas / "_settings/atlas.toml").read_bytes()
        capsys.readouterr()

        assert main(["plugin", "add", "coding-rules", "coco"]) == 1

        assert (atlas / "_settings/atlas.toml").read_bytes() == before
        assert not (atlas / "CODING_RULES_DEVIATIONS.md").exists()
        assert "'coco' is not a source" in capsys.readouterr().out


def test_refuse_a_folder_that_is_not_an_atlas(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["plugin", "add", "coding-rules", "mcp:coco"]) == 1

    assert list(tmp_path.iterdir()) == []
    assert "not an Atlas" in capsys.readouterr().out


def test_refuse_a_file_source_outside_the_atlas_or_not_markdown(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        before = (atlas / "_settings/atlas.toml").read_bytes()

        for source in ("file:../outside.md", "file:/etc/rules.md", "file:rules.txt"):
            assert main(["plugin", "add", "coding-rules", source]) == 1

        assert (atlas / "_settings/atlas.toml").read_bytes() == before
        assert capsys.readouterr().out.count("is not a source") == 3
