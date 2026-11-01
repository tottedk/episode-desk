"""Shared fixtures for episode desk tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest import mock

from podcast_brief import DEFAULT_BANNED_VOICES, LAUNCH_SETTLE_SECONDS, AppConfig


def write_shelf(books: Path) -> None:
    books.mkdir(parents=True, exist_ok=True)
    (books / "On Lighthouses.pdf").write_bytes(b"%PDF-1.4\n")
    (books / "Coast Notes.txt").write_text("The coast.\n", encoding="utf-8")
    (books / "skip.exe").write_bytes(b"MZ")
    more = books / "more"
    more.mkdir()
    (more / "Fog.md").write_text("# Fog\n", encoding="utf-8")
    (more / "tape.epub").write_bytes(b"PK\x03\x04")


def make_config(root: Path, **overrides) -> AppConfig:
    books = root / "books"
    briefs = root / "briefs"
    uploads = root / "uploads" / "books"
    write_shelf(books)
    briefs.mkdir()
    uploads.mkdir(parents=True)
    status = root / "status.txt"
    status.write_text("rendering chapter 2\n", encoding="utf-8")
    values = {
        "books_dir": books,
        "briefs_dir": briefs,
        "launcher_cmd": "& 'C:\\PodcastPipeline\\launch_episode.ps1' -BriefPath {brief_path}",
        "voices": ("Carter", "Hugh", "Elena", "Jonah", "Priya", "Maya"),
        "banned_voices": DEFAULT_BANNED_VOICES,
        "not_ready_voices": (),
        "status_file": status,
        "uploads_dir": uploads,
        "library_enabled": True,
    }
    values.update(overrides)
    return AppConfig(**values)


def valid_payload(**overrides) -> dict:
    payload = {
        "topic": "On Lighthouses",
        "files": ["On Lighthouses.pdf"],
        "research": True,
        "content_style": "v2.5",
        "length_minutes": 40,
        "guest_voices": ["Elena", "Jonah"],
        "tone": "calm",
        "depth": "deep",
        "notes": "Open on the lamp.",
        "tts": {"engine": "not the real engine"},
        "host": "Hugh",
    }
    payload.update(overrides)
    return payload


def write_config(path: Path, body: dict) -> None:
    path.write_text(json.dumps(body), encoding="utf-8")


def running_launcher(pid: int) -> mock.Mock:
    """A Popen stand-in that is still alive after the settle wait."""
    proc = mock.Mock()
    proc.pid = pid
    proc.wait.side_effect = subprocess.TimeoutExpired("powershell.exe", LAUNCH_SETTLE_SECONDS)
    return proc
