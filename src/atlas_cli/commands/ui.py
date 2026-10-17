import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from atlas_cli.atlascorpus import fingerprint, read_corpus
from atlas_cli.atlasfiles import ATLAS_TOML
from atlas_cli.commands import doctor, setup, status


def register(subparsers) -> None:
    parser = subparsers.add_parser("ui", help="open a local read-only page on this Atlas")
    parser.add_argument("--port", type=int, default=0, help="port to listen on (default: 0)")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.set_defaults(handler=run)


def run(args) -> int:
    folder = Path.cwd()
    if not (folder / ATLAS_TOML).is_file():
        print(f"This folder is not an Atlas (no {ATLAS_TOML}).")
        return 1
    try:
        server = make_server(folder, args.port)
    except OSError as error:
        print(f"Cannot listen on 127.0.0.1:{args.port} ({error.strerror or error}).")
        return 1
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    print(f"Atlas UI on {url} — Ctrl+C to stop")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


class AtlasUIServer(ThreadingHTTPServer):
    """The local server; it knows the Atlas it serves.

    A tunnel's forwarder opens many connections at once: the standard library keeps only 5
    waiting, and the rest are reset.
    """

    request_queue_size = 128

    def __init__(self, folder: Path, port: int):
        self.atlas_folder = folder
        super().__init__(("127.0.0.1", port), AtlasUIHandler)


def make_server(folder: Path, port: int) -> AtlasUIServer:
    return AtlasUIServer(folder, port)


def _static_names() -> set[str]:
    """Only a file the package ships is served: no path, no drive letter, no backslash gets through."""
    return {entry.name for entry in files("atlas_cli").joinpath("ui", "static").iterdir() if entry.is_file()}


def _package_resource(*parts: str) -> bytes:
    return files("atlas_cli").joinpath("ui", *parts).read_bytes()


def _content_type(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext == ".html":
        return "text/html; charset=utf-8"
    if ext == ".css":
        return "text/css; charset=utf-8"
    if ext == ".js":
        return "application/javascript; charset=utf-8"
    if ext == ".json":
        return "application/json; charset=utf-8"
    if ext == ".txt":
        return "text/plain; charset=utf-8"
    if ext == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"


class AtlasUIHandler(BaseHTTPRequestHandler):
    # Keep-alive: the page's ~30 files reuse a few connections instead of one each.
    protocol_version = "HTTP/1.1"
    timeout = 30

    def do_GET(self) -> None:
        self._responded = False
        try:
            self._route(urlsplit(self.path).path.rstrip("/") or "/")
        except ConnectionError:
            pass  # the browser went away
        except Exception as error:  # a file that can't be read must not drop the request
            if not self._responded:
                self._json_response({"ok": False, "error": f"{type(error).__name__}: {error}"}, code=500)

    def send_response(self, code: int, message: str | None = None) -> None:
        self._responded = True
        super().send_response(code, message)

    def _refuse_method(self) -> None:
        self.close_connection = True  # a refused request's body is never read, so the connection can't be reused
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    do_HEAD = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _refuse_method

    def _route(self, path: str) -> None:
        if path == "/":
            self._serve_index()
        elif path.startswith("/static/"):
            self._serve_static(path[len("/static/"):])
        elif path.startswith("/api/"):
            self._serve_api(path)
        else:
            self._not_found()

    def _serve_index(self) -> None:
        data = _package_resource("index.html")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, name: str) -> None:
        if name not in _static_names():
            self._not_found()
            return
        data = _package_resource("static", name)
        ct = _content_type(name)
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_api(self, path: str) -> None:
        if path == "/api/doctor":
            self._doctor_json()
        elif path == "/api/status":
            self._status_json()
        elif path == "/api/corpus":
            self._corpus_json()
        elif path == "/api/version":
            self._version_json()
        elif path == "/api/machinery":
            self._json_response(setup.machinery_state())
        else:
            self._not_found()

    def _doctor_json(self) -> None:
        try:
            report = doctor.diagnose(self.server.atlas_folder)
        except ValueError as error:
            self._json_response({"ok": False, "error": str(error)})
            return
        self._json_response(report)

    def _status_json(self) -> None:
        code, lines = status.status_lines(self.server.atlas_folder)
        self._json_response({"code": code, "text": "\n".join(lines)})

    def _corpus_json(self) -> None:
        self._json_response(read_corpus(self.server.atlas_folder))

    def _version_json(self) -> None:
        self._json_response({"version": fingerprint(self.server.atlas_folder, setup.config_folder())})

    def _json_response(self, data: object, code: int = 200) -> None:
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self) -> None:
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass
