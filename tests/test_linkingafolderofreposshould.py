import json
import shlex
import shutil
import subprocess
import tomllib
from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext, orient_sources

_GROUP = {"infra": ["gke-logy", "gke-n8n"]}


def _settings(atlas: Path) -> dict:
    return tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))


def _scan(atlas: Path) -> list[str]:
    return json.loads((atlas / ".vscode/settings.json").read_text(encoding="utf-8"))["git.scanRepositories"]


def _init_and_link(world: EphemeralAtlasContext, monkeypatch) -> Path:
    monkeypatch.chdir(world.atlas)
    assert main(["init"]) == 0
    assert main(["link", "infra", str(world.source("infra"))]) == 0
    orient_sources(world.atlas, "infra")
    return world.atlas


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def test_declare_each_repo_inside_the_folder_with_its_remote(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        atlas = _init_and_link(world, monkeypatch)

        source = _settings(atlas)["sources"]["infra"]
        assert "remote" not in source
        assert source["repos"] == {
            "gke-logy": {"remote": world.origin("infra/gke-logy")},
            "gke-n8n": {"remote": world.origin("infra/gke-n8n")},
        }
        assert _scan(atlas) == ["infra/gke-logy", "infra/gke-n8n"]
        claude = json.loads((atlas / ".claude/settings.local.json").read_text(encoding="utf-8"))
        assert claude["permissions"]["additionalDirectories"] == [str(world.source("infra").resolve())]


def test_keep_the_declaration_readable_as_one_section_per_repo(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        atlas = _init_and_link(world, monkeypatch)

        text = (atlas / "_settings/atlas.toml").read_text(encoding="utf-8")
        assert "[sources.infra]\n\n[sources.infra.repos.gke-logy]\nremote = " in text
        assert "\n\n[sources.infra.repos.gke-n8n]\nremote = " in text


def test_declare_a_folder_with_no_git_children_as_today(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["notes"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        (world.source("notes") / "drafts").mkdir()

        assert main(["link", "notes", str(world.source("notes"))]) == 0

        assert _settings(world.atlas)["sources"]["notes"] == {}
        assert _scan(world.atlas) == ["notes"]


def test_rescan_the_folder_on_rebind(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        atlas = _init_and_link(world, monkeypatch)
        new = world.source("infra") / "gke-rocket"
        subprocess.run(["git", "init", "-q", "-b", "main", str(new)], check=True)
        _git(new, "remote", "add", "origin", "https://github.com/me/gke-rocket.git")

        assert main(["link", "infra", str(world.source("infra"))]) == 0

        repos = _settings(atlas)["sources"]["infra"]["repos"]
        assert list(repos) == ["gke-logy", "gke-n8n", "gke-rocket"]
        assert repos["gke-rocket"] == {"remote": "https://github.com/me/gke-rocket.git"}
        assert _scan(atlas) == ["infra/gke-logy", "infra/gke-n8n", "infra/gke-rocket"]


def test_store_a_nested_remote_without_credentials(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        _git(world.source("infra") / "gke-logy", "remote", "set-url", "origin", "https://me:t0ken@dev.azure.com/o/p/_git/gke-logy")

        atlas = _init_and_link(world, monkeypatch)

        assert _settings(atlas)["sources"]["infra"]["repos"]["gke-logy"] == {"remote": "https://dev.azure.com/o/p/_git/gke-logy"}
        assert "t0ken" not in (atlas / "_settings/atlas.toml").read_text(encoding="utf-8")


def test_migrate_a_folder_of_repos(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        atlas = world.atlas
        (atlas / "CLAUDE.md").write_text("# acme\n", encoding="utf-8")
        (atlas / "STATUS.md").write_text("# acme — STATUS\n", encoding="utf-8")
        (atlas / "infra").symlink_to(world.source("infra"), target_is_directory=True)
        monkeypatch.chdir(atlas)

        assert main(["migrate", "--apply"]) == 0

        assert list(_settings(atlas)["sources"]["infra"]["repos"]) == ["gke-logy", "gke-n8n"]
        assert _scan(atlas) == ["infra/gke-logy", "infra/gke-n8n"]
        assert "declared infra (folder of 2 repos: gke-logy, gke-n8n)" in capsys.readouterr().out


def test_unlink_the_folder_with_every_repo_in_it(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"], grouped_sources=_GROUP) as world:
        atlas = _init_and_link(world, monkeypatch)
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0

        assert main(["unlink", "infra"]) == 0

        assert list(_settings(atlas)["sources"]) == ["log-daemon"]
        assert "infra" not in (atlas / "_settings/atlas.toml").read_text(encoding="utf-8")
        assert _scan(atlas) == ["log-daemon"]
        assert not (atlas / "infra").exists()


def test_doctor_says_ok_when_every_repo_is_there(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        _init_and_link(world, monkeypatch)
        capsys.readouterr()

        assert main(["doctor"]) == 0

        assert capsys.readouterr().out == "ok infra\n"


def test_doctor_suggests_the_clone_of_a_missing_nested_repo(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        _init_and_link(world, monkeypatch)
        shutil.rmtree(world.source("infra") / "gke-n8n")
        capsys.readouterr()

        assert main(["doctor"]) == 1

        assert capsys.readouterr().out == (
            "ok infra\n"
            "missing infra/gke-n8n\n"
            f"git clone {shlex.quote(world.origin('infra/gke-n8n'))} infra/gke-n8n\n"
        )


def test_doctor_flags_a_repo_that_appeared_in_the_folder_undeclared(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        atlas = _init_and_link(world, monkeypatch)
        subprocess.run(["git", "init", "-q", str(world.source("infra") / "gke-new")], check=True)
        capsys.readouterr()

        assert main(["doctor"]) == 1

        target = shlex.quote(str((atlas / "infra").readlink()))
        assert capsys.readouterr().out == f"ok infra\nundeclared infra/gke-new\natlas link infra {target}\n"


def test_doctor_suggests_every_clone_when_the_folder_is_missing(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        atlas = _init_and_link(world, monkeypatch)
        (atlas / "infra").unlink()
        capsys.readouterr()

        assert main(["doctor"]) == 1

        assert capsys.readouterr().out == (
            "missing infra\n"
            f"git clone {shlex.quote(world.origin('infra/gke-logy'))} ../infra/gke-logy\n"
            f"git clone {shlex.quote(world.origin('infra/gke-n8n'))} ../infra/gke-n8n\n"
            "atlas link infra ../infra\n"
        )


def test_doctor_flags_rule_files_inside_a_nested_repo(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        _init_and_link(world, monkeypatch)
        (world.source("infra") / "gke-n8n" / "CLAUDE.md").write_text("rules\n", encoding="utf-8")
        capsys.readouterr()

        assert main(["doctor"]) == 0

        assert capsys.readouterr().out.splitlines()[:2] == ["ok infra", "rules infra/gke-n8n: CLAUDE.md"]


def test_status_reports_each_nested_repo_and_the_spec_branch(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        atlas = _init_and_link(world, monkeypatch)
        (atlas / "SPEC_0007_LOGS.md").write_text("# SPEC_0007_LOGS\nrepos: infra/gke-logy\n", encoding="utf-8")
        (atlas / "STATUS.md").write_text("## Active\n\n### SPEC_0007_LOGS — IN PROGRESS\n- **Next:** go\n", encoding="utf-8")
        _git(world.source("infra") / "gke-logy", "switch", "-q", "-c", "spec/0007-logs")
        (world.source("infra") / "gke-n8n" / "new.txt").write_text("x\n", encoding="utf-8")
        capsys.readouterr()

        assert main(["status"]) == 0

        out = capsys.readouterr().out
        assert "  infra/gke-logy: spec/0007-logs, 0 changed — on SPEC_0007's branch\n" in out
        assert "  infra/gke-n8n: main, 1 changed\n" in out
        assert "  infra:" not in out


def test_status_reports_a_paused_stash_in_a_nested_repo(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        _init_and_link(world, monkeypatch)
        repo = world.source("infra") / "gke-n8n"
        (repo / "new.txt").write_text("x\n", encoding="utf-8")
        _git(repo, "stash", "push", "-q", "-u", "-m", "SPEC_0007 paused")
        capsys.readouterr()

        assert main(["status"]) == 0

        assert "Paused\n  infra/gke-n8n: stash@{0} — SPEC_0007\n" in capsys.readouterr().out


def test_doctor_reports_a_missing_nested_repo_without_a_remote_with_no_hint(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        _git(world.source("infra") / "gke-n8n", "remote", "remove", "origin")
        _init_and_link(world, monkeypatch)
        shutil.rmtree(world.source("infra") / "gke-n8n")
        capsys.readouterr()

        assert main(["doctor"]) == 1

        assert capsys.readouterr().out == "ok infra\nmissing infra/gke-n8n\n"


def test_doctor_flags_credentials_in_a_nested_remote_with_the_link_that_rewrites_it(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        atlas = _init_and_link(world, monkeypatch)
        path = atlas / "_settings/atlas.toml"
        text = path.read_text(encoding="utf-8").replace(
            f'remote = "{world.origin("infra/gke-n8n")}"', 'remote = "https://me:t0ken@github.com/me/gke-n8n.git"'
        )
        path.write_text(text, encoding="utf-8", newline="\n")
        target = shlex.quote(str((atlas / "infra").readlink()))
        capsys.readouterr()

        assert main(["doctor"]) == 1

        out = capsys.readouterr().out
        assert out == f"ok infra\ncredentials infra/gke-n8n -> https://…@github.com/me/gke-n8n.git\natlas link infra {target}\n"
        assert "t0ken" not in out


def test_doctor_flags_a_repo_that_appeared_in_a_plain_folder(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["notes"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "notes", str(world.source("notes"))]) == 0
        orient_sources(world.atlas, "notes")
        subprocess.run(["git", "init", "-q", str(world.source("notes") / "tool")], check=True)
        capsys.readouterr()

        assert main(["doctor"]) == 1

        target = shlex.quote(str((world.atlas / "notes").readlink()))
        assert capsys.readouterr().out == f"ok notes\nundeclared notes/tool\natlas link notes {target}\n"


def test_keep_the_editor_entries_where_they_were_on_rebind(monkeypatch):
    with EphemeralAtlasContext(git_sources=["a", "b"], grouped_sources=_GROUP) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "a", str(world.source("a"))]) == 0
        assert main(["link", "infra", str(world.source("infra"))]) == 0
        assert main(["link", "b", str(world.source("b"))]) == 0

        assert main(["link", "infra", str(world.source("infra"))]) == 0
        assert main(["link", "a", str(world.source("a"))]) == 0

        assert _scan(world.atlas) == ["a", "infra/gke-logy", "infra/gke-n8n", "b"]


def test_unlink_a_folder_whose_name_prefixes_another_source(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], grouped_sources={"infra": ["x"], "infra2": ["y"]}) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "infra", str(world.source("infra"))]) == 0
        assert main(["link", "infra2", str(world.source("infra2"))]) == 0

        assert main(["unlink", "infra"]) == 0

        assert list(_settings(world.atlas)["sources"]) == ["infra2"]
        assert _settings(world.atlas)["sources"]["infra2"]["repos"] == {"y": {"remote": world.origin("infra2/y")}}
        assert _scan(world.atlas) == ["infra2/y"]


def test_refuse_a_rebind_when_the_declaration_has_an_unexpected_shape(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], grouped_sources=_GROUP) as world:
        atlas = _init_and_link(world, monkeypatch)
        path = atlas / "_settings/atlas.toml"
        text = path.read_text(encoding="utf-8")
        header = "[sources.infra]\n"
        orphan = f"[sources.infra.repos.gke-zz]\nremote = \"https://github.com/me/zz.git\"\n\n"
        path.write_text(text.replace(header, orphan + header), encoding="utf-8", newline="\n")
        before = path.read_bytes()
        capsys.readouterr()

        assert main(["link", "infra", str(world.source("infra"))]) == 1

        assert path.read_bytes() == before
        assert "unexpected shape" in capsys.readouterr().out
