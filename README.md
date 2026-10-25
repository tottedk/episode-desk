# Episode desk

Episode desk is a small local page for setting up a podcast episode before a pipeline on the same Windows PC generates it. You choose the source, the length, one or two guest voices, the tone, the depth, and whether the episode ends with a quiz. The desk writes a brief JSON file and starts the pipeline with that file. It does not generate audio itself.

Carter hosts every episode. The speech engine is fixed: **Fish Audio Drama 3**, with **VibeVoice-7B** noted only as a fallback. The desk cannot switch engines.

The page is one static HTML file plus vanilla JavaScript. The server is Python's standard library (`http.server`). There is no pip install and no build step.

It is meant for a Windows 11 PC with PowerShell 5.1 and Python 3.10 or newer. The pipeline itself lives outside this repo. This repo only writes the brief and launches the command you configure.

## Setup

1. Install Python 3.10+ and confirm `py -3` or `python` works in PowerShell.
2. Copy the sample config and edit it:

   ```powershell
   Copy-Item config.example.json config.json
   ```

   `config.example.json` is the committed sample. It uses dummy paths under `C:\PodcastPipeline`. `config.json` is gitignored. Do not put secrets in either file.

3. Create the books folder, the briefs folder, and point `status_file` at a plain-text file the pipeline will update. The status file can be missing until the pipeline creates it.
4. Put source files (`.pdf`, `.epub`, `.txt`, `.md`) in `books_dir`.
5. Point `launcher_cmd` at your pipeline. See [Config](#config).

## Run

Start it by hand. This does not install a service, a startup item, or a scheduled task.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_ui.ps1
```

Dry run (write the brief, do not start the pipeline):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_ui.ps1 -DryRun
```

Optional port (loopback only, default `47221`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_ui.ps1 -Port 47221
```

`start_ui.ps1` starts Python in that window and opens `http://127.0.0.1:47221/`. Close the window to stop the server, or use **Stop server** on the page. Stopping the desk does not stop a pipeline that has already been launched. The pipeline process is detached on purpose.

You can also run the server directly:

```powershell
py -3 server.py --dry-run
```

## Config

`config.json`:

| Field | Meaning |
| --- | --- |
| `books_dir` | Folder of source files. Relative paths are resolved next to `config.json`. |
| `briefs_dir` | Folder where `brief_<slug>_<timestamp>.json` is written. Must already exist. |
| `launcher_cmd` | PowerShell command template. `{brief_path}` is replaced with the brief path, single-quoted. |
| `voices` | Every voice the desk knows, including Carter and anyone you want hidden. |
| `banned_voices` | Optional. These names are never offered as guests. If the key is omitted, the default is Maya, Declan, Alice, Mary. |
| `status_file` | Plain-text file the page reads every 10 seconds. |

`launcher_cmd` is the command body, not a call to `powershell.exe`. The desk runs it as:

```text
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command <rendered>
```

Leave `{brief_path}` unquoted in the template. The desk adds PowerShell single quotes and doubles any single quote inside the path. If the token is missing, the quoted path is appended.

Sample (`config.example.json`):

```json
{
  "books_dir": "C:\\PodcastPipeline\\books",
  "briefs_dir": "C:\\PodcastPipeline\\briefs",
  "launcher_cmd": "& 'C:\\PodcastPipeline\\launch_episode.ps1' -BriefPath {brief_path}",
  "voices": ["Carter", "Hugh", "Elena", "Jonah", "Priya", "Sam", "Noah", "Ruth", "Maya", "Declan", "Alice", "Mary"],
  "banned_voices": ["Maya", "Declan", "Alice", "Mary"],
  "status_file": "C:\\PodcastPipeline\\status.txt"
}
```

That renders, for a real brief, as:

```text
& 'C:\PodcastPipeline\launch_episode.ps1' -BriefPath 'C:\PodcastPipeline\briefs\brief_on-lighthouses_20261025_143012.json'
```

Voice rules, applied in this order:

- Carter is always the host and is never a guest.
- Hugh is never selectable. He is not paired with Carter, and Carter always hosts.
- `banned_voices` are never offered. The default list is Maya, Declan, Alice, Mary.
- You pick 1 or 2 guests from whoever remains, in the order they appear in `voices`.

The working directory of the launched PowerShell process is the briefs folder. The brief path on the command line is absolute.

## Form

- **Source.** A dropdown of files in `books_dir` (pdf, epub, txt, md), up to 2, or a free-text theme. Not both.
- **Length.** 20, 30, or 40 minutes. Default 40.
- **Guest voices.** 1 or 2, under the rules above.
- **Tone.** calm, playful, debate, or serious.
- **Depth.** intro, standard, or deep.
- **Quiz.** yes or no. Default no.
- **Speech.** Fish Audio Drama 3, fallback VibeVoice-7B. Not editable.
- **Notes.** Optional, up to 4000 characters.

On submit the desk validates the form, writes the brief, and starts `launcher_cmd` unless `--dry-run` / `-DryRun` is on. The page shows the brief path and, when it launched the pipeline, the process id. The status panel polls `status_file` every 10 seconds.

## Brief schema

`schema_version` is `1`. The file name is `brief_<slug>_<YYYYMMDD>_<HHMMSS>.json`. If that name already exists, `_1`, `_2`, and so on are appended until the name is free. The `id` field is the file name without `.json`.

The slug comes from the theme, or from the first book's file name. It is lowercase ASCII, non-letters become hyphens, and it is at most 48 characters. The timestamp is the PC's local time.

```json
{
  "schema_version": 1,
  "id": "brief_on-lighthouses_20261025_143012",
  "created_at": "2026-10-25T14:30:12-04:00",
  "source": {
    "type": "files",
    "files": [
      "C:\\PodcastPipeline\\books\\On Lighthouses.pdf"
    ],
    "theme": null
  },
  "length_minutes": 40,
  "host": "Carter",
  "guest_voices": ["Elena", "Jonah"],
  "tone": "calm",
  "depth": "deep",
  "quiz": false,
  "tts": {
    "engine": "Fish Audio Drama 3",
    "fallback": "VibeVoice-7B"
  },
  "notes": ""
}
```

A theme brief uses `"type": "theme"`, `"files": []`, and a string `theme`.

| Field | Rule |
| --- | --- |
| `schema_version` | Always `1`. |
| `id` | `brief_<slug>_<YYYYMMDD>_<HHMMSS>` with an optional `_N` suffix. |
| `created_at` | ISO 8601 local time with a numeric offset, to the second. |
| `source.type` | `files` or `theme`. |
| `source.files` | Absolute paths. One or two when `type` is `files`, otherwise empty. Paths stay inside `books_dir`. |
| `source.theme` | The theme string, or `null` when `type` is `files`. |
| `length_minutes` | `20`, `30`, or `40`. |
| `host` | Always `Carter`. |
| `guest_voices` | One or two names from the selectable list. |
| `tone` | `calm`, `playful`, `debate`, or `serious`. |
| `depth` | `intro`, `standard`, or `deep`. |
| `quiz` | Boolean. |
| `tts.engine` | Always `Fish Audio Drama 3`. |
| `tts.fallback` | Always `VibeVoice-7B`. The pipeline may use it only as a fallback. |
| `notes` | String. May be empty. |

Anything the browser sends for `host` or `tts` is ignored. The server writes the fixed values.

## HTTP

The page and these routes are served on `127.0.0.1` only:

| Method | Path | Role |
| --- | --- | --- |
| GET | `/` | The desk page. |
| GET | `/api/options` | Shelf, selectable voices, and the fixed engine. The launcher command is not included. |
| GET | `/api/status` | Plain text from `status_file`, capped at 16 KB. |
| GET | `/api/health` | `{"ok": true, "bind": "127.0.0.1", ...}`. |
| POST | `/api/brief` | Validate, write, and launch (or skip launch in a dry run). |
| POST | `/api/stop` | Stop the desk process. |

## Tests

From the repo root, with Python 3.10+:

```powershell
py -3 -m unittest discover -s tests -v
```

The tests cover validation, voice rules, brief writing, the launcher command, dry-run, and the loopback bind. They do not need the real pipeline.

## Layout

```text
server.py              loopback HTTP server
podcast_brief.py       config, validation, brief files, launcher
start_ui.ps1           manual start; opens the browser
static/index.html      the page
static/app.css
static/app.js
config.example.json    sample config with dummy paths
tests/                 unittest
```

## Security

- The server binds to `127.0.0.1` only. It does not listen on the LAN. Do not port-forward it or put it behind a tunnel. There is no login, because it is a local desk: anyone who can reach the port can write a brief.
- Start it by hand with `start_ui.ps1`. Closing that window stops it. **Stop server** stops it too. Nothing here registers a service, a logon task, or a scheduled task.
- No secrets belong in this repo, in `config.example.json`, or in `config.json`. If the pipeline needs an API key, it should read that from its own environment, outside this repo. Do not put keys in `launcher_cmd`.
- `config.json` is gitignored. The committed sample uses dummy `C:\PodcastPipeline` paths.
- Book choices are resolved and rejected when they escape `books_dir`, when they are symlinks, or when the extension is not pdf, epub, txt, or md.
- The brief path is inserted into `launcher_cmd` as a PowerShell single-quoted literal. `launcher_cmd` itself is local configuration, so it is trusted on this PC.
- Request bodies are capped at 32 KB. Status text is capped at 16 KB.
- The launched pipeline is detached, so it keeps running after the desk stops. Stop server does not kill it.

## Troubleshooting

- **Missing config.json.** Copy `config.example.json` and edit the paths.
- **Port in use.** Pass `-Port` with another port, or close the other desk window.
- **Empty shelf.** The books folder is missing, or it has no pdf, epub, txt, or md files. A theme still works.
- **Briefs folder does not exist.** Create `briefs_dir` before submitting.
- **Pipeline did not start.** Run once with `-DryRun` and confirm the brief file. Then check `launcher_cmd`. The desk looks for `powershell.exe` (Windows PowerShell 5.1), not `pwsh`.
- **Browser did not open.** Open the `http://127.0.0.1:...` URL printed in the window. Use `127.0.0.1`, not a LAN address.
