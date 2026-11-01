# Episode desk

Episode desk is a small local page for setting up a podcast episode before a pipeline on the same Windows PC generates it. You start with what the episode is about, then the length, one or two guest voices, the tone, and the depth. Books are optional. The desk writes a brief JSON file and starts the pipeline with that file. It does not generate audio itself.

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
4. Put source files (`.pdf`, `.epub`, `.txt`, `.md`) in `books_dir`. You can also upload those same types from the page. Uploads are saved under `uploads_dir` (the desk creates that folder on the first upload).
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
| `books_dir` | Library folder of source files. Relative paths are resolved next to `config.json`. Ignored when `library_enabled` is false. |
| `uploads_dir` | Optional. Folder for books uploaded from the page. Relative paths are resolved next to `config.json`. If the key is omitted, the default is `uploads/books` next to the config file (`uploads\books` on Windows). The desk creates it on the first upload. |
| `library_enabled` | Optional. `true` by default. Set it to `false` to hide the library picker and stop accepting files from `books_dir`. Uploads still work. One flag, so the library folder can be switched off later. |
| `briefs_dir` | Folder where `brief_<slug>_<timestamp>.json` is written. Must already exist. |
| `launcher_cmd` | PowerShell command template. `{brief_path}` is replaced with the brief path, single-quoted. |
| `voices` | Every voice the desk knows, including Carter and anyone you want hidden. |
| `banned_voices` | Optional. These names are never offered as guests. If the key is omitted, the default is Maya, Declan, Alice, Mary. |
| `not_ready_voices` | Optional. These guests are shown and cannot be picked, because they have no Drama 3 clip yet. If the key is omitted, the default is Isla, Marcus, Willa, Zara, Imogen, Frank, Samuel. Remove a name, and add it to `voices`, when that clip exists. |
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
  "uploads_dir": "uploads/books",
  "library_enabled": true,
  "briefs_dir": "C:\\PodcastPipeline\\briefs",
  "launcher_cmd": "& 'C:\\PodcastPipeline\\launch_episode.ps1' -BriefPath {brief_path}",
  "voices": ["Carter", "Clara", "Lachlan", "Isla", "Marcus", "Willa", "Zara", "Imogen", "Frank", "Samuel", "Hugh", "Maya", "Declan", "Alice", "Mary"],
  "banned_voices": ["Maya", "Declan", "Alice", "Mary"],
  "not_ready_voices": ["Isla", "Marcus", "Willa", "Zara", "Imogen", "Frank", "Samuel"],
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
- Elliot is never selectable. His Drama 3 voice is monotone. He is not in the sample roster. If a local `config.json` still lists him, the desk leaves him off the page.
- `banned_voices` are never offered. The default list is Maya, Declan, Alice, Mary.
- The page always lists the guest roster: Clara, Lachlan, Isla, Marcus, Willa, Zara, Imogen, Frank, Samuel. A name is listed even when it is missing from `voices`. That roster lives in the code, so a local `config.json` that only puts Clara and Lachlan in `voices` still shows the other seven.
- A guest can be picked only when the name is in `voices` and not in `not_ready_voices`. Everyone else on the roster is shown greyed out, with the name struck through and the tag "voice not ready", and the desk will not accept them. Clara and Lachlan are the ready guests in the sample. The sample not-ready list is Isla, Marcus, Willa, Zara, Imogen, Frank, and Samuel. When a Drama 3 clip is added, put that name in `voices` and remove it from `not_ready_voices`.
- If `not_ready_voices` is omitted, those seven names are not ready. An empty list does not by itself enable a roster name: the name also has to be in `voices`. Other ready names from `voices` are listed after the roster.
- You pick 1 or 2 ready guests.

The working directory of the launched PowerShell process is the briefs folder. The brief path on the command line is absolute.

On Windows the process is created with `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` (`0x08000200`). `DETACHED_PROCESS` (`0x8`) is not used: under PowerShell 5.1 it makes `powershell.exe` exit 0 without running `-Command`. After starting it, the desk waits about 2 seconds. Still running, or an exit code of 0, counts as launched. That is what a launcher does when it only registers a scheduled task and returns. A non-zero exit in that window is a failure, and the message includes the exit code. The brief stays on disk either way.

## Form

- **What's the episode about?** Required. A question, claim, or prompt, up to 600 characters.
- **Books.** Optional, 0 to 2 files, from the library, from an upload, or one of each. pdf, epub, txt, or md. An upload can be up to 200 MB. Uploaded files are stored under `uploads_dir` with a safe generated name and count toward the same limit. A topic and books can be used together.
- **Research the web.** On by default. Turn it off only when at least one book or PDF is attached.
- **Script style.** `v2.5` (default, cast + short turns) or `v2.3` (legacy).
- **Length.** 20, 30, or 40 minutes. Default 40.
- **Guest voices.** The nine roster names, each as a name plus at most a short tag. Pick 1 or 2 ready names. Guests without a Drama 3 clip are on the page, struck through, tagged "voice not ready", and cannot be submitted.
- **Tone.** calm, playful, debate, or serious.
- **Depth.** intro, standard, or deep.
- **Speech.** Fish Audio Drama 3, fallback VibeVoice-7B. Not editable.
- **Angle.** Optional, up to 2000 characters. The episode's angle or focus.
- **Skip.** Optional, up to 2000 characters. Chapters, topics, or tangents to leave out.

On submit the desk validates the form, writes the brief, and starts `launcher_cmd` unless `--dry-run` / `-DryRun` is on. The page shows the brief path and, when it launched the pipeline, the process id. The status panel polls `status_file` every 10 seconds.

## Brief schema

