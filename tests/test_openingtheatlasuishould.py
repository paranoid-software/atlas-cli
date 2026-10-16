import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from atlas_cli.cli import main
from tests.ephemeralatlascontext import EphemeralAtlasContext, orient_sources

from atlas_cli.commands.ui import make_server


@contextmanager
def _server_context(atlas: Path, port: int):
    """Start a real server in a thread; return the port and stop it when done."""
    server = make_server(atlas, port)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield actual_port, server
    finally:
        server.shutdown()
        server.server_close()


def _get(url: str) -> tuple[int, str | None, dict]:
    """GET url, return (status_code, body_text_or_none, headers)."""
    try:
        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req)
        body = resp.read().decode("utf-8")
        return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, None, dict(exc.headers)


def _post(url: str) -> int:
    """POST url, return the status code."""
    try:
        req = urllib.request.Request(url, method="POST", data=b"")
        urllib.request.urlopen(req)
    except urllib.error.HTTPError as exc:
        return exc.code
    return 200


def _make_atlas(context: EphemeralAtlasContext, monkeypatch, *names: str) -> Path:
    """Initialise an Atlas and link the given sources so doctor/status work."""
    atlas = context.atlas
    monkeypatch.chdir(atlas)
    assert main(["init"]) == 0
    for name in names:
        assert main(["link", name, str(context.source(name))]) == 0
    orient_sources(atlas, *names)
    return atlas


def _declare_remote(atlas: Path, name: str, remote: str) -> None:
    path = atlas / "_settings/atlas.toml"
    text = path.read_text(encoding="utf-8")
    header = f"[sources.{name}]\n"
    start = text.index(header) + len(header)
    end = text.find("\n[", start)
    end = len(text) if end == -1 else end + 1
    path.write_text(
        text[:start] + f'remote = "{remote}"\n' + text[end:],
        encoding="utf-8",
        newline="\n",
    )


def test_serve_the_doctor_report_as_json(monkeypatch, capsys):
    with EphemeralAtlasContext(
        git_sources=["log-daemon", "vault"],
        plain_sources=["ruled", "draft", "bare", "notes", "scratch"],
        grouped_sources={"infra": ["gke-logy", "gke-n8n"]},
    ) as world:
        atlas = _make_atlas(
            world, monkeypatch,
            "ruled", "draft", "log-daemon", "notes", "vault", "infra",
        )
        (world.source("ruled") / "CLAUDE.md").write_text("rules\n", encoding="utf-8")
        claude = atlas / "CLAUDE.md"
        claude.write_text(
            claude.read_text(encoding="utf-8").replace(
                "- **Contributes:** draft does its part.",
                "- **Contributes:** <one paragraph>",
            ),
            encoding="utf-8",
            newline="\n",
        )
        (atlas / "log-daemon").unlink()
        (atlas / "notes").unlink()
        (atlas / "notes").symlink_to(world.root / "gone")
        _declare_remote(atlas, "vault", "https://me:s3cr3t-token@github.com/me/vault.git")

        capsys.readouterr()

        with _server_context(atlas, 0) as (port, server):
            base = f"http://127.0.0.1:{port}"
            status_code, body, _ = _get(f"{base}/api/doctor")
            assert status_code == 200
            report = json.loads(body)

            capsys.readouterr()
            assert main(["doctor", "--json"]) == 1
            assert report == json.loads(capsys.readouterr().out)
            assert "s3cr3t" not in body


def test_serve_the_status_text(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=["atlas-cli", "log-daemon", "notes"]) as world:
        atlas = _make_atlas(world, monkeypatch, "atlas-cli", "log-daemon", "notes")

        capsys.readouterr()

        with _server_context(atlas, 0) as (port, server):
            base = f"http://127.0.0.1:{port}"
            status_code, body, _ = _get(f"{base}/api/status")
            assert status_code == 200
            status_data = json.loads(body)
            assert status_data["code"] == 0

            capsys.readouterr()
            assert main(["status"]) == status_data["code"]
            assert capsys.readouterr().out == status_data["text"] + "\n"


