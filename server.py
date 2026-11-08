"""Loopback episode desk.

The server listens on 127.0.0.1 only. Start it by hand with start_ui.ps1.
Closing that window stops the process. The page also has a Stop server button.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import traceback
from urllib.parse import unquote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from podcast_brief import (
    HOST_VOICE,
    TTS_ENGINE,
    TTS_FALLBACK,
    AppConfig,
    BriefIOError,
    ConfigError,
    DEPTHS,
    DEFAULT_HUMANITY,
    HUMANITY_LEVELS,
    DEFAULT_LENGTH_MINUTES,
    LaunchError,
    LENGTH_MINUTES,
    TONES,
    MAX_UPLOAD_BYTES,
    UPLOAD_BODY_OVERHEAD,
    BookError,
    launch_detached,
    list_books,
    load_config,
    read_status,
    NOT_READY_NOTE,
    save_upload,
    selectable_voices,
    validate_payload,
    voice_choices,
    write_episode,
)

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
BIND_HOST = "127.0.0.1"
DEFAULT_PORT = 47221
MAX_BODY_BYTES = 32_768

CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "connect-src 'self'; "
    "img-src 'self'; "
    "base-uri 'none'; "
    "form-action 'self'"
)

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


class App:
    def __init__(self, config: AppConfig, dry_run: bool) -> None:
        self.config = config
        self.dry_run = dry_run


def create_server(app: App, port: int) -> ThreadingHTTPServer:
    """Bind an HTTP server to 127.0.0.1 and refuse any other address."""
    if BIND_HOST != "127.0.0.1":
        raise RuntimeError("The desk only binds to 127.0.0.1.")
    handler = make_handler(app)
    server = ThreadingHTTPServer((BIND_HOST, port), handler)
    bound_host = server.server_address[0]
    if bound_host != "127.0.0.1":
        server.server_close()
        raise RuntimeError(f"Refusing to listen on {bound_host}.")
    server.daemon_threads = True
    return server


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "EpisodeDesk/1.0"

        def do_GET(self) -> None:
            try:
                self._route_get()
            except Exception:
                traceback.print_exc()
                if not getattr(self, "_responded", False):
                    self._send_json(500, {"ok": False, "error": "The desk hit an unexpected error."})

        def do_POST(self) -> None:
            try:
                self._route_post()
            except Exception:
                traceback.print_exc()
                if not getattr(self, "_responded", False):
                    self._send_json(500, {"ok": False, "error": "The desk hit an unexpected error."})

        def log_message(self, fmt: str, *args) -> None:
            path = urlparse(self.path).path
            if path in {"/api/status", "/favicon.ico"}:
                return
            super().log_message(fmt, *args)

        def _route_get(self) -> None:
            path = urlparse(self.path).path
            if path == "/favicon.ico":
                self._send_empty(204)
                return
            if path in STATIC_FILES:
                filename, content_type = STATIC_FILES[path]
                self._serve_static(filename, content_type)
                return
            if path == "/api/options":
                self._send_json(200, _options_payload(app))
                return
            if path == "/api/status":
                payload = read_status(app.config.status_file)
                payload["path"] = str(app.config.status_file)
                self._send_json(200, payload)
                return
            if path == "/api/health":
                host, port = self.server.server_address[:2]
                self._send_json(
                    200,
                    {"ok": True, "bind": host, "port": port, "dry_run": app.dry_run},
                )
                return
            if path in {"/api/brief", "/api/stop", "/api/upload"}:
                self._send_json(405, {"ok": False, "error": "Method not allowed."}, allow="POST")
                return
            self._send_json(404, {"ok": False, "error": "Not found."})

        def _route_post(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/brief":
                self._handle_brief()
                return
            if path == "/api/upload":
                self._handle_upload()
                return
            if path == "/api/stop":
                self._handle_stop()
                return
            if path in {"/api/options", "/api/status", "/api/health"} or path in STATIC_FILES:
                self._send_json(405, {"ok": False, "error": "Method not allowed."}, allow="GET")
                return
            self._send_json(404, {"ok": False, "error": "Not found."})

        def _handle_brief(self) -> None:
            content_type = self.headers.get("Content-Type", "")
            if "application/json" not in content_type.lower():
                self._send_json(415, {"ok": False, "error": "Content-Type must be application/json."})
                return
            try:
                received = self._read_json()
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return
            episode, errors = validate_payload(received, app.config)
            if episode is None:
                self._send_json(
                    400,
                    {"ok": False, "errors": errors or {"form": "The brief could not be validated."}},
                )
                return
            try:
                brief, path = write_episode(app.config, episode)
            except BriefIOError as exc:
                self._send_json(500, {"ok": False, "error": str(exc)})
                return
            try:
                launch = launch_detached(
                    app.config.launcher_cmd, str(path), dry_run=app.dry_run
                )
            except LaunchError as exc:
                print(f"Launcher failed: {exc}", flush=True)
                self._send_json(
                    500,
                    {
                        "ok": False,
                        "brief_written": True,
                        "brief_path": str(path),
                        "brief_id": brief["id"],
                        "launched": False,
                        "dry_run": app.dry_run,
                        "error": str(exc),
                    },
                )
                return
            print(f"Wrote {path}", flush=True)
            if launch["launched"]:
                print(f"Launched pid {launch['pid']}", flush=True)
            else:
                print("Dry run: launcher not started", flush=True)
            self._send_json(
                201,
                {
                    "ok": True,
                    "brief_written": True,
                    "brief_path": str(path),
                    "brief_id": brief["id"],
                    "launched": launch["launched"],
                    "pid": launch["pid"],
                    "dry_run": launch["dry_run"],
                },
            )

        def _handle_upload(self) -> None:
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type.lower():
                self._send_json(
                    415,
                    {"ok": False, "error": "Upload the file as multipart form data."},
                )
                return
            try:
                length = _content_length(self)
            except ValueError as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return
            if length > MAX_UPLOAD_BYTES + UPLOAD_BODY_OVERHEAD:
                self.close_connection = True
                self._send_json(400, {"ok": False, "error": "That file is over 200 MB."})
                return
            if length <= 0:
                self._send_json(400, {"ok": False, "error": "Expected a file."})
                return
            raw = self.rfile.read(length)
            try:
                filename, data = extract_upload(content_type, raw)
                saved = save_upload(app.config, filename, data)
            except (ValueError, BookError) as exc:
                self._send_json(400, {"ok": False, "error": str(exc)})
                return
            except OSError:
                self._send_json(500, {"ok": False, "error": "Couldn't save that file."})
                return
            self._send_json(201, {"ok": True, "rel": saved["rel"], "name": saved["name"]})

        def _handle_stop(self) -> None:
            self._send_json(200, {"ok": True, "stopping": True})
            print("Stop requested.", flush=True)
            _defer_shutdown(self.server)

        def _read_json(self) -> dict:
            length = _content_length(self)
            if length > MAX_BODY_BYTES:
                self.close_connection = True
                raise ValueError("Request body is too large.")
            raw = self.rfile.read(length) if length else b""
            if not raw:
                raise ValueError("Expected a JSON body.")
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Body is not valid JSON.") from exc
            if not isinstance(data, dict):
                raise ValueError("Body must be a JSON object.")
            return data

        def _serve_static(self, filename: str, content_type: str) -> None:
            path = (STATIC_DIR / filename).resolve()
            if path.parent != STATIC_DIR.resolve() or not path.is_file():
                self._send_json(404, {"ok": False, "error": "Not found."})
                return
            data = path.read_bytes()
            self._send_bytes(200, data, content_type)

        def _send_json(self, status: int, payload: dict, allow: str | None = None) -> None:
            body = json.dumps(payload).encode("utf-8")
            self._send_bytes(status, body, "application/json; charset=utf-8", allow=allow)

        def _send_bytes(
            self, status: int, body: bytes, content_type: str, allow: str | None = None
        ) -> None:
            self.send_response(status)
            self._security_headers()
            if allow:
                self.send_header("Allow", allow)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self._responded = True

        def _send_empty(self, status: int) -> None:
            self.send_response(status)
            self._security_headers()
            self.send_header("Content-Length", "0")
            self.send_header("Connection", "close")
            self.end_headers()
            self._responded = True

        def _security_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Cache-Control", "no-store")

    return Handler


def extract_upload(content_type: str, body: bytes) -> tuple[str, bytes]:
    """Return the filename and bytes of the first file part."""
    match = re.search(
        r'boundary\s*=\s*(?:"([^"]+)"|([^;]+))',
        content_type,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError("Upload must be multipart form data.")
    boundary = (match.group(1) or match.group(2) or "").strip()
    if not boundary:
        raise ValueError("Upload must be multipart form data.")
    try:
        marker = b"--" + boundary.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("Upload must be multipart form data.") from exc
    for chunk in body.split(marker)[1:]:
        if chunk.startswith(b"--"):
            break
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        elif chunk.startswith(b"\n"):
            chunk = chunk[1:]
        separator = b"\r\n\r\n" if b"\r\n\r\n" in chunk else b"\n\n"
        head, found, data = chunk.partition(separator)
        if not found:
            continue
        if data.endswith(b"\r\n"):
            data = data[:-2]
        elif data.endswith(b"\n"):
            data = data[:-1]
        disposition = ""
        for line in head.decode("utf-8", "replace").splitlines():
            if line.lower().startswith("content-disposition:"):
                disposition = line.split(":", 1)[1].strip()
                break
        filename = _filename_from_disposition(disposition)
        if filename:
            return filename, data
    raise ValueError("Choose a file to upload.")


def _filename_from_disposition(disposition: str) -> str | None:
    if not disposition:
        return None
    star = re.search(r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", disposition)
    if star:
        name = unquote(star.group(1).strip().strip('"'))
        if name:
            return name
    quoted = re.search(r'filename\s*=\s*"((?:\\.|[^"\\])*)"', disposition)
    if quoted:
        return quoted.group(1).replace('\\"', '"').replace("\\\\", "\\")
    plain = re.search(r"filename\s*=\s*([^;]+)", disposition)
    if plain:
        name = plain.group(1).strip().strip('"')
        if name:
            return name
    return None


def _content_length(handler: BaseHTTPRequestHandler) -> int:
    raw = handler.headers.get("Content-Length", "0")
    try:
        length = int(raw)
    except ValueError as exc:
        raise ValueError("Invalid Content-Length.") from exc
    if length < 0:
        raise ValueError("Invalid Content-Length.")
    return length


def _defer_shutdown(server: ThreadingHTTPServer) -> None:
    def _run() -> None:
        time.sleep(0.05)
        server.shutdown()

    threading.Thread(target=_run, daemon=True).start()


def _options_payload(app: App) -> dict:
    config = app.config
    books: list[dict[str, str]] = []
    books_error = None
    truncated = False
    if config.library_enabled:
        try:
            books, truncated = list_books(config.books_dir)
        except BookError as exc:
            books = []
            books_error = str(exc)
    return {
        "ok": True,
        "books": books,
        "books_error": books_error,
        "books_truncated": truncated,
        "library_enabled": config.library_enabled,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "voices": selectable_voices(
            config.voices, config.banned_voices, config.not_ready_voices
        ),
        "voice_choices": voice_choices(
            config.voices, config.banned_voices, config.not_ready_voices
        ),
        "not_ready_note": NOT_READY_NOTE,
        "host": HOST_VOICE,
        "lengths": list(LENGTH_MINUTES),
        "default_length": DEFAULT_LENGTH_MINUTES,
        "tones": list(TONES),
        "depths": list(DEPTHS),
        "humanity_levels": list(HUMANITY_LEVELS),
        "default_humanity": DEFAULT_HUMANITY,
        "tts": {"engine": TTS_ENGINE, "fallback": TTS_FALLBACK},
        "dry_run": app.dry_run,
        "books_dir": str(config.books_dir),
        "briefs_dir": str(config.briefs_dir),
        "status_file": str(config.status_file),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local episode desk. Writes a podcast brief and starts the pipeline."
    )
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the brief and do not start the pipeline.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not 1 <= args.port <= 65535:
        print("Port must be between 1 and 65535.", file=sys.stderr)
        return 1
    try:
        config = load_config(Path(args.config))
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    app = App(config, dry_run=args.dry_run)
    try:
        server = create_server(app, args.port)
    except OSError as exc:
        print(f"Could not listen on {BIND_HOST}:{args.port}: {exc}", file=sys.stderr)
        return 1
    host, port = server.server_address[:2]
    print(f"Episode desk at http://{host}:{port}/", flush=True)
    if app.dry_run:
        print("Dry run: briefs are written and the pipeline is not started.", flush=True)
    print("Close this window, or use Stop server in the page, to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
