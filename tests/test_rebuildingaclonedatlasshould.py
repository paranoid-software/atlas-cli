import shlex
import subprocess
import tomllib
from pathlib import Path

from atlas_cli.cli import main

from tests.ephemeralatlascontext import EphemeralAtlasContext, orient_sources


def test_rebuild_a_cloned_atlas_with_the_links_doctor_suggests(monkeypatch, capsys):
    with EphemeralAtlasContext(["log-daemon", "atlas-cli"]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        assert main(["workbench", "add", "claude"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        assert main(["link", "atlas-cli", str(world.source("atlas-cli"))]) == 0
        orient_sources(world.atlas, "log-daemon", "atlas-cli")
        capsys.readouterr()

        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=world.atlas, check=True)
        subprocess.run(["git", "add", "-A"], cwd=world.atlas, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "Declare the sources"], cwd=world.atlas, check=True)
        clone = world.root / "rebuilt"
        subprocess.run(["git", "clone", "-q", str(world.atlas), str(clone)], check=True)
        assert not (clone / ".claude" / "settings.local.json").exists()

        monkeypatch.chdir(clone)
        before = (clone / "_settings" / "atlas.toml").read_bytes()
        assert main(["doctor"]) == 1
        report = capsys.readouterr().out
        assert report == _missing_report(world.atlas)
        assert (clone / "_settings" / "atlas.toml").read_bytes() == before

        for line in report.splitlines():
            if line.startswith("atlas link "):
                assert main(shlex.split(line)[1:]) == 0

        claude = clone / ".claude" / "settings.local.json"
        assert claude.is_file()
        capsys.readouterr()
        assert main(["doctor"]) == 0
        assert capsys.readouterr().out == "ok log-daemon\nok atlas-cli\n"


def _missing_report(atlas: Path) -> str:
    declared = tomllib.loads((atlas / "_settings" / "atlas.toml").read_text(encoding="utf-8"))["sources"]
    lines = []
    for name, table in declared.items():
        destination = shlex.quote(f"../{name}")
        lines.append(f"missing {name}")
        lines.append(f"git clone {shlex.quote(table['remote'])} {destination}")
        lines.append(f"atlas link {shlex.quote(name)} {destination}")
    lines.append("workbench claude: missing")
    lines.append("atlas workbench add claude")
    return "\n".join(lines) + "\n"