def test_serve_the_page_and_its_static_files_with_their_types(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _make_atlas(world, monkeypatch, "log-daemon")

        with _server_context(atlas, 0) as (port, server):
            base = f"http://127.0.0.1:{port}"

            status_code, body, headers = _get(f"{base}/")
            assert status_code == 200
            assert body.lower().startswith("<!doctype html>")
            assert '<title>Atlas</title>' in body
            assert '<link rel="stylesheet" href="/static/atlas.css">' in body
            assert headers.get("Content-Type") == "text/html; charset=utf-8"
            assert headers.get("Cache-Control") == "no-store"

            status_code, body, headers = _get(f"{base}/static/atlas.css")
            assert status_code == 200
            assert "font: 15px/1.5 system-ui" in body
            assert headers.get("Content-Type") == "text/css; charset=utf-8"
            assert headers.get("Cache-Control") == "no-store"


def test_refuse_a_path_outside_the_page_and_the_api(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _make_atlas(world, monkeypatch, "log-daemon")

        with _server_context(atlas, 0) as (port, server):
            base = f"http://127.0.0.1:{port}"

            status_code, _, _ = _get(f"{base}/x")
            assert status_code == 404

            status_code, _, _ = _get(f"{base}/static/../cli.py")
            assert status_code == 404

            status_code, _, _ = _get(f"{base}/static/missing.css")
            assert status_code == 404


def test_refuse_a_request_that_is_not_a_get(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon"]) as world:
        atlas = _make_atlas(world, monkeypatch, "log-daemon")

        with _server_context(atlas, 0) as (port, server):
            base = f"http://127.0.0.1:{port}"

            code = _post(f"{base}/")
            assert code == 405

            code = _post(f"{base}/api/doctor")
            assert code == 405


def test_write_nothing_while_serving(monkeypatch):
    with EphemeralAtlasContext(git_sources=["log-daemon", "notes"]) as world:
        atlas = _make_atlas(world, monkeypatch, "log-daemon", "notes")

        snapshot_before = {
            str(p): p.read_bytes() for p in atlas.rglob("*") if p.is_file() and not p.is_symlink()
        }

        with _server_context(atlas, 0) as (port, server):
            base = f"http://127.0.0.1:{port}"

            for _ in range(5):
                _get(f"{base}/")
                _get(f"{base}/api/doctor")
                _get(f"{base}/api/status")
                _get(f"{base}/static/atlas.css")

        snapshot_after = {
            str(p): p.read_bytes() for p in atlas.rglob("*") if p.is_file() and not p.is_symlink()
        }

        assert snapshot_after == snapshot_before


def test_refuse_to_open_outside_an_atlas(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    code = main(["ui", "--no-browser"])

    assert code == 1
    assert list(tmp_path.iterdir()) == []


def test_answer_an_api_request_that_carries_a_query_string(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["notes"]) as world:
        atlas = _make_atlas(world, monkeypatch, "notes")
        with _server_context(atlas, 0) as (port, _server):
            code, body, _headers = _get(f"http://127.0.0.1:{port}/api/doctor?t=1")

        assert code == 200
        assert json.loads(body)["ok"] is True


def test_serve_two_atlases_from_two_servers_at_once(monkeypatch):
    with EphemeralAtlasContext(git_sources=[], plain_sources=["notes", "docs"]) as world:
        first_atlas = _make_atlas(world, monkeypatch, "notes")
        second_atlas = world.root / "other"
        second_atlas.mkdir()
        monkeypatch.chdir(second_atlas)
        assert main(["init"]) == 0
        assert main(["link", "docs", str(world.source("docs"))]) == 0
        with _server_context(first_atlas, 0) as (first_port, _a), _server_context(second_atlas, 0) as (second_port, _b):
            _, first_body, _ = _get(f"http://127.0.0.1:{first_port}/api/doctor")
            _, second_body, _ = _get(f"http://127.0.0.1:{second_port}/api/doctor")

        assert [source["name"] for source in json.loads(first_body)["sources"]] == ["notes"]
        assert [source["name"] for source in json.loads(second_body)["sources"]] == ["docs"]


def test_serve_every_script_and_template_the_page_refers_to(monkeypatch):
    import re
    from importlib.resources import files

    static = files("atlas_cli").joinpath("ui", "static")
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        with _server_context(world.atlas, 0) as (port, _server):
            code, page, _ = _get(f"http://127.0.0.1:{port}/")
            refs = set(re.findall(r'(?:src|href)="(/static/[^"]+)"', page))
            for templates in re.findall(r"data-child-templates='(\[[^']+\])'", page):
                refs.update(json.loads(templates))
            for script in static.iterdir():
                if script.name.endswith(".js"):
                    refs.update(f"/static/{name}" for name in re.findall(r"from '\./([^']+)'", script.read_text(encoding="utf-8")))
            missing = [ref for ref in sorted(refs) if _get(f"http://127.0.0.1:{port}{ref}")[0] != 200]

    assert code == 200
    assert len(refs) > 20
    assert missing == []


def test_refuse_a_static_name_that_is_not_a_file_the_package_ships(monkeypatch):
    import http.client

    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        with _server_context(world.atlas, 0) as (port, _server):
            codes = []
            for path in ("/static/%2e%2e/cli.py", "/static/..%2fcli.py", "/static/..\\cli.py",
                         "/static/\\etc\\passwd", "/static/C:secret", "/static/a/b.js", "/static/"):
                connection = http.client.HTTPConnection("127.0.0.1", port)
                connection.request("GET", path)
                codes.append(connection.getresponse().status)
                connection.close()

    assert codes == [404] * 7


def test_refuse_every_method_but_get(monkeypatch):
    import http.client

    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        with _server_context(world.atlas, 0) as (port, _server):
            codes = {}
            for method in ("HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"):
                connection = http.client.HTTPConnection("127.0.0.1", port)
                connection.request(method, "/api/doctor")
                codes[method] = connection.getresponse().status
                connection.close()

    assert set(codes.values()) == {405}


def test_listen_only_on_the_loopback_address(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        with _server_context(world.atlas, 0) as (_port, server):
            address = server.server_address[0]

    assert address == "127.0.0.1"


def test_say_so_when_the_port_is_taken(monkeypatch, capsys):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        with _server_context(world.atlas, 0) as (port, _server):
            capsys.readouterr()
            code = main(["ui", "--no-browser", "--port", str(port)])
            out = capsys.readouterr().out

    assert code == 1
    assert f"Cannot listen on 127.0.0.1:{port}" in out


def test_serve_the_page_scripts_as_javascript_and_the_templates_as_html(monkeypatch):
    with EphemeralAtlasContext(git_sources=[]) as world:
        monkeypatch.chdir(world.atlas)
        assert main(["init"]) == 0
        with _server_context(world.atlas, 0) as (port, _server):
            script = _get(f"http://127.0.0.1:{port}/static/doctor-plugster.js")[2]["Content-Type"]
            template = _get(f"http://127.0.0.1:{port}/static/doctor-finding-card.html")[2]["Content-Type"]

    assert script == "application/javascript; charset=utf-8"
    assert template == "text/html; charset=utf-8"
