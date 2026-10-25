"""Validate an episode brief, write it, and start the local pipeline.

The brief schema lives in README.md. Keep that document in step with
``build_brief``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

# Carter hosts every episode. Hugh is never a guest: he is not paired with
# Carter, and Carter is always the host, so Hugh is never selectable.
HOST_VOICE = "Carter"
EXCLUDED_WITH_HOST = "Hugh"
DEFAULT_BANNED_VOICES = ("Maya", "Declan", "Alice", "Mary")

BOOK_EXTENSIONS = frozenset({".pdf", ".epub", ".txt", ".md"})
LENGTH_MINUTES = (20, 30, 40)
DEFAULT_LENGTH_MINUTES = 40
TONES = ("calm", "playful", "debate", "serious")
DEPTHS = ("intro", "standard", "deep")

TTS_ENGINE = "Fish Audio Drama 3"
TTS_FALLBACK = "VibeVoice-7B"
SCHEMA_VERSION = 1

MAX_THEME_LENGTH = 240
MAX_NOTES_LENGTH = 4000
MAX_BOOKS_LISTED = 2000
MAX_STATUS_BYTES = 16_384
MAX_LAUNCHER_LENGTH = 2000
BRIEF_PATH_TOKEN = "{brief_path}"

# DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP. The pipeline survives after
# the desk window closes. CREATE_NO_WINDOW is intentionally not combined
# with DETACHED_PROCESS.
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
WINDOWS_DETACHED_FLAGS = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

_ID_RE = re.compile(r"^brief_[a-z0-9-]+_\d{8}_\d{6}(?:_\d+)?$")
_WRITE_LOCK = threading.Lock()


class ConfigError(Exception):
    """config.json is missing or does not match the expected shape."""


class BookError(Exception):
    """A book path is missing, outside the shelf, or not a source file."""


class BriefIOError(Exception):
    """The brief could not be written."""


class LaunchError(Exception):
    """PowerShell could not be started."""


@dataclass(frozen=True)
class AppConfig:
    books_dir: Path
    briefs_dir: Path
    launcher_cmd: str
    voices: tuple[str, ...]
    banned_voices: tuple[str, ...]
    status_file: Path


@dataclass(frozen=True)
class EpisodeRequest:
    source_type: str
    files: tuple[Path, ...]
    theme: str | None
    length_minutes: int
    guest_voices: tuple[str, ...]
    tone: str
    depth: str
    quiz: bool
    notes: str


def load_config(path: Path) -> AppConfig:
    """Load config.json. Paths are resolved next to the file when relative."""
    if not path.is_file():
        raise ConfigError(
            f"Config not found: {path}. Copy config.example.json to config.json and edit the paths."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("Config must be a JSON object.")

    base = path.resolve().parent
    books_dir = _require_path(data, "books_dir", base)
    briefs_dir = _require_path(data, "briefs_dir", base)
    status_file = _require_path(data, "status_file", base)
    launcher = data.get("launcher_cmd")
    if not isinstance(launcher, str) or not launcher.strip():
        raise ConfigError("launcher_cmd must be a non-empty string.")
    if len(launcher) > MAX_LAUNCHER_LENGTH:
        raise ConfigError("launcher_cmd is too long.")
    voices = _require_name_list(data, "voices", allow_empty=False)
    if "banned_voices" not in data:
        banned = DEFAULT_BANNED_VOICES
    else:
        banned = _require_name_list(data, "banned_voices", allow_empty=True)
    return AppConfig(
        books_dir=books_dir,
        briefs_dir=briefs_dir,
        launcher_cmd=launcher,
        voices=voices,
        banned_voices=banned,
        status_file=status_file,
    )


def selectable_voices(voices: Sequence[str], banned_voices: Sequence[str]) -> list[str]:
    """Voices the desk may offer as guests.

    Carter is the host. Hugh is never offered. Names in ``banned_voices``
    are never offered. Order follows ``voices``.
    """
    blocked = {name.casefold() for name in banned_voices}
    blocked.add(HOST_VOICE.casefold())
    blocked.add(EXCLUDED_WITH_HOST.casefold())
    result: list[str] = []
    seen: set[str] = set()
    for voice in voices:
        key = voice.casefold()
        if key in blocked or key in seen:
            continue
        seen.add(key)
        result.append(voice)
    return result


def list_books(books_dir: Path) -> tuple[list[dict[str, str]], bool]:
    """Return source files under ``books_dir`` and whether the list was capped."""
    root = books_dir.resolve()
    if not root.is_dir():
        raise BookError(f"Books folder does not exist: {root}")
    found: list[dict[str, str]] = []
    truncated = False
    try:
        for path in root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.lower() not in BOOK_EXTENSIONS:
                continue
            resolved = path.resolve()
            if not is_within(resolved, root):
                continue
            rel = resolved.relative_to(root).as_posix()
            if any(ord(char) < 32 for char in rel):
                continue
            if len(found) >= MAX_BOOKS_LISTED:
                truncated = True
                break
            found.append({"rel": rel, "name": path.name})
    except BookError:
        raise
    except OSError as exc:
        raise BookError(f"Couldn't read the books folder: {exc}") from exc
    found.sort(key=lambda item: item["rel"].casefold())
    return found, truncated


def resolve_book(books_dir: Path, rel: str) -> Path:
    """Resolve one shelf-relative file and reject anything outside the shelf."""
    if not isinstance(rel, str):
        raise BookError("That file isn't on the shelf.")
    cleaned = rel.replace("\\", "/").strip()
    if not cleaned or cleaned.startswith("/") or re.match(r"^[A-Za-z]:", cleaned):
        raise BookError("That file isn't on the shelf.")
    parts = cleaned.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise BookError("That file isn't on the shelf.")
    root = books_dir.resolve()
    if not root.is_dir():
        raise BookError(f"Books folder does not exist: {root}")
    candidate = root.joinpath(*parts)
    if candidate.is_symlink():
        raise BookError("That file isn't on the shelf.")
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise BookError("That file isn't on the shelf.") from exc
    if not is_within(resolved, root) or not resolved.is_file():
        raise BookError("That file isn't on the shelf.")
    if resolved.suffix.lower() not in BOOK_EXTENSIONS:
        raise BookError("That file isn't on the shelf.")
    return resolved


def is_within(child: Path, parent: Path) -> bool:
    parent_resolved = parent.resolve()
    child_resolved = child.resolve()
    return child_resolved != parent_resolved and parent_resolved in child_resolved.parents


def validate_payload(
    payload: object, config: AppConfig
) -> tuple[EpisodeRequest | None, dict[str, str]]:
    """Return a request, or field errors. Nothing is written."""
    if not isinstance(payload, dict):
        return None, {"form": "Expected an object."}

    errors: dict[str, str] = {}
    source_type, files, theme, source_error = _validate_source(payload, config)
    if source_error:
        errors["source"] = source_error

    length, length_error = _clean_length(payload)
    if length_error:
        errors["length_minutes"] = length_error

    guests, guest_error = _validate_guests(payload.get("guest_voices", None), config, "guest_voices" in payload)
    if guest_error:
        errors["guest_voices"] = guest_error

    tone, tone_error = _clean_choice(payload.get("tone"), TONES, "Choose a tone.")
    if tone_error:
        errors["tone"] = tone_error

    depth, depth_error = _clean_choice(payload.get("depth"), DEPTHS, "Choose a depth.")
    if depth_error:
        errors["depth"] = depth_error

    quiz, quiz_error = _clean_quiz(payload)
    if quiz_error:
        errors["quiz"] = quiz_error

    notes, notes_error = _clean_notes(payload.get("notes", ""))
    if notes_error:
        errors["notes"] = notes_error

    if (
        errors
        or source_type is None
        or length is None
        or guests is None
        or tone is None
        or depth is None
        or quiz is None
        or notes is None
    ):
        return None, errors or {"form": "The brief could not be validated."}

    return (
        EpisodeRequest(
            source_type=source_type,
            files=files,
            theme=theme,
            length_minutes=length,
            guest_voices=guests,
            tone=tone,
            depth=depth,
            quiz=quiz,
            notes=notes,
        ),
        {},
    )


def slugify(text: str) -> str:
    """ASCII slug, at most 48 characters. Empty input becomes ``episode``."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    slug = slug[:48].strip("-")
    return slug or "episode"


