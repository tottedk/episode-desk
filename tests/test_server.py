"""HTTP server: loopback bind, brief route, and dry-run."""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import support  # noqa: E402

import server  # noqa: E402
from podcast_brief import (  # noqa: E402
    LAUNCH_SETTLE_SECONDS,
    MAX_STATUS_BYTES,
    WINDOWS_DETACHED_FLAGS,
)
from server import App, create_server  # noqa: E402


class ServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.config = support.make_config(Path(self.tmp.name))
        self.app = App(self.config, dry_run=True)
        self.httpd = create_server(self.app, 0)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address[:2]
        self.port = port
        self.base = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def request(self, method: str, path: str, body: dict | None = None, content_type: str | None = None):
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = content_type or "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                raw = response.read()
                payload = json.loads(raw.decode("utf-8")) if raw else None
                return response.status, payload, response.headers
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            payload = json.loads(raw.decode("utf-8")) if raw else None
            return exc.code, payload, exc.headers

    def test_binds_loopback_only(self) -> None:
        self.assertEqual(server.BIND_HOST, "127.0.0.1")
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")
        with socket.create_connection(("127.0.0.1", self.port), timeout=2) as sock:
            self.assertEqual(sock.getpeername()[0], "127.0.0.1")
        status, payload, _headers = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["bind"], "127.0.0.1")
        self.assertTrue(payload["dry_run"])
        self.assert_proc_net_tcp_loopback(self.port)

    def test_options_hide_launcher_and_blocked_voices(self) -> None:
        status, payload, _headers = self.request("GET", "/api/options")
        self.assertEqual(status, 200)
        self.assertEqual(payload["voices"], ["Elena", "Jonah", "Priya"])
        self.assertNotIn("Carter", payload["voices"])
        self.assertNotIn("Hugh", payload["voices"])
        self.assertNotIn("Maya", payload["voices"])
        self.assertEqual(payload["host"], "Carter")
        self.assertEqual(payload["tts"]["engine"], "Fish Audio Drama 3")
        self.assertEqual(payload["tts"]["fallback"], "VibeVoice-7B")
        self.assertEqual(payload["default_length"], 40)
        encoded = json.dumps(payload)
        self.assertNotIn("launcher_cmd", encoded)
        self.assertNotIn("launch_episode", encoded)
        rels = [item["rel"] for item in payload["books"]]
        self.assertIn("On Lighthouses.pdf", rels)
        self.assertNotIn("skip.exe", rels)

    def test_dry_run_writes_brief_without_spawning(self) -> None:
        with mock.patch("podcast_brief.subprocess.Popen") as popen:
            status, payload, _headers = self.request("POST", "/api/brief", support.valid_payload())
        self.assertEqual(status, 201)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["launched"])
        self.assertIsNone(payload["pid"])
        popen.assert_not_called()
        written = Path(payload["brief_path"])
        self.assertTrue(written.is_file())
        self.assertEqual(written.parent, self.config.briefs_dir.resolve())
        brief = json.loads(written.read_text(encoding="utf-8"))
        self.assertEqual(brief["host"], "Carter")
        self.assertEqual(brief["tts"]["engine"], "Fish Audio Drama 3")
        self.assertNotIn("not the real engine", written.read_text(encoding="utf-8"))

    def test_launch_uses_detached_powershell_when_not_dry_run(self) -> None:
        self.app.dry_run = False
        proc = support.running_launcher(99)
        with mock.patch("podcast_brief.subprocess.Popen", return_value=proc) as popen:
            status, payload, _headers = self.request("POST", "/api/brief", support.valid_payload())
        self.assertEqual(status, 201, payload)
        self.assertTrue(payload["launched"])
        self.assertEqual(payload["pid"], 99)
        self.assertFalse(payload["dry_run"])
        self.assertEqual(popen.call_args.args[0][0], "powershell.exe")
        kwargs = popen.call_args.kwargs
        self.assertFalse(kwargs["shell"])
        proc.wait.assert_called_once_with(timeout=LAUNCH_SETTLE_SECONDS)
        if os.name == "nt":
            self.assertEqual(kwargs["creationflags"], WINDOWS_DETACHED_FLAGS)
        else:
            self.assertTrue(kwargs["start_new_session"])
            self.assertNotIn("creationflags", kwargs)

    def test_clean_launcher_exit_is_success(self) -> None:
        self.app.dry_run = False
        proc = mock.Mock()
        proc.pid = 5
        proc.wait.return_value = 0
        with mock.patch("podcast_brief.subprocess.Popen", return_value=proc):
            status, payload, _headers = self.request("POST", "/api/brief", support.valid_payload())
        self.assertEqual(status, 201, payload)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["launched"])
        self.assertEqual(payload["pid"], 5)
        self.assertTrue(Path(payload["brief_path"]).is_file())

    def test_nonzero_launcher_exit_is_not_success(self) -> None:
        self.app.dry_run = False
        proc = mock.Mock()
        proc.pid = 6
        proc.wait.return_value = 7
        with mock.patch("podcast_brief.subprocess.Popen", return_value=proc):
            status, payload, _headers = self.request("POST", "/api/brief", support.valid_payload())
        self.assertEqual(status, 500, payload)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["brief_written"])
        self.assertFalse(payload["launched"])
        self.assertIn("code 7", payload["error"])
        self.assertTrue(Path(payload["brief_path"]).is_file())

    def test_rejects_hugh_and_does_not_write(self) -> None:
        status, payload, _headers = self.request(
            "POST", "/api/brief", support.valid_payload(guest_voices=["Hugh"])
        )
        self.assertEqual(status, 400)
        self.assertIn("Hugh", payload["errors"]["guest_voices"])
        self.assertEqual(list(self.config.briefs_dir.glob("brief_*.json")), [])

    def test_rejects_escape_and_banned_voice(self) -> None:
        status, payload, _headers = self.request(
            "POST",
            "/api/brief",
            support.valid_payload(files=["../secret.txt"], guest_voices=["Maya"]),
        )
        self.assertEqual(status, 400)
        self.assertIn("source", payload["errors"])
        self.assertIn("guest_voices", payload["errors"])
        self.assertEqual(list(self.config.briefs_dir.glob("brief_*.json")), [])

    def test_status_roundtrip(self) -> None:
        status, payload, _headers = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(payload["exists"])
        self.assertIn("rendering chapter 2", payload["text"])
        self.assertEqual(payload["path"], str(self.config.status_file))

    def test_status_truncates(self) -> None:
        self.config.status_file.write_text("y" * (MAX_STATUS_BYTES + 40), encoding="utf-8")
        status, payload, _headers = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(payload["truncated"])
        self.assertEqual(len(payload["text"]), MAX_STATUS_BYTES)

    def test_missing_status_file(self) -> None:
        self.config.status_file.unlink()
        status, payload, _headers = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertFalse(payload["exists"])
        self.assertEqual(payload["text"], "")

    def test_page_exposes_fixed_engine(self) -> None:
        with urllib.request.urlopen(self.base + "/", timeout=5) as response:
            html = response.read().decode("utf-8")
            content_type = response.headers["Content-Type"]
        self.assertIn("text/html", content_type)
        self.assertIn("Fish Audio Drama 3", html)
        self.assertIn("VibeVoice-7B", html)
        self.assertNotRegex(html, r'name="tts"')
        self.assertNotRegex(html, r'id="tts"')
        self.assertIn('value="40" checked', html)
        for tone in ("calm", "playful", "debate", "serious"):
            self.assertIn(f'value="{tone}"', html)
        for depth in ("intro", "standard", "deep"):
            self.assertIn(f'value="{depth}"', html)

    def test_security_headers_and_unknown_route(self) -> None:
        status, payload, headers = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        status, payload, _headers = self.request("GET", "/nope")
        self.assertEqual(status, 404)
        status, _payload, headers = self.request("POST", "/api/health", {})
        self.assertEqual(status, 405)
        self.assertEqual(headers["Allow"], "GET")

    def test_rejects_non_json_and_large_body(self) -> None:
        status, payload, _headers = self.request(
            "POST",
            "/api/brief",
            {"ok": True},
            content_type="text/plain",
        )
        self.assertEqual(status, 415)
        big = b'{"notes":"' + (b"x" * 40000) + b'"}'
        req = urllib.request.Request(
            self.base + "/api/brief",
            data=big,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(caught.exception.code, 400)
        detail = json.loads(caught.exception.read().decode("utf-8"))
        self.assertIn("too large", detail["error"])

    def test_favicon_is_empty(self) -> None:
        with urllib.request.urlopen(self.base + "/favicon.ico", timeout=5) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(response.read(), b"")

    def test_books_dir_missing_is_reported(self) -> None:
        paths = list(self.config.books_dir.rglob("*"))
        for child in paths:
            if child.is_file() or child.is_symlink():
                child.unlink()
        for child in sorted((path for path in paths if path.is_dir()), reverse=True):
            child.rmdir()
        self.config.books_dir.rmdir()
        status, payload, _headers = self.request("GET", "/api/options")
        self.assertEqual(status, 200)
        self.assertEqual(payload["books"], [])
        self.assertIn("does not exist", payload["books_error"])

    def assert_proc_net_tcp_loopback(self, port: int) -> None:
        proc = Path("/proc/net/tcp")
        if not proc.exists():
            return
        port_hex = f"{port:04X}"
        found = False
        for line in proc.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split()
            local_ip, local_port = parts[1].split(":")
            if local_port.upper() != port_hex or parts[3] != "0A":
                continue
            found = True
            self.assertEqual(local_ip.upper(), "0100007F")
            self.assertNotEqual(local_ip.upper(), "00000000")
        self.assertTrue(found, "listening socket was not found in /proc/net/tcp")
        tcp6 = Path("/proc/net/tcp6")
        if not tcp6.exists():
            return
        for line in tcp6.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split()
            _ip, local_port = parts[1].split(":")
            if local_port.upper() == port_hex and parts[3] == "0A":
                self.fail(f"port {port} is also listening on IPv6")


class StopTest(unittest.TestCase):
    def test_stop_shuts_the_server_down(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = support.make_config(Path(tmp.name))
        app = App(config, dry_run=True)
        httpd = create_server(app, 0)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(httpd.server_close)
        port = httpd.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/stop", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
        self.assertTrue(payload["stopping"])
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        httpd.server_close()
        with self.assertRaises(OSError):
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2)


if __name__ == "__main__":
    unittest.main()
