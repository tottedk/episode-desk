"""Repo constraints: loopback only, manual start, no secret markers."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ConstraintTests(unittest.TestCase):
    def test_server_source_binds_loopback(self) -> None:
        text = (ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn('BIND_HOST = "127.0.0.1"', text)
        self.assertNotIn("0.0.0.0", text)

    def test_start_script_is_manual_and_loopback(self) -> None:
        text = (ROOT / "start_ui.ps1").read_text(encoding="utf-8")
        lowered = text.lower()
        self.assertIn("127.0.0.1", text)
        self.assertNotIn("0.0.0.0", text)
        self.assertIn("DryRun", text)
        self.assertIn("--dry-run", text)
        self.assertNotIn("register-scheduledtask", lowered)
        self.assertNotIn("new-service", lowered)
        self.assertNotIn("schtasks", lowered)

    def test_poll_interval_is_ten_seconds(self) -> None:
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        page = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("const STATUS_POLL_MS = 10000;", script)
        self.assertIn("every 10 seconds", page)

    def test_example_config_is_the_sample_and_has_no_secrets(self) -> None:
        raw = (ROOT / "config.example.json").read_text(encoding="utf-8")
        lowered = raw.lower()
        for marker in ("api_key", "apikey", "secret", "token", "password", "bearer "):
            self.assertNotIn(marker, lowered)
        data = json.loads(raw)
        self.assertEqual(
            set(data),
            {
                "books_dir",
                "briefs_dir",
                "launcher_cmd",
                "voices",
                "banned_voices",
                "status_file",
            },
        )
        self.assertEqual(data["banned_voices"], ["Maya", "Declan", "Alice", "Mary"])
        self.assertIn("Carter", data["voices"])
        self.assertIn("Hugh", data["voices"])
        self.assertTrue(data["books_dir"].startswith("C:\\"))
        self.assertIn("{brief_path}", data["launcher_cmd"])

    def test_config_json_is_gitignored(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("config.json", ignore)


if __name__ == "__main__":
    unittest.main()
