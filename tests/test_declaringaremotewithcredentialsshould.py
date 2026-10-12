import tomllib
from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext, orient_sources

_SECRET = "https://me:s3cr3t-token@github.com/me/log-daemon.git"
_CLEAN = "https://github.com/me/log-daemon.git"


def _remote(atlas: Path, name: str) -> str | None:
    settings = tomllib.loads((atlas / "_settings/atlas.toml").read_text(encoding="utf-8"))
    return settings["sources"][name].get("remote")


def _toml(atlas: Path) -> str:
    return (atlas / "_settings/atlas.toml").read_text(encoding="utf-8")


def test_declare_the_remote_without_its_credentials(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"], origins={"log-daemon": _SECRET}) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0

        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0

        assert _remote(world.atlas, "log-daemon") == _CLEAN
        assert "s3cr3t" not in _toml(world.atlas)


def test_drop_a_bare_user_too(monkeypatch):
    azure = "https://org@dev.azure.com/org/project/_git/repo"
    with EphemeralAtlasContext(git_sources=["repo"], origins={"repo": azure}) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0

        assert main(["link", "repo", str(world.source("repo"))]) == 0

        assert _remote(world.atlas, "repo") == "https://dev.azure.com/org/project/_git/repo"


def test_keep_an_scp_like_origin_as_it_is(monkeypatch):
    scp = "git@github.com:me/log-daemon.git"
    with EphemeralAtlasContext(git_sources=["log-daemon"], origins={"log-daemon": scp}) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0

        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0

        assert _remote(world.atlas, "log-daemon") == scp


def test_rebind_the_remote_without_its_credentials(monkeypatch):
    with EphemeralAtlasContext(
        git_sources=["old-log-daemon", "new-log-daemon"], origins={"new-log-daemon": _SECRET}
    ) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("old-log-daemon"))]) == 0

        assert main(["link", "log-daemon", str(world.source("new-log-daemon"))]) == 0

        assert _remote(world.atlas, "log-daemon") == _CLEAN
        assert "s3cr3t" not in _toml(world.atlas)


def test_migrate_the_remote_without_its_credentials(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"], origins={"log-daemon": _SECRET}) as world:
        atlas = world.atlas
        (atlas / "CLAUDE.md").write_text("# acme\n", encoding="utf-8")
        (atlas / "STATUS.md").write_text("# acme — STATUS\n", encoding="utf-8")
        (atlas / "log-daemon").symlink_to(world.source("log-daemon"), target_is_directory=True)
        monkeypatch.chdir(atlas)

        assert main(["migrate", "--apply"]) == 0

        assert _remote(atlas, "log-daemon") == _CLEAN
        assert "s3cr3t" not in _toml(atlas)
        assert "s3cr3t" not in capsys.readouterr().out


def test_flag_a_declared_remote_that_carries_credentials_and_say_how_to_rewrite_it(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        orient_sources(atlas, "log-daemon")
        _declare_remote(atlas, "log-daemon", _SECRET)
        target = (atlas / "log-daemon").readlink()
        capsys.readouterr()

        assert main(["doctor"]) == 1

        out = capsys.readouterr().out
        assert out == (
            "ok log-daemon\n"
            "credentials log-daemon -> https://…@github.com/me/log-daemon.git\n"
            f"atlas link log-daemon {target}\n"
        )
        assert "s3cr3t" not in out


def test_flag_a_missing_source_whose_remote_carries_credentials_without_a_rewrite_hint(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        orient_sources(atlas, "log-daemon")
        _declare_remote(atlas, "log-daemon", _SECRET)
        (atlas / "log-daemon").unlink()
        capsys.readouterr()

        assert main(["doctor"]) == 1

        out = capsys.readouterr().out
        assert out == (
            "missing log-daemon\n"
            f"git clone {_CLEAN} ../log-daemon\n"
            "atlas link log-daemon ../log-daemon\n"
            "credentials log-daemon -> https://…@github.com/me/log-daemon.git\n"
        )
        assert "s3cr3t" not in out


def test_flag_a_broken_source_whose_remote_carries_credentials_without_a_rewrite_hint(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        orient_sources(atlas, "log-daemon")
        _declare_remote(atlas, "log-daemon", _SECRET)
        (atlas / "log-daemon").unlink()
        (atlas / "log-daemon").symlink_to(world.root / "gone")
        capsys.readouterr()

        assert main(["doctor"]) == 1

        out = capsys.readouterr().out
        assert out == (
            f"broken log-daemon -> {world.root / 'gone'}\n"
            "credentials log-daemon -> https://…@github.com/me/log-daemon.git\n"
        )
        assert "s3cr3t" not in out


def test_rewrite_the_remote_when_the_suggested_link_is_run(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"], origins={"log-daemon": _SECRET}) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        orient_sources(atlas, "log-daemon")
        _declare_remote(atlas, "log-daemon", _SECRET)
        target = (atlas / "log-daemon").readlink()

        assert main(["link", "log-daemon", str(target)]) == 0
        capsys.readouterr()
        assert main(["doctor"]) == 0

        assert _remote(atlas, "log-daemon") == _CLEAN
        assert capsys.readouterr().out == "ok log-daemon\n"


def _declare_remote(atlas: Path, name: str, remote: str) -> None:
    path = atlas / "_settings/atlas.toml"
    text = path.read_text(encoding="utf-8")
    header = f"[sources.{name}]\n"
    start = text.index(header) + len(header)
    end = text.find("\n[", start)
    end = len(text) if end == -1 else end + 1
    path.write_text(text[:start] + f'remote = "{remote}"\n' + text[end:], encoding="utf-8", newline="\n")
