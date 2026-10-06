import shlex
import subprocess
from pathlib import Path

import pytest

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


def _place_rule_file(source: Path, rule_file: str) -> None:
    if rule_file.endswith("/"):
        (source / rule_file.removesuffix("/")).mkdir()
        return
    (source / rule_file).write_text("rules\n", encoding="utf-8")


def _tree(folder: Path) -> dict[str, tuple]:
    found = {}
    for path in folder.rglob("*"):
        relative = str(path.relative_to(folder))
        if path.is_symlink():
            found[relative] = ("symlink", str(path.readlink()))
        elif path.is_file():
            found[relative] = ("file", path.read_bytes())
    return found


def test_report_an_ok_source(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "log-daemon", origin="git@github.com:me/log-daemon.git")
    assert main(["link", "log-daemon", str(source)]) == 0
    before = _tree(atlas)
    capsys.readouterr()

    def fail_on_git(*args, **kwargs):
        raise AssertionError(args)

    monkeypatch.setattr(subprocess, "run", fail_on_git)
    assert main(["doctor"]) == 0

    assert capsys.readouterr().out == "ok log-daemon\n"
    assert _tree(atlas) == before


def test_suggest_clone_and_link_when_a_source_is_missing(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "log-daemon", origin="git@github.com:me/log-daemon.git")
    assert main(["link", "log-daemon", str(source)]) == 0
    (atlas / "log-daemon").unlink()
    before = _tree(atlas)
    capsys.readouterr()

    assert main(["doctor"]) == 1

    assert capsys.readouterr().out == (
        "missing log-daemon\n"
        "git clone git@github.com:me/log-daemon.git ../log-daemon\n"
        "atlas link log-daemon ../log-daemon\n"
    )
    assert _tree(atlas) == before


def test_suggest_only_link_when_a_missing_source_has_no_remote(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "notes")
    assert main(["link", "notes", str(source)]) == 0
    (atlas / "notes").unlink()
    capsys.readouterr()

    assert main(["doctor"]) == 1

    assert capsys.readouterr().out == "missing notes\natlas link notes <path>\n"


def test_treat_a_real_file_as_missing(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "notes")
    assert main(["link", "notes", str(source)]) == 0
    (atlas / "notes").unlink()
    (atlas / "notes").write_text("keep me", encoding="utf-8")
    capsys.readouterr()

    assert main(["doctor"]) == 1

    assert capsys.readouterr().out == "missing notes\natlas link notes <path>\n"
    assert (atlas / "notes").read_text(encoding="utf-8") == "keep me"


def test_report_a_dangling_symlink_as_broken(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "log-daemon", origin="git@github.com:me/log-daemon.git")
    assert main(["link", "log-daemon", str(source)]) == 0
    (atlas / "log-daemon").unlink()
    (atlas / "log-daemon").symlink_to(tmp_path / "gone")
    target = (atlas / "log-daemon").readlink()
    before = _tree(atlas)
    capsys.readouterr()

    assert main(["doctor"]) == 1

    assert capsys.readouterr().out == f"broken log-daemon -> {target}\n"
    assert _tree(atlas) == before


def test_flag_a_symlink_that_is_not_declared(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "scratch")
    (atlas / "scratch").symlink_to(source)
    target = (atlas / "scratch").readlink()
    before = _tree(atlas)
    capsys.readouterr()

    assert main(["doctor"]) == 1

    assert capsys.readouterr().out == f"undeclared scratch\natlas link scratch {shlex.quote(str(target))}\n"
    assert _tree(atlas) == before


def test_list_findings_in_declaration_order_then_undeclared_names(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    atlas_source = _source(tmp_path / "atlas")
    missing = _source(tmp_path / "log-daemon", origin="git@github.com:me/log-daemon.git")
    broken = _source(tmp_path / "notes", origin="git@github.com:me/notes.git")
    assert main(["link", "atlas", str(atlas_source)]) == 0
    assert main(["link", "log-daemon", str(missing)]) == 0
    assert main(["link", "notes", str(broken)]) == 0
    (atlas / "log-daemon").unlink()
    (atlas / "notes").unlink()
    (atlas / "notes").symlink_to(tmp_path / "gone")
    (atlas / "zebra").symlink_to(tmp_path / "zebra")
    (atlas / "alpha").symlink_to(tmp_path / "alpha")
    target = (atlas / "notes").readlink()
    alpha = shlex.quote(str((atlas / "alpha").readlink()))
    zebra = shlex.quote(str((atlas / "zebra").readlink()))
    capsys.readouterr()

    assert main(["doctor"]) == 1

    assert capsys.readouterr().out == (
        "ok atlas\n"
        "missing log-daemon\n"
        "git clone git@github.com:me/log-daemon.git ../log-daemon\n"
        "atlas link log-daemon ../log-daemon\n"
        f"broken notes -> {target}\n"
        "undeclared alpha\n"
        f"atlas link alpha {alpha}\n"
        "undeclared zebra\n"
        f"atlas link zebra {zebra}\n"
    )


def test_say_nothing_when_every_source_is_in_place(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    capsys.readouterr()

    assert main(["doctor"]) == 0

    assert capsys.readouterr().out == ""
    assert not (atlas / "doctor.txt").exists()


def test_refuse_when_the_folder_is_not_an_atlas(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["doctor"]) == 1

    assert list(tmp_path.iterdir()) == []
    out = capsys.readouterr().out
    assert "not an Atlas" in out
    assert "nothing was changed" in out


@pytest.mark.parametrize(
    "rule_file",
    ["CLAUDE.md", "CLAUDE.local.md", ".claude/", "AGENTS.md", ".cursorrules"],
)
def test_flag_one_rule_file_at_the_source_top_level(tmp_path, monkeypatch, capsys, rule_file):
    _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "log-daemon")
    assert main(["link", "log-daemon", str(source)]) == 0
    _place_rule_file(source, rule_file)
    capsys.readouterr()

    assert main(["doctor"]) == 1

    assert capsys.readouterr().out == f"ok log-daemon\nrules log-daemon: {rule_file}\n"


def test_list_every_rule_file_in_order(tmp_path, monkeypatch, capsys):
    _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "log-daemon")
    assert main(["link", "log-daemon", str(source)]) == 0
    for rule_file in (".cursorrules", "AGENTS.md", ".claude/", "CLAUDE.local.md", "CLAUDE.md"):
        _place_rule_file(source, rule_file)
    capsys.readouterr()

    assert main(["doctor"]) == 1

    assert capsys.readouterr().out == (
        "ok log-daemon\n"
        "rules log-daemon: CLAUDE.md, CLAUDE.local.md, .claude/, AGENTS.md, .cursorrules\n"
    )


def test_leave_a_clean_source_out_of_the_rules_report(tmp_path, monkeypatch, capsys):
    _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "log-daemon")
    (source / "README.md").write_text("notes\n", encoding="utf-8")
    assert main(["link", "log-daemon", str(source)]) == 0
    capsys.readouterr()

    assert main(["doctor"]) == 0

    output = capsys.readouterr().out
    assert output == "ok log-daemon\n"
    assert "rules " not in output


def test_ignore_a_rule_file_below_the_source_top_level(tmp_path, monkeypatch, capsys):
    _atlas(tmp_path, monkeypatch)
    source = _source(tmp_path / "log-daemon")
    nested = source / "sub"
    nested.mkdir()
    (nested / "CLAUDE.md").write_text("nested\n", encoding="utf-8")
    assert main(["link", "log-daemon", str(source)]) == 0
    capsys.readouterr()

    assert main(["doctor"]) == 0

    assert capsys.readouterr().out == "ok log-daemon\n"


def test_refuse_unreadable_toml_and_change_nothing(tmp_path, monkeypatch, capsys):
    atlas = _atlas(tmp_path, monkeypatch)
    toml_path = atlas / "_settings/atlas.toml"
    toml_path.write_text("version = [\n", encoding="utf-8")
    before = _tree(atlas)
    capsys.readouterr()

    assert main(["doctor"]) == 1

    assert _tree(atlas) == before
    assert "nothing was changed" in capsys.readouterr().out