def build_brief(episode: EpisodeRequest, *, brief_id: str, now: datetime) -> dict:
    """Build the brief document. Host and TTS are fixed here, not taken from the form."""
    if now.tzinfo is None:
        raise BriefIOError("Brief timestamps need a timezone.")
    if episode.source_type == "files":
        source: dict[str, object] = {
            "type": "files",
            "files": [str(path) for path in episode.files],
            "theme": None,
        }
    else:
        source = {
            "type": "theme",
            "files": [],
            "theme": episode.theme,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "id": brief_id,
        "created_at": now.isoformat(timespec="seconds"),
        "source": source,
        "length_minutes": episode.length_minutes,
        "host": HOST_VOICE,
        "guest_voices": list(episode.guest_voices),
        "tone": episode.tone,
        "depth": episode.depth,
        "quiz": episode.quiz,
        "tts": {
            "engine": TTS_ENGINE,
            "fallback": TTS_FALLBACK,
        },
        "notes": episode.notes,
    }


def write_episode(
    config: AppConfig, episode: EpisodeRequest, now: datetime | None = None
) -> tuple[dict, Path]:
    """Write ``brief_<slug>_<timestamp>.json`` under the briefs folder."""
    moment = now if now is not None else datetime.now().astimezone()
    if moment.tzinfo is None:
        raise BriefIOError("Brief timestamps need a timezone.")
    if episode.source_type == "files":
        slug_source = episode.files[0].stem
    else:
        slug_source = episode.theme or ""
    slug = slugify(slug_source)
    directory = config.briefs_dir
    if not directory.is_dir():
        raise BriefIOError(f"Briefs folder does not exist: {directory}")
    with _WRITE_LOCK:
        brief_id = _allocate_id(directory, slug, moment)
        brief = build_brief(episode, brief_id=brief_id, now=moment)
        path = _write_json(directory, brief)
    return brief, path


def powershell_single_quote(value: str) -> str:
    """Wrap ``value`` as a PowerShell single-quoted literal."""
    return "'" + value.replace("'", "''") + "'"


def render_launcher_command(template: str, brief_path: str) -> str:
    """Fill ``{brief_path}`` with a quoted path. Append the path if the token is absent."""
    if not isinstance(template, str) or not template.strip():
        raise LaunchError("Launcher command is empty.")
    quoted = powershell_single_quote(brief_path)
    if BRIEF_PATH_TOKEN in template:
        return template.replace(BRIEF_PATH_TOKEN, quoted)
    return template.rstrip() + " " + quoted


def launch_detached(
    template: str,
    brief_path: str,
    *,
    dry_run: bool,
    platform_name: str | None = None,
) -> dict:
    """Start ``launcher_cmd`` in a detached PowerShell process.

    ``dry_run`` writes nothing here and does not start a process. The brief
    file is written by the caller either way. On Windows the process is
    created with DETACHED_PROCESS and a new process group, so closing the
    desk window does not kill the pipeline.
    """
    command = render_launcher_command(template, brief_path)
    if dry_run:
        return {"launched": False, "pid": None, "dry_run": True}
    system = os.name if platform_name is None else platform_name
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
        "cwd": _launch_cwd(brief_path),
        "shell": False,
    }
    if system == "nt":
        kwargs["creationflags"] = WINDOWS_DETACHED_FLAGS
    else:
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            **kwargs,
        )
    except OSError as exc:
        raise LaunchError(f"Could not start PowerShell: {exc}") from exc
    return {"launched": True, "pid": proc.pid, "dry_run": False}


def _launch_cwd(brief_path: str) -> str:
    """Working directory for the pipeline: the folder that holds the brief."""
    path = Path(brief_path)
    if path.is_absolute() or path.parent != Path("."):
        return str(path.resolve().parent)
    return str(Path.cwd())


def read_status(path: Path) -> dict:
    """Read the pipeline status file as plain text, capped at 16 KB."""
    try:
        if not path.exists():
            return {"ok": True, "exists": False, "text": "", "truncated": False}
        if not path.is_file():
            return {"ok": False, "error": "Status path is not a file."}
        data = path.read_bytes()
    except OSError as exc:
        return {"ok": False, "error": f"Couldn't read the status file: {exc}"}
    truncated = len(data) > MAX_STATUS_BYTES
    text = data[:MAX_STATUS_BYTES].decode("utf-8", errors="replace")
    return {"ok": True, "exists": True, "text": text, "truncated": truncated}


def _require_path(data: dict, key: str, base: Path) -> Path:
    raw = data.get(key)
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise ConfigError(f"{key} must be a path.")
    path = Path(raw.strip())
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _require_name_list(data: dict, key: str, *, allow_empty: bool) -> tuple[str, ...]:
    raw = data.get(key)
    if not isinstance(raw, list):
        raise ConfigError(f"{key} must be a list of names.")
    if not raw and not allow_empty:
        raise ConfigError(f"{key} must list at least one name.")
    names: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if (
            not isinstance(item, str)
            or not item.strip()
            or item != item.strip()
            or "\x00" in item
            or len(item) > 80
        ):
            raise ConfigError(f"{key} contains an invalid name.")
        fold = item.casefold()
        if fold in seen:
            raise ConfigError(f"{key} lists {item} more than once.")
        seen.add(fold)
        names.append(item)
    return tuple(names)


def _validate_source(
    payload: dict, config: AppConfig
) -> tuple[str | None, tuple[Path, ...], str | None, str | None]:
    source_type = payload.get("source_type")
    if source_type not in ("files", "theme"):
        return None, (), None, "Choose books or a theme."

    files_raw = payload.get("files", [])
    theme_raw = payload.get("theme", "")
    if files_raw is None:
        files_raw = []
    if theme_raw is None:
        theme_raw = ""
    if not isinstance(files_raw, list) or not all(isinstance(item, str) for item in files_raw):
        return None, (), None, "Books must be a list of file names."
    if not isinstance(theme_raw, str):
        return None, (), None, "Theme must be text."

    if source_type == "files":
        if theme_raw.strip():
            return None, (), None, "Choose books or a theme, not both."
        if not 1 <= len(files_raw) <= 2:
            return None, (), None, "Pick one or two books."
        resolved: list[Path] = []
        seen: set[str] = set()
        for rel in files_raw:
            try:
                path = resolve_book(config.books_dir, rel)
            except BookError as exc:
                return None, (), None, str(exc)
            key = str(path).casefold()
            if key in seen:
                return None, (), None, "That book is selected twice."
            seen.add(key)
            resolved.append(path)
        return "files", tuple(resolved), None, None

    if files_raw:
        return None, (), None, "Choose books or a theme, not both."
    theme, theme_error = _clean_theme(theme_raw)
    if theme_error:
        return None, (), None, theme_error
    return "theme", (), theme, None


def _validate_guests(
    raw: object, config: AppConfig, present: bool
) -> tuple[tuple[str, ...] | None, str | None]:
    if not present:
        return None, "Pick one or two guest voices."
    if not isinstance(raw, list) or not 1 <= len(raw) <= 2:
        return None, "Pick one or two guest voices."
    allowed = {
        voice.casefold(): voice
        for voice in selectable_voices(config.voices, config.banned_voices)
    }
    banned = {name.casefold() for name in config.banned_voices}
    chosen: list[str] = []
    seen: set[str] = set()
    for voice in raw:
        if not isinstance(voice, str):
            return None, "Guest voices must be names."
        fold = voice.strip().casefold()
        if not fold:
            return None, "That voice isn't available."
        if fold in seen:
            return None, "That guest is listed twice."
        seen.add(fold)
        if fold == HOST_VOICE.casefold():
            return None, "Carter hosts. Carter isn't a guest."
        if fold == EXCLUDED_WITH_HOST.casefold():
            return None, "Hugh isn't paired with Carter, so Hugh can't be a guest."
        if fold in banned or fold not in allowed:
            return None, "That voice isn't available."
        chosen.append(allowed[fold])
    return tuple(chosen), None


def _clean_theme(theme: str) -> tuple[str | None, str | None]:
    if "\x00" in theme:
        return None, "Theme contains an invalid character."
    cleaned = re.sub(r"\s+", " ", theme).strip()
    if not cleaned:
        return None, "Enter a theme."
    if len(cleaned) > MAX_THEME_LENGTH:
        return None, "Keep the theme under 240 characters."
    return cleaned, None


def _clean_notes(notes: object) -> tuple[str | None, str | None]:
    if notes is None:
        notes = ""
    if not isinstance(notes, str):
        return None, "Notes must be text."
    if "\x00" in notes:
        return None, "Notes contain an invalid character."
    cleaned = notes.strip()
    if len(cleaned) > MAX_NOTES_LENGTH:
        return None, "Keep notes under 4000 characters."
    return cleaned, None


def _clean_length(payload: dict) -> tuple[int | None, str | None]:
    if "length_minutes" not in payload or payload["length_minutes"] is None:
        return DEFAULT_LENGTH_MINUTES, None
    length = payload["length_minutes"]
    if isinstance(length, bool) or not isinstance(length, int) or length not in LENGTH_MINUTES:
        return None, "Length must be 20, 30, or 40 minutes."
    return length, None


def _clean_quiz(payload: dict) -> tuple[bool | None, str | None]:
    if "quiz" not in payload or payload["quiz"] is None:
        return False, None
    quiz = payload["quiz"]
    if not isinstance(quiz, bool):
        return None, "Quiz must be yes or no."
    return quiz, None


def _clean_choice(
    value: object, allowed: tuple[str, ...], message: str
) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or value not in allowed:
        return None, message
    return value, None


def _allocate_id(directory: Path, slug: str, now: datetime) -> str:
    stamp = now.strftime("%Y%m%d_%H%M%S")
    base = f"brief_{slug}_{stamp}"
    candidate = base
    suffix = 1
    while (directory / f"{candidate}.json").exists():
        candidate = f"{base}_{suffix}"
        suffix += 1
        if suffix > 1000:
            raise BriefIOError("Could not allocate a brief name.")
    if not _ID_RE.match(candidate):
        raise BriefIOError("Could not build a brief name.")
    return candidate


def _write_json(directory: Path, brief: dict) -> Path:
    directory = directory.resolve()
    name = brief["id"] + ".json"
    if Path(name).name != name or not _ID_RE.match(brief["id"]):
        raise BriefIOError("Refusing to write a brief outside the briefs folder.")
    dest = directory / name
    if dest.parent.resolve() != directory:
        raise BriefIOError("Refusing to write a brief outside the briefs folder.")
    fd, tmp_name = tempfile.mkstemp(prefix=".brief-", suffix=".tmp", dir=directory)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(brief, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, dest)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    return dest
