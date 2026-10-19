import json
import unicodedata
from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext, orient_sources

_TRACKED = (
    "_settings/atlas.toml",
    ".vscode/settings.json",
    ".claude/settings.local.json",
)


def _init(context: EphemeralAtlasContext, monkeypatch) -> Path:
    monkeypatch.chdir(context.atlas)
    assert main(["init"]) == 0
    assert main(["workbench", "add", "claude"]) == 0
    return context.atlas


def _link(name: str, path: Path, capsys) -> tuple[int, str]:
    capsys.readouterr()
    code = main(["link", name, str(path)])
    return code, capsys.readouterr().out


def _snapshot(atlas: Path) -> dict[str, bytes]:
    return {path: (atlas / path).read_bytes() for path in _TRACKED}


def test_refuse_a_name_that_differs_only_in_case_from_a_linked_source(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["src1", "other"], case_insensitive=True) as context:
        atlas = _init(context, monkeypatch)
        assert main(["link", "src1", str(context.source("src1"))]) == 0
        before = _snapshot(atlas)

        code, out = _link("SRC1", context.source("other"), capsys)

        assert code == 1
        assert _snapshot(atlas) == before
        assert sorted(entry.name for entry in atlas.iterdir() if entry.is_symlink()) == ["src1"]
        assert (atlas / "src1").readlink() == context.source("src1").resolve()
        assert "SRC1 and src1 are the same name on a case-insensitive disk" in out
        assert "nothing was changed" in out


def test_refuse_a_name_that_differs_only_in_case_from_a_declared_source(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["src1"], case_insensitive=True) as context:
        atlas = _init(context, monkeypatch)
        assert main(["link", "src1", str(context.source("src1"))]) == 0
        (atlas / "src1").unlink()
        before = _snapshot(atlas)

        code, out = _link("Src1", context.source("src1"), capsys)

        assert code == 1
        assert _snapshot(atlas) == before
        assert not any(entry.is_symlink() for entry in atlas.iterdir())
        assert "Src1 and src1 are the same name on a case-insensitive disk" in out


def test_refuse_a_name_that_differs_only_in_case_from_an_undeclared_symlink(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["src1", "other"], case_insensitive=True) as context:
        atlas = _init(context, monkeypatch)
        (atlas / "src1").symlink_to(context.source("src1"), target_is_directory=True)
        before = _snapshot(atlas)

        code, out = _link("SRC1", context.source("other"), capsys)

        assert code == 1
        assert _snapshot(atlas) == before
        assert (atlas / "src1").readlink() == context.source("src1")
        assert "SRC1 and src1 are the same name on a case-insensitive disk" in out


def test_refuse_a_name_that_differs_only_in_unicode_form(monkeypatch, capsys):
    composed = unicodedata.normalize("NFC", "café")
    decomposed = unicodedata.normalize("NFD", "café")
    with EphemeralAtlasContext(git_sources=[], plain_sources=["src1", "other"], case_insensitive=True) as context:
        atlas = _init(context, monkeypatch)
        assert main(["link", composed, str(context.source("src1"))]) == 0
        before = _snapshot(atlas)

        code, out = _link(decomposed, context.source("other"), capsys)

        assert code == 1
        assert _snapshot(atlas) == before
        assert (atlas / composed).readlink() == context.source("src1").resolve()
        assert f"{decomposed} and {composed} are the same name on a case-insensitive disk" in out
        assert "nothing was changed" in out


def test_refuse_a_name_that_differs_only_in_case_from_an_entry(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["notes"], case_insensitive=True) as context:
        atlas = _init(context, monkeypatch)
        (atlas / "Notes").mkdir()
        before = _snapshot(atlas)

        code, out = _link("notes", context.source("notes"), capsys)

        assert code == 1
        assert _snapshot(atlas) == before
        assert (atlas / "Notes").is_dir() and not (atlas / "Notes").is_symlink()
        assert "notes and Notes are the same name on a case-insensitive disk" in out


def test_keep_rebinding_a_source_by_its_exact_name(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["src1", "other"], case_insensitive=True) as context:
        atlas = _init(context, monkeypatch)
        assert main(["link", "src1", str(context.source("src1"))]) == 0

        code, out = _link("src1", context.source("other"), capsys)

        assert code == 0
        assert (atlas / "src1").readlink() == context.source("other").resolve()
        claude = json.loads((atlas / ".claude/settings.local.json").read_text(encoding="utf-8"))
        assert claude["permissions"]["additionalDirectories"] == [str(context.source("other").resolve())]
        assert f"rebound src1 -> {context.source('other').resolve()}\n" in out


def test_doctor_judges_a_declared_source_by_its_exact_name(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["src1"], case_insensitive=True) as context:
        atlas = _init(context, monkeypatch)
        assert main(["link", "src1", str(context.source("src1"))]) == 0
        orient_sources(atlas, "src1")
        (atlas / "src1").unlink()
        (atlas / "SRC1").symlink_to(context.source("src1"), target_is_directory=True)
        capsys.readouterr()

        code = main(["doctor"])

        out = capsys.readouterr().out
        assert code == 1
        assert out.splitlines()[:4] == [
            "missing src1",
            "atlas unlink SRC1",
            "atlas link src1 <path>",
            "undeclared SRC1",
        ]
