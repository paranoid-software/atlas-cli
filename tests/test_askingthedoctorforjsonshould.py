import json
import shlex
import shutil
import subprocess
from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext, orient_sources

_SECRET = "https://me:s3cr3t-token@github.com/me/vault.git"
_KINDS = ("missing ", "broken ", "undeclared ", "rules ", "unoriented ", "placeholder ", "credentials ")


def test_report_a_clean_atlas_as_ok_with_its_sources(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["log-daemon", "notes"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        assert main(["link", "notes", str(world.source("notes"))]) == 0
        orient_sources(atlas, "log-daemon", "notes")
        capsys.readouterr()

        assert main(["doctor", "--json"]) == 0

        expected = {
            "ok": True,
            "sources": [
                {"name": "log-daemon", "state": "ok", "target": str((atlas / "log-daemon").readlink())},
                {"name": "notes", "state": "ok", "target": str((atlas / "notes").readlink())},
            ],
            "findings": [],
        }
        assert capsys.readouterr().out == json.dumps(expected, indent=2, ensure_ascii=False) + "\n"


def test_report_every_kind_of_finding_with_its_fix(monkeypatch, capsys):
    with EphemeralAtlasContext(
        git_sources=["log-daemon", "vault"],
        plain_sources=["ruled", "draft", "bare", "notes", "scratch"],
        grouped_sources={"infra": ["gke-logy", "gke-n8n"]},
    ) as world:
        atlas = _prepare_an_atlas_with_every_finding(world, monkeypatch)
        capsys.readouterr()

        assert main(["doctor", "--json"]) == 1

        expected = {
            "ok": False,
            "sources": [
                {"name": "ruled", "state": "ok", "target": str((atlas / "ruled").readlink())},
                {"name": "draft", "state": "ok", "target": str((atlas / "draft").readlink())},
                {"name": "bare", "state": "ok", "target": str((atlas / "bare").readlink())},
                {"name": "log-daemon", "state": "missing", "target": None},
                {"name": "notes", "state": "broken", "target": str((atlas / "notes").readlink())},
                {"name": "vault", "state": "ok", "target": str((atlas / "vault").readlink())},
                {
                    "name": "infra",
                    "state": "ok",
                    "target": str((atlas / "infra").readlink()),
                    "repos": [
                        {"name": "gke-logy", "state": "ok"},
                        {"name": "gke-n8n", "state": "missing"},
                    ],
                },
            ],
            "findings": [
                {"kind": "rules", "level": "notice", "subject": "ruled", "detail": "CLAUDE.md", "fix": []},
                {"kind": "placeholder", "level": "problem", "subject": "draft", "detail": "<one paragraph>", "fix": []},
                {"kind": "unoriented", "level": "problem", "subject": "bare", "detail": None, "fix": []},
                {
                    "kind": "missing",
                    "level": "problem",
                    "subject": "log-daemon",
                    "detail": None,
                    "fix": [
                        f"git clone {shlex.quote(world.origin('log-daemon'))} ../log-daemon",
                        "atlas link log-daemon ../log-daemon",
                    ],
                },
                {"kind": "broken", "level": "problem", "subject": "notes", "detail": str((atlas / "notes").readlink()), "fix": []},
                {
                    "kind": "credentials",
                    "level": "problem",
                    "subject": "vault",
                    "detail": "https://…@github.com/me/vault.git",
                    "fix": [f"atlas link vault {shlex.quote(str((atlas / 'vault').readlink()))}"],
                },
                {
                    "kind": "missing",
                    "level": "problem",
                    "subject": "infra/gke-n8n",
                    "detail": None,
                    "fix": [f"git clone {shlex.quote(world.origin('infra/gke-n8n'))} infra/gke-n8n"],
                },
                {
                    "kind": "undeclared",
                    "level": "problem",
                    "subject": "infra/gke-new",
                    "detail": None,
                    "fix": [f"atlas link infra {shlex.quote(str((atlas / 'infra').readlink()))}"],
                },
                {
                    "kind": "undeclared",
                    "level": "problem",
                    "subject": "scratch",
                    "detail": None,
                    "fix": [f"atlas link scratch {shlex.quote(str((atlas / 'scratch').readlink()))}"],
                },
            ],
        }
        assert capsys.readouterr().out == json.dumps(expected, indent=2, ensure_ascii=False) + "\n"


def test_list_the_same_findings_as_the_text_report(monkeypatch, capsys):
    with EphemeralAtlasContext(
        git_sources=["log-daemon", "vault"],
        plain_sources=["ruled", "draft", "bare", "notes", "scratch"],
        grouped_sources={"infra": ["gke-logy", "gke-n8n"]},
    ) as world:
        _prepare_an_atlas_with_every_finding(world, monkeypatch)
        capsys.readouterr()

        assert main(["doctor"]) == 1
        text = capsys.readouterr().out
        assert main(["doctor", "--json"]) == 1
        report = json.loads(capsys.readouterr().out)

        assert [(finding["kind"], finding["subject"]) for finding in report["findings"]] == _finding_lines(text)


def test_report_the_nested_repos_of_a_folder_of_repos(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[], grouped_sources={"infra": ["gke-logy", "gke-n8n"]}) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["link", "infra", str(world.source("infra"))]) == 0
        orient_sources(atlas, "infra")
        shutil.rmtree(world.source("infra") / "gke-n8n")
        capsys.readouterr()

        assert main(["doctor", "--json"]) == 1

        present = json.loads(capsys.readouterr().out)
        assert present["sources"] == [
            {
                "name": "infra",
                "state": "ok",
                "target": str((atlas / "infra").readlink()),
                "repos": [
                    {"name": "gke-logy", "state": "ok"},
                    {"name": "gke-n8n", "state": "missing"},
                ],
            }
        ]

        (atlas / "infra").unlink()
        assert main(["doctor", "--json"]) == 1

        missing = json.loads(capsys.readouterr().out)
        assert missing["sources"] == [
            {
                "name": "infra",
                "state": "missing",
                "target": None,
                "repos": [
                    {"name": "gke-logy", "state": "missing"},
                    {"name": "gke-n8n", "state": "missing"},
                ],
            }
        ]


def test_keep_credentials_out_of_the_json(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        orient_sources(atlas, "log-daemon")
        _declare_remote(atlas, "log-daemon", "https://me:s3cr3t-token@github.com/me/log-daemon.git")
        (atlas / "log-daemon").unlink()
        capsys.readouterr()

        assert main(["doctor", "--json"]) == 1

        out = capsys.readouterr().out
        report = json.loads(out)
        assert "s3cr3t" not in out
        assert "https://me:s3cr3t-token@github.com/me/log-daemon.git" not in out
        missing, credentials = report["findings"]
        assert missing["fix"] == [
            "git clone https://github.com/me/log-daemon.git ../log-daemon",
            "atlas link log-daemon ../log-daemon",
        ]
        assert credentials == {
            "kind": "credentials",
            "level": "problem",
            "subject": "log-daemon",
            "detail": "https://…@github.com/me/log-daemon.git",
            "fix": [],
        }


def test_report_an_error_as_json_outside_an_atlas(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert main(["doctor", "--json"]) == 1

    out = capsys.readouterr().out
    assert out == json.dumps(
        {"ok": False, "error": "This folder is not an Atlas (no _settings/atlas.toml)"},
        ensure_ascii=False,
    ) + "\n"
    assert "nothing was changed" not in out
    assert list(tmp_path.iterdir()) == []


def test_exit_with_the_same_code_as_the_text_report(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = world.atlas
        monkeypatch.chdir(atlas)
        assert main(["init"]) == 0
        assert main(["link", "log-daemon", str(world.source("log-daemon"))]) == 0
        orient_sources(atlas, "log-daemon")
        capsys.readouterr()

        assert main(["doctor"]) == main(["doctor", "--json"]) == 0

        (atlas / "log-daemon").unlink()
        capsys.readouterr()

        assert main(["doctor"]) == main(["doctor", "--json"]) == 1


def _prepare_an_atlas_with_every_finding(world: EphemeralAtlasContext, monkeypatch) -> Path:
    atlas = world.atlas
    monkeypatch.chdir(atlas)
    assert main(["init"]) == 0
    for name in ("ruled", "draft", "bare", "log-daemon", "notes", "vault", "infra"):
        assert main(["link", name, str(world.source(name))]) == 0
    orient_sources(atlas, "ruled", "draft", "log-daemon", "notes", "vault", "infra")
    claude = atlas / "CLAUDE.md"
    claude.write_text(
        claude.read_text(encoding="utf-8").replace(
            "- **Contributes:** draft does its part.",
            "- **Contributes:** <one paragraph>",
        ),
        encoding="utf-8",
        newline="\n",
    )
    (world.source("ruled") / "CLAUDE.md").write_text("rules\n", encoding="utf-8")
    (atlas / "log-daemon").unlink()
    (atlas / "notes").unlink()
    (atlas / "notes").symlink_to(world.root / "gone")
    _declare_remote(atlas, "vault", _SECRET)
    shutil.rmtree(world.source("infra") / "gke-n8n")
    subprocess.run(["git", "init", "-q", str(world.source("infra") / "gke-new")], check=True)
    (atlas / "scratch").symlink_to(world.source("scratch"))
    return atlas


def _declare_remote(atlas: Path, name: str, remote: str) -> None:
    path = atlas / "_settings/atlas.toml"
    text = path.read_text(encoding="utf-8")
    header = f"[sources.{name}]\n"
    start = text.index(header) + len(header)
    end = text.find("\n[", start)
    end = len(text) if end == -1 else end + 1
    path.write_text(text[:start] + f'remote = "{remote}"\n' + text[end:], encoding="utf-8", newline="\n")


def _finding_lines(text: str) -> list[tuple[str, str]]:
    found = []
    for line in text.splitlines():
        for prefix in _KINDS:
            if line.startswith(prefix):
                rest = line[len(prefix):]
                subject = rest.split(" -> ", 1)[0].split(": ", 1)[0]
                found.append((prefix.rstrip(), subject))
                break
    return found
