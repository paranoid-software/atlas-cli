import json
import os
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from atlas_cli.cli import main
from atlas_cli.commands.ui import make_server
from tests.ephemeralatlascontext import EphemeralAtlasContext

_STATUS = "# acme — STATUS (living)\n\n## Active\n\n### SPEC_0002_ACTIVE_WORK — IN PROGRESS\n- **Next:** go\n\n## Recently closed\n"
_BACKLOG = "# acme — BACKLOG\n\n## Open\n- SPEC_0003_QUEUED_WORK — later\n"


@contextmanager
def _server(atlas: Path):
    server = make_server(atlas, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def _get_json(port: int, path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as response:
        return json.loads(response.read().decode("utf-8"))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _atlas(world: EphemeralAtlasContext, monkeypatch) -> Path:
    monkeypatch.chdir(world.atlas)
    assert main(["init"]) == 0
    return world.atlas


def _corpus(atlas: Path) -> dict:
    with _server(atlas) as port:
        return _get_json(port, "/api/corpus")


def _by_name(corpus: dict) -> dict:
    return {spec["name"]: spec for spec in corpus["specs"]}


def _tree(folder: Path) -> dict[str, bytes]:
    return {str(path.relative_to(folder)): path.read_bytes() for path in sorted(folder.rglob("*")) if path.is_file()}


def test_list_every_spec_with_its_place(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "STATUS.md", _STATUS)
        _write(atlas / "BACKLOG.md", _BACKLOG)
        _write(atlas / "SPEC_0002_ACTIVE_WORK.md", "# SPEC_0002_ACTIVE_WORK\n")
        _write(atlas / "SPEC_0003_QUEUED_WORK.md", "# SPEC_0003_QUEUED_WORK\n")
        _write(atlas / "_archived" / "SPEC_0001_DONE_WORK.md", "# SPEC_0001_DONE_WORK\n")
        _write(atlas / "SPEC_0004_LOST_WORK.md", "# SPEC_0004_LOST_WORK\n")

        specs = _by_name(_corpus(atlas))

    assert {name: (spec["place"], spec["file"], spec["title"]) for name, spec in specs.items()} == {
        "SPEC_0001_DONE_WORK": ("archived", "_archived/SPEC_0001_DONE_WORK.md", "Done work"),
        "SPEC_0002_ACTIVE_WORK": ("active", "SPEC_0002_ACTIVE_WORK.md", "Active work"),
        "SPEC_0003_QUEUED_WORK": ("backlog", "SPEC_0003_QUEUED_WORK.md", "Queued work"),
        "SPEC_0004_LOST_WORK": ("unplaced", "SPEC_0004_LOST_WORK.md", "Lost work"),
    }
    assert list(specs) == sorted(specs)


def test_read_the_header_stamps_repos_and_mode(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(
            atlas / "_archived" / "SPEC_0001_X.md",
            "# SPEC_0001_X\ncreated: 2026-10-01\nstarted: 2026-10-02\nclosed: 2026-10-05\n"
            "repos: atlas-cli,  atlas\nmode: paired\n\n## What\nstarted: not a stamp here\n",
        )
        _write(atlas / "SPEC_0002_Y.md", "# SPEC_0002_Y\ncreated: 2026-10-03\nrepos:\n")

        specs = _by_name(_corpus(atlas))

    first, second = specs["SPEC_0001_X"], specs["SPEC_0002_Y"]
    assert (first["number"], first["created"], first["started"], first["closed"]) == ("0001", "2026-10-01", "2026-10-02", "2026-10-05")
    assert (first["repos"], first["mode"]) == (["atlas-cli", "atlas"], "paired")
    assert (second["started"], second["closed"], second["repos"], second["mode"]) == (None, None, [], None)


def test_split_a_spec_into_its_sections(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(
            atlas / "SPEC_0002_X.md",
            "# SPEC_0002_X\ncreated: 2026-10-03\n\n## What\nThe goal.\n\n## Acceptance\n- one\n- two\n\n## Plan\n1. Step.\n",
        )

        spec = _by_name(_corpus(atlas))["SPEC_0002_X"]

    assert spec["sections"] == {"What": "The goal.", "Acceptance": "- one\n- two", "Plan": "1. Step."}
    assert list(spec["sections"]) == ["What", "Acceptance", "Plan"]


def test_attach_the_findings_beside_a_spec(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "SPEC_0002_X.md", "# SPEC_0002_X\n")
        _write(atlas / "SPEC_0002_FINDINGS.md", "# SPEC_0002 — findings\n\n- A finding.\n")
        _write(atlas / "_archived" / "SPEC_0001_Y.md", "# SPEC_0001_Y\n")
        _write(atlas / "_archived" / "SPEC_0001_FINDINGS.md", "# SPEC_0001 — findings\n\n- Old finding.\n")
        _write(atlas / "SPEC_0003_Z.md", "# SPEC_0003_Z\n")

        specs = _by_name(_corpus(atlas))

    assert specs["SPEC_0002_X"]["findings"] == "# SPEC_0002 — findings\n\n- A finding.\n"
    assert specs["SPEC_0001_Y"]["findings"] == "# SPEC_0001 — findings\n\n- Old finding.\n"
    assert specs["SPEC_0003_Z"]["findings"] is None


def test_ignore_findings_files_as_specs(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "SPEC_0002_X.md", "# SPEC_0002_X\n")
        _write(atlas / "SPEC_0002_FINDINGS.md", "# findings\n")
        _write(atlas / "_archived" / "SPEC_0001_FINDINGS.md", "# findings\n")

        specs = _by_name(_corpus(atlas))

    assert list(specs) == ["SPEC_0002_X"]


def test_list_the_drafts(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "DRAFT_ATLAS_UI.md", "# DRAFT_ATLAS_UI\n\nAn idea.\n")
        _write(atlas / "DRAFT_OTHER.md", "# DRAFT_OTHER\n")

        drafts = _corpus(atlas)["drafts"]

    assert drafts == [
        {"name": "DRAFT_ATLAS_UI", "file": "DRAFT_ATLAS_UI.md", "text": "# DRAFT_ATLAS_UI\n\nAn idea.\n"},
        {"name": "DRAFT_OTHER", "file": "DRAFT_OTHER.md", "text": "# DRAFT_OTHER\n"},
    ]


def test_report_the_coding_rules_in_force(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        assert main(["plugin", "add", "coding-rules", "mcp:coco"]) == 0
        candidates = (atlas / "CODING_RULES_CANDIDATES.md").read_text(encoding="utf-8")
        deviations = (atlas / "CODING_RULES_DEVIATIONS.md").read_text(encoding="utf-8")

        rules = _corpus(atlas)["rules"]

    assert rules == {"source": "mcp:coco", "candidates": candidates, "deviations": deviations}


def test_report_no_coding_rules_without_the_plugin(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)

        rules = _corpus(atlas)["rules"]

    assert rules == {"source": None, "candidates": None, "deviations": None}


def test_list_a_file_it_cannot_read_as_unreadable(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        (atlas / "SPEC_0002_BROKEN.md").write_bytes(b"# SPEC_0002_BROKEN\n\xff\xfe\n")
        _write(atlas / "SPEC_0003_FINE.md", "# SPEC_0003_FINE\n")

        corpus = _corpus(atlas)

    assert [spec["name"] for spec in corpus["specs"]] == ["SPEC_0003_FINE"]
    assert corpus["unreadable"] == ["SPEC_0002_BROKEN.md"]


def test_change_the_version_when_a_spec_changes(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        spec = atlas / "SPEC_0002_X.md"
        _write(spec, "# SPEC_0002_X\n")
        with _server(atlas) as port:
            first = _get_json(port, "/api/version")["version"]
            again = _get_json(port, "/api/version")["version"]
            _write(spec, "# SPEC_0002_X\n\n## What\nMore.\n")
            stat = spec.stat()
            os.utime(spec, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
            changed = _get_json(port, "/api/version")["version"]

    assert first == again
    assert changed != first


def test_write_nothing_while_serving_the_corpus(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "SPEC_0002_X.md", "# SPEC_0002_X\n")
        before = _tree(atlas)

        with _server(atlas) as port:
            for path in ("/api/corpus", "/api/version", "/api/corpus"):
                _get_json(port, path)

        assert _tree(atlas) == before


def test_change_the_version_when_status_claude_or_a_link_changes(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["notes"]) as world:
        atlas = _atlas(world, monkeypatch)
        versions = []
        with _server(atlas) as port:
            versions.append(_get_json(port, "/api/version")["version"])
            _write(atlas / "STATUS.md", _STATUS)
            versions.append(_get_json(port, "/api/version")["version"])
            _write(atlas / "AGENTS.md", "# acme\n\n## 1. What lives here\n")
            versions.append(_get_json(port, "/api/version")["version"])
            assert main(["link", "notes", str(world.source("notes"))]) == 0
            versions.append(_get_json(port, "/api/version")["version"])

    assert len(set(versions)) == 4


def test_list_an_unreadable_status_and_keep_serving_the_specs(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        (atlas / "STATUS.md").write_bytes(b"# STATUS\n\xff\xfe\n")
        _write(atlas / "SPEC_0002_X.md", "# SPEC_0002_X\n")

        corpus = _corpus(atlas)

    assert [spec["name"] for spec in corpus["specs"]] == ["SPEC_0002_X"]
    assert "STATUS.md" in corpus["unreadable"]


def test_bring_the_handoff_of_an_active_spec(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "STATUS.md", "# acme — STATUS (living)\n\n## Active\n\n### SPEC_0002_ACTIVE_WORK — IN REVIEW\n"
               "- **Done:** the endpoints.\n- **Next:** the page.\n\n## Recently closed\n")
        _write(atlas / "SPEC_0002_ACTIVE_WORK.md", "# SPEC_0002_ACTIVE_WORK\n")
        _write(atlas / "_archived" / "SPEC_0001_DONE.md", "# SPEC_0001_DONE\n")

        specs = _by_name(_corpus(atlas))

    assert specs["SPEC_0002_ACTIVE_WORK"]["status"] == "IN REVIEW"
    assert specs["SPEC_0002_ACTIVE_WORK"]["handoff"] == {"Done": "the endpoints.", "Next": "the page."}
    assert (specs["SPEC_0001_DONE"]["status"], specs["SPEC_0001_DONE"]["handoff"]) == (None, {})


def test_report_spec_files_with_an_older_name_without_reading_them(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "SPEC_0001_NEW_WORK.md", "# SPEC_0001 — New work\n")
        _write(atlas / "SPEC_DUAL_DISTRIBUTION.md", "# Dual distribution\n")
        _write(atlas / "_archived/SPEC_BASELINE_ALIGNMENT-2026-05-18.md", "# Baseline\n")
        _write(atlas / "_archived/SPEC_DUAL_FINDINGS.md", "- a finding\n")

        corpus = _corpus(atlas)

    assert list(_by_name(corpus)) == ["SPEC_0001_NEW_WORK"]
    assert corpus["unrecognized"] == ["SPEC_DUAL_DISTRIBUTION.md", "_archived/SPEC_BASELINE_ALIGNMENT-2026-05-18.md"]


def test_serve_an_archived_spec_without_stamps(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        atlas = _atlas(world, monkeypatch)
        _write(atlas / "_archived/SPEC_0001_OLD_WORK.md", "# SPEC_0001 — Old work\n\n## Goal\nDone long ago.\n")

        with _server(atlas) as port:
            spec = _by_name(_get_json(port, "/api/corpus"))["SPEC_0001_OLD_WORK"]
            timeline = _get_json(port, "/api/timeline?days=all")

    assert (spec["place"], spec["created"], spec["started"], spec["closed"]) == ("archived", None, None, None)
    assert timeline["events"] == []
