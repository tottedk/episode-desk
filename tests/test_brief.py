"""Validation, voice rules, and brief files."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import support  # noqa: E402

from podcast_brief import (  # noqa: E402
    DEFAULT_BANNED_VOICES,
    HOST_VOICE,
    LAUNCH_SETTLE_SECONDS,
    TTS_ENGINE,
    TTS_FALLBACK,
    WINDOWS_DETACHED_FLAGS,
    BriefIOError,
    ConfigError,
    LaunchError,
    launch_detached,
    list_books,
    load_config,
    powershell_single_quote,
    read_status,
    render_launcher_command,
    selectable_voices,
    slugify,
    validate_payload,
    write_episode,
)


NOW = datetime(2026, 10, 25, 14, 30, 12, tzinfo=timezone(timedelta(hours=-4)))


class SlugTests(unittest.TestCase):
    def test_slugify(self) -> None:
        self.assertEqual(slugify("On Lighthouses"), "on-lighthouses")
        self.assertEqual(slugify("Café & Fog"), "cafe-fog")
        self.assertEqual(slugify("Fish & Chips"), "fish-chips")
        self.assertEqual(slugify("---"), "episode")
        self.assertEqual(slugify(""), "episode")
        self.assertEqual(slugify("a" * 80), "a" * 48)
        self.assertEqual(slugify("hello_world"), "hello-world")


class VoiceTests(unittest.TestCase):
    def test_selectable_voices_drop_host_hugh_and_banned(self) -> None:
        voices = selectable_voices(
            ["Carter", "Hugh", "Elena", "Jonah", "Maya", "elena"],
            ["Maya", "Declan", "Alice", "Mary"],
        )
        self.assertEqual(voices, ["Elena", "Jonah"])

    def test_hugh_stays_out_even_if_the_ban_list_is_empty(self) -> None:
        voices = selectable_voices(["Maya", "Hugh", "Carter", "Elena"], ())
        self.assertEqual(voices, ["Maya", "Elena"])

    def test_example_config_voice_rules(self) -> None:
        config = load_config(ROOT / "config.example.json")
        voices = selectable_voices(config.voices, config.banned_voices)
        folds = {voice.casefold() for voice in voices}
        self.assertNotIn("carter", folds)
        self.assertNotIn("hugh", folds)
        for banned in ("maya", "declan", "alice", "mary"):
            self.assertNotIn(banned, folds)
        self.assertGreaterEqual(len(voices), 2)
        self.assertIn("{brief_path}", config.launcher_cmd)
        rendered = render_launcher_command(
            config.launcher_cmd,
            r"C:\PodcastPipeline\briefs\brief_demo_20261025_120000.json",
        )
        self.assertNotIn("{brief_path}", rendered)
        self.assertIn(
            r"'C:\PodcastPipeline\briefs\brief_demo_20261025_120000.json'",
            rendered,
        )
        self.assertIn(r"& 'C:\PodcastPipeline\launch_episode.ps1'", rendered)


class ConfigTests(unittest.TestCase):
    def test_relative_paths_and_default_bans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "books").mkdir()
            (root / "briefs").mkdir()
            path = root / "config.json"
            support.write_config(
                path,
                {
                    "books_dir": "books",
                    "briefs_dir": "briefs",
                    "launcher_cmd": "echo {brief_path}",
                    "voices": ["Elena", "Jonah"],
                    "status_file": "status.txt",
                },
            )
            config = load_config(path)
            self.assertEqual(config.books_dir, (root / "books").resolve())
            self.assertEqual(config.briefs_dir, (root / "briefs").resolve())
            self.assertEqual(config.status_file, (root / "status.txt").resolve())
            self.assertEqual(config.banned_voices, DEFAULT_BANNED_VOICES)

    def test_explicit_empty_ban_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "config.json"
            support.write_config(
                path,
                {
                    "books_dir": "books",
                    "briefs_dir": "briefs",
                    "launcher_cmd": "echo {brief_path}",
                    "voices": ["Maya", "Hugh", "Carter", "Elena"],
                    "banned_voices": [],
                    "status_file": "status.txt",
                },
            )
            config = load_config(path)
            self.assertEqual(config.banned_voices, ())
            self.assertEqual(
                selectable_voices(config.voices, config.banned_voices),
                ["Maya", "Elena"],
            )

    def test_rejects_bad_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.json"
            with self.assertRaises(ConfigError):
                load_config(missing)
            path = root / "config.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)
            support.write_config(
                path,
                {
                    "books_dir": "books",
                    "briefs_dir": "briefs",
                    "launcher_cmd": "   ",
                    "voices": ["Elena"],
                    "status_file": "status.txt",
                },
            )
            with self.assertRaises(ConfigError):
                load_config(path)
            support.write_config(
                path,
                {
                    "books_dir": "books",
                    "briefs_dir": "briefs",
                    "launcher_cmd": "echo {brief_path}",
                    "voices": ["Elena", "elena"],
                    "status_file": "status.txt",
                },
            )
            with self.assertRaises(ConfigError):
                load_config(path)
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)


class ShelfTests(unittest.TestCase):
    def test_list_books_filters_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            books = root / "books"
            support.write_shelf(books)
            found, truncated = list_books(books)
            self.assertFalse(truncated)
            self.assertEqual(
                [item["rel"] for item in found],
                [
                    "Coast Notes.txt",
                    "more/Fog.md",
                    "more/tape.epub",
                    "On Lighthouses.pdf",
                ],
            )

    def test_list_books_skips_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            books = root / "books"
            support.write_shelf(books)
            secret = root / "secret.txt"
            secret.write_text("nope", encoding="utf-8")
            link = books / "secret.txt"
            try:
                link.symlink_to(secret)
            except OSError as exc:
                self.skipTest(f"symlinks are not available: {exc}")
            rels = [item["rel"] for item in list_books(books)[0]]
            self.assertNotIn("secret.txt", rels)
            self.assertIn("On Lighthouses.pdf", rels)

    def test_list_caps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            books = root / "books"
            support.write_shelf(books)
            with mock.patch("podcast_brief.MAX_BOOKS_LISTED", 1):
                found, truncated = list_books(books)
            self.assertTrue(truncated)
            self.assertEqual(len(found), 1)

    def test_missing_shelf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = support.make_config(Path(tmp))
            missing = config.books_dir / "nope"
            episode, errors = validate_payload(
                support.valid_payload(files=["missing.txt"]), config
            )
            self.assertIsNone(episode)
            self.assertIn("source", errors)
            self.assertFalse(missing.exists())


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.config = support.make_config(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_accepts_files_and_ignores_client_tts_and_host(self) -> None:
        episode, errors = validate_payload(support.valid_payload(), self.config)
        self.assertEqual(errors, {})
        assert episode is not None
        self.assertEqual(episode.guest_voices, ("Elena", "Jonah"))
        self.assertEqual(episode.length_minutes, 40)
        self.assertTrue(episode.quiz)
        self.assertEqual(
            episode.files[0],
            (self.config.books_dir / "On Lighthouses.pdf").resolve(),
        )

    def test_theme_mode(self) -> None:
        episode, errors = validate_payload(
            support.valid_payload(
                source_type="theme",
                files=[],
                theme="  How   Fresnel lenses\nchanged the coast  ",
                guest_voices=["elena"],
                quiz=False,
                length_minutes=20,
                tone="debate",
                depth="intro",
                notes="  ",
            ),
            self.config,
        )
        self.assertEqual(errors, {})
        assert episode is not None
        self.assertEqual(episode.theme, "How Fresnel lenses changed the coast")
        self.assertEqual(episode.guest_voices, ("Elena",))
        self.assertEqual(episode.notes, "")
        self.assertFalse(episode.quiz)

    def test_defaults_when_length_and_quiz_omitted(self) -> None:
        payload = support.valid_payload()
        del payload["length_minutes"]
        del payload["quiz"]
        episode, errors = validate_payload(payload, self.config)
        self.assertEqual(errors, {})
        assert episode is not None
        self.assertEqual(episode.length_minutes, 40)
        self.assertFalse(episode.quiz)

    def test_rejects_bad_fields(self) -> None:
        cases = [
            ({"files": []}, "source"),
            ({"files": ["a.pdf", "b.txt", "c.md"]}, "source"),
            ({"files": ["../secret.txt"]}, "source"),
            ({"files": ["..\\secret.txt"]}, "source"),
            ({"files": ["/etc/passwd"]}, "source"),
            ({"files": ["C:/Windows/win.ini"]}, "source"),
            ({"files": ["skip.exe"]}, "source"),
            ({"files": ["On Lighthouses.pdf", "On Lighthouses.pdf"]}, "source"),
            ({"theme": "also a theme"}, "source"),
            ({"source_type": "theme", "files": ["On Lighthouses.pdf"], "theme": "Fog"}, "source"),
            ({"source_type": "theme", "files": [], "theme": "   "}, "source"),
            ({"guest_voices": []}, "guest_voices"),
            ({"guest_voices": ["Elena", "Jonah", "Priya"]}, "guest_voices"),
            ({"guest_voices": ["Carter"]}, "guest_voices"),
            ({"guest_voices": ["Hugh"]}, "guest_voices"),
            ({"guest_voices": ["hugh"]}, "guest_voices"),
            ({"guest_voices": ["Maya"]}, "guest_voices"),
            ({"guest_voices": ["Elena", "elena"]}, "guest_voices"),
            ({"guest_voices": ["Nobody"]}, "guest_voices"),
            ({"length_minutes": 15}, "length_minutes"),
            ({"length_minutes": "40"}, "length_minutes"),
            ({"length_minutes": True}, "length_minutes"),
            ({"tone": "Calm"}, "tone"),
            ({"tone": ""}, "tone"),
            ({"depth": "expert"}, "depth"),
            ({"quiz": "yes"}, "quiz"),
            ({"notes": "x" * 4001}, "notes"),
        ]
        for overrides, field in cases:
            with self.subTest(overrides=overrides):
                episode, errors = validate_payload(support.valid_payload(**overrides), self.config)
                self.assertIsNone(episode)
                self.assertIn(field, errors)

    def test_nested_book_and_backslash(self) -> None:
        episode, errors = validate_payload(
            support.valid_payload(files=["more\\Fog.md", "more/tape.epub"]),
            self.config,
        )
        self.assertEqual(errors, {})
        assert episode is not None
        self.assertEqual(episode.files[0].name, "Fog.md")
        self.assertEqual(episode.files[1].name, "tape.epub")

    def test_hugh_message_is_specific(self) -> None:
        _, errors = validate_payload(support.valid_payload(guest_voices=["Hugh"]), self.config)
        self.assertIn("Hugh", errors["guest_voices"])
        self.assertIn("Carter", errors["guest_voices"])

    def test_carter_message_is_specific(self) -> None:
        _, errors = validate_payload(support.valid_payload(guest_voices=["Carter"]), self.config)
        self.assertIn("Carter hosts", errors["guest_voices"])


class BriefWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.config = support.make_config(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_writes_schema_and_filename(self) -> None:
        episode, errors = validate_payload(support.valid_payload(), self.config)
        self.assertEqual(errors, {})
        assert episode is not None
        brief, path = write_episode(self.config, episode, now=NOW)
        self.assertTrue(path.is_file())
        self.assertEqual(path.parent, self.config.briefs_dir.resolve())
        self.assertRegex(path.name, r"^brief_[a-z0-9-]+_\d{8}_\d{6}(?:_\d+)?\.json$")
        self.assertEqual(path.name, brief["id"] + ".json")
        self.assertEqual(path.name, "brief_on-lighthouses_20261025_143012.json")
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, brief)
        self.assertEqual(
            list(brief.keys()),
            [
                "schema_version",
                "id",
                "created_at",
                "source",
                "length_minutes",
                "host",
                "guest_voices",
                "tone",
                "depth",
                "quiz",
                "tts",
                "notes",
            ],
        )
        self.assertEqual(brief["schema_version"], 1)
        self.assertEqual(brief["created_at"], "2026-10-25T14:30:12-04:00")
        self.assertEqual(datetime.fromisoformat(brief["created_at"]), NOW)
        self.assertEqual(brief["host"], HOST_VOICE)
        self.assertEqual(brief["tts"]["engine"], TTS_ENGINE)
        self.assertEqual(brief["tts"]["fallback"], TTS_FALLBACK)
        self.assertEqual(brief["tts"]["engine"], "Fish Audio Drama 3")
        self.assertEqual(brief["tts"]["fallback"], "VibeVoice-7B")
        self.assertEqual(brief["source"]["type"], "files")
        self.assertIsNone(brief["source"]["theme"])
        self.assertEqual(brief["guest_voices"], ["Elena", "Jonah"])
        self.assertEqual(brief["length_minutes"], 40)
        self.assertEqual(brief["tone"], "calm")
        self.assertEqual(brief["depth"], "deep")
        self.assertTrue(brief["quiz"])
        self.assertTrue(str(path).endswith(".json"))
        self.assertNotIn("not the real engine", path.read_text(encoding="utf-8"))

    def test_theme_brief_slug(self) -> None:
        episode, errors = validate_payload(
            support.valid_payload(
                source_type="theme",
                files=[],
                theme="How Fresnel lenses changed the coast",
            ),
            self.config,
        )
        assert episode is not None and not errors
        brief, path = write_episode(self.config, episode, now=NOW)
        self.assertEqual(path.name, "brief_how-fresnel-lenses-changed-the-coast_20261025_143012.json")
        self.assertEqual(brief["source"]["type"], "theme")
        self.assertEqual(brief["source"]["files"], [])
        self.assertEqual(brief["source"]["theme"], "How Fresnel lenses changed the coast")

    def test_collision_gets_a_suffix(self) -> None:
        episode, _ = validate_payload(support.valid_payload(), self.config)
        assert episode is not None
        first, path_one = write_episode(self.config, episode, now=NOW)
        second, path_two = write_episode(self.config, episode, now=NOW)
        self.assertNotEqual(path_one.name, path_two.name)
        self.assertTrue(path_two.name.endswith("_1.json"))
        self.assertNotEqual(first["id"], second["id"])

    def test_missing_briefs_dir(self) -> None:
        episode, _ = validate_payload(support.valid_payload(), self.config)
        assert episode is not None
        missing = self.config.briefs_dir
        missing.rmdir()
        with self.assertRaises(BriefIOError):
            write_episode(self.config, episode, now=NOW)


class LaunchTests(unittest.TestCase):
    def test_quotes_apostrophes(self) -> None:
        self.assertEqual(
            powershell_single_quote(r"C:\O'Brien\brief.json"),
            r"'C:\O''Brien\brief.json'",
        )

    def test_appends_path_when_token_missing(self) -> None:
        rendered = render_launcher_command("Write-Output ready", r"C:\briefs\a.json")
        self.assertEqual(rendered, r"Write-Output ready 'C:\briefs\a.json'")

    def test_dry_run_does_not_spawn(self) -> None:
        with mock.patch("podcast_brief.subprocess.Popen") as popen:
            result = launch_detached("echo {brief_path}", r"C:\b\brief.json", dry_run=True)
        popen.assert_not_called()
        self.assertFalse(result["launched"])
        self.assertTrue(result["dry_run"])
        self.assertIsNone(result["pid"])

    def test_windows_launch_is_detached(self) -> None:
        proc = support.running_launcher(7)
        brief = r"C:\briefs\brief.json"
        with mock.patch("podcast_brief.subprocess.Popen", return_value=proc) as popen:
            result = launch_detached(
                "& 'C:\\x.ps1' -BriefPath {brief_path}",
                brief,
                dry_run=False,
                platform_name="nt",
            )
        self.assertEqual(result["pid"], 7)
        self.assertTrue(result["launched"])
        kwargs = popen.call_args.kwargs
        self.assertEqual(kwargs["creationflags"], WINDOWS_DETACHED_FLAGS)
        self.assertEqual(kwargs["creationflags"], 0x08000000 | 0x00000200)
        self.assertEqual(kwargs["creationflags"], 0x08000200)
        self.assertEqual(WINDOWS_DETACHED_FLAGS & 0x00000008, 0)
        self.assertNotIn("start_new_session", kwargs)
        self.assertFalse(kwargs["shell"])
        proc.wait.assert_called_once_with(timeout=LAUNCH_SETTLE_SECONDS)
        self.assertEqual(LAUNCH_SETTLE_SECONDS, 2.0)
        argv = popen.call_args.args[0]
        self.assertEqual(argv[0], "powershell.exe")
        self.assertIn("-Command", argv)
        self.assertIn(r"'C:\briefs\brief.json'", argv[-1])
        self.assertNotIn("{brief_path}", argv[-1])

    def test_immediate_exit_is_a_failure_even_with_code_zero(self) -> None:
        proc = mock.Mock()
        proc.pid = 11
        proc.wait.return_value = 0
        with mock.patch("podcast_brief.subprocess.Popen", return_value=proc):
            with self.assertRaises(LaunchError) as caught:
                launch_detached(
                    "echo {brief_path}",
                    r"C:\briefs\brief.json",
                    dry_run=False,
                    platform_name="nt",
                )
        self.assertIn("code 0", str(caught.exception))
        proc.wait.assert_called_once_with(timeout=LAUNCH_SETTLE_SECONDS)

    def test_posix_launch_starts_a_new_session(self) -> None:
        proc = support.running_launcher(3)
        with mock.patch("podcast_brief.subprocess.Popen", return_value=proc) as popen:
            launch_detached(
                "echo {brief_path}",
                "/tmp/brief.json",
                dry_run=False,
                platform_name="posix",
            )
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertNotIn("creationflags", popen.call_args.kwargs)
        proc.wait.assert_called_once_with(timeout=LAUNCH_SETTLE_SECONDS)


class StatusTests(unittest.TestCase):
    def test_missing_empty_and_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "status.txt"
            self.assertFalse(read_status(missing)["exists"])
            missing.write_text("", encoding="utf-8")
            empty = read_status(missing)
            self.assertTrue(empty["exists"])
            self.assertEqual(empty["text"], "")
            missing.write_text("x" * 20, encoding="utf-8")
            with mock.patch("podcast_brief.MAX_STATUS_BYTES", 8):
                capped = read_status(missing)
            self.assertTrue(capped["truncated"])
            self.assertEqual(capped["text"], "x" * 8)
            (root / "folder").mkdir()
            self.assertFalse(read_status(root / "folder")["ok"])


if __name__ == "__main__":
    unittest.main()
