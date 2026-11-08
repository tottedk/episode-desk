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
                "uploads_dir",
                "library_enabled",
                "briefs_dir",
                "launcher_cmd",
                "voices",
                "banned_voices",
                "not_ready_voices",
                "status_file",
            },
        )
        self.assertEqual(data["uploads_dir"], "uploads/books")
        self.assertIs(data["library_enabled"], True)
        self.assertEqual(data["banned_voices"], ["Maya", "Declan", "Alice", "Mary"])
        self.assertEqual(
            data["not_ready_voices"],
            ["Lachlan", "Isla", "Marcus", "Willa", "Zara", "Imogen", "Frank", "Samuel"],
        )
        self.assertIn("Lachlan", data["not_ready_voices"])
        self.assertEqual(
            data["voices"],
            [
                "Carter",
                "Clara",
                "Lachlan",
                "Isla",
                "Marcus",
                "Willa",
                "Zara",
                "Imogen",
                "Frank",
                "Samuel",
                "Hugh",
                "Maya",
                "Declan",
                "Alice",
                "Mary",
            ],
        )
        self.assertNotIn("Elliot", data["voices"])
        self.assertNotIn("Elena", data["voices"])
        self.assertTrue(data["books_dir"].startswith("C:\\"))
        self.assertIn("{brief_path}", data["launcher_cmd"])

    def test_config_json_is_gitignored(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in (
            "config.json",
            "uploads/",
            ".env",
            "models/",
            "weights/",
            "*.gguf",
            "*.safetensors",
            "voices/",
            "drama3_refs/",
            "episodes/",
            "briefs/",
            "*.wav",
            "*.mp3",
        ):
            self.assertIn(pattern, ignore)

    def test_license_covers_original_code_only(self) -> None:
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", text)
        self.assertIn("Thomas Jensen", text)
        self.assertIn("Fish Audio Community License", text)
        self.assertIn("original Episode Desk", text)

    def test_readme_attribution_and_no_personal_paths(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Built with Fish Audio", readme)
        self.assertIn("Fish Audio Community License", readme)
        self.assertIn("LLM limits", readme)
        self.assertIn("Lachlan", readme)
        self.assertNotIn("Clara and Lachlan are the ready guests", readme)
        self.assertNotIn("C:\\Users", readme)
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".py", ".md", ".json", ".js", ".html", ".css", ".ps1", ".txt"}:
                continue
            if ".git" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("C:\\Users", text, path.name)
            self.assertNotRegex(
                text,
                r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                path.name,
            )


if __name__ == "__main__":
    unittest.main()