`schema_version` is `2`. The file name is `brief_<slug>_<YYYYMMDD>_<HHMMSS>.json`. If that name already exists, `_1`, `_2`, and so on are appended until the name is free. The `id` field is the file name without `.json`.

The slug comes from the topic. It is lowercase ASCII, non-letters become hyphens, and it is at most 48 characters. The timestamp is the PC's local time.

```json
{
  "schema_version": 2,
  "id": "brief_on-lighthouses_20261025_143012",
  "created_at": "2026-10-25T14:30:12-04:00",
  "source": {
    "type": "topic",
    "topic": "On lighthouses",
    "files": [
      "C:\\PodcastPipeline\\books\\On Lighthouses.pdf"
    ],
    "research": "web"
  },
  "content_style": "v2.5",
  "length_minutes": 40,
  "host": "Carter",
  "guest_voices": ["Clara", "Lachlan"],
  "tone": "calm",
  "depth": "deep",
  "quiz": false,
  "tts": {
    "engine": "Fish Audio Drama 3",
    "fallback": "VibeVoice-7B"
  },
  "angle": "",
  "skip": ""
}
```

A topic with no books uses `"files": []`. With web research off, `source.research` is `"none"` and `files` has one or two paths.

The desk writes schema 2 only. Briefs already sitting in the briefs folder are not rewritten. The pipeline still accepts older schema 1 briefs.

| Field | Rule |
| --- | --- |
| `schema_version` | Always `2`. |
| `id` | `brief_<slug>_<YYYYMMDD>_<HHMMSS>` with an optional `_N` suffix. |
| `created_at` | ISO 8601 local time with a numeric offset, to the second. |
| `source.type` | Always `topic`. |
| `source.topic` | Required. 1 to 600 characters after whitespace is collapsed. |
| `source.files` | Absolute paths. Zero, one, or two. Each path stays inside `books_dir` or inside `uploads_dir`. The pipeline reads the paths the same way either way. |
| `source.research` | `web` or `none`. `none` requires at least one file. |
| `content_style` | `v2.5` (default) or `v2.3`. |
| `length_minutes` | `20`, `30`, or `40`. |
| `host` | Always `Carter`. |
| `guest_voices` | One or two names from the selectable list. |
| `tone` | `calm`, `playful`, `debate`, or `serious`. |
| `depth` | `intro`, `standard`, or `deep`. |
| `quiz` | Always `false`. The desk does not ask. A value sent by the client is ignored. The pipeline still reads the key. |
| `tts.engine` | Always `Fish Audio Drama 3`. |
| `tts.fallback` | Always `VibeVoice-7B`. The pipeline may use it only as a fallback. |
| `angle` | String. May be empty. The episode's angle or focus, at most 2000 characters. |
| `skip` | String. May be empty. Chapters, topics, or tangents to leave out, at most 2000 characters. |

A request that still sends `notes` stores that text as `angle` when `angle` is empty. The brief does not include `notes`.

Anything the browser sends for `host`, `tts`, or `quiz` is ignored. The server writes the fixed values, including `"quiz": false`. The status panel reads the pipeline status file as plain text. A line containing `step=gen research` is shown as "Researching the web...". A line containing `ABORT research too thin` is shown unchanged.

## HTTP

The page and these routes are served on `127.0.0.1` only:

| Method | Path | Role |
| --- | --- | --- |
| GET | `/` | The desk page. |
| GET | `/api/options` | Shelf, guest roster, selectable voices, and the fixed engine. The launcher command is not included. |
| GET | `/api/status` | Plain text from `status_file`, capped at 16 KB. |
| GET | `/api/health` | `{"ok": true, "bind": "127.0.0.1", ...}`. |
| POST | `/api/upload` | Save one pdf, epub, txt, or md file under `uploads_dir`. Capped at 200 MB. |
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
- Book choices are resolved and rejected when they escape `books_dir` or `uploads_dir`, when they are symlinks, or when the extension is not pdf, epub, txt, or md. With `library_enabled` set to false, library paths are rejected and the shelf is not read.
- An upload keeps only a sanitized basename, then adds a timestamp and a random suffix. The original name is not used as a path, so `..\secret.txt` cannot leave `uploads_dir`. The brief stores the absolute path of that saved file.
- The brief path is inserted into `launcher_cmd` as a PowerShell single-quoted literal. `launcher_cmd` itself is local configuration, so it is trusted on this PC.
- JSON request bodies are capped at 32 KB. A book upload is a separate request, capped at 200 MB plus a small allowance for the multipart headers. Status text is capped at 16 KB.
- `uploads/` is gitignored. Uploaded books stay on this PC.
- The launched pipeline is in its own process group and has no console window, so it keeps running after the desk stops. Stop server does not kill it. A non-zero PowerShell exit within about 2 seconds is reported as a failed launch.

## Troubleshooting

- **Missing config.json.** Copy `config.example.json` and edit the paths.
- **Port in use.** Pass `-Port` with another port, or close the other desk window.
- **Empty shelf.** The books folder is missing, or it has no pdf, epub, txt, or md files. Upload a file, or use a topic with web research. Turn research off only when a book is attached. If `library_enabled` is false, the library picker is hidden on purpose.
- **Briefs folder does not exist.** Create `briefs_dir` before submitting.
- **Pipeline did not start.** Run once with `-DryRun` and confirm the brief file. Then check `launcher_cmd`. The desk looks for `powershell.exe` (Windows PowerShell 5.1), not `pwsh`. If the message includes an exit code, PowerShell quit with that non-zero code within about 2 seconds. The brief file is still there. An exit code of 0 is a successful handoff.
- **Browser did not open.** Open the `http://127.0.0.1:...` URL printed in the window. Use `127.0.0.1`, not a LAN address.
