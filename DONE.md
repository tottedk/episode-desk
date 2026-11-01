# Done

Episode desk is a local page for writing a podcast brief and handing it to a pipeline on the same PC.

- [x] Python standard library only. No pip packages and no build step.
- [x] Listens on `127.0.0.1` only. `server.py` has no wildcard bind.
- [x] Manual start: `start_ui.ps1` runs the server in that window and opens the browser. Close the window, or use **Stop server**. No service, startup item, or scheduled task.
- [x] `config.example.json` is the committed sample, with dummy `C:\PodcastPipeline` paths. `config.json` is gitignored. No secrets in the repo.
- [x] The episode starts with a required topic (a question, claim, or prompt, up to 600 characters). Books are optional, 0 to 2, from the library or from an upload, and can be used with the topic. Uploads are pdf, epub, txt, or md, up to 200 MB, saved under `uploads_dir`. `library_enabled` defaults to true and is the switch that turns the library folder off. Web research is on by default. Turning it off requires a book or PDF. Script style is v2.5 by default, or v2.3.
- [x] Length is 20, 30, or 40 minutes, default 40.
- [x] One or two guest voices. Carter is always the host and is not a guest. Hugh is never selectable. Elliot is never selectable (monotone Drama 3 voice) and is not on the page. `banned_voices` defaults to Maya, Declan, Alice, Mary when the key is omitted. The page always lists Clara, Lachlan, Isla, Marcus, Willa, Zara, Imogen, Frank, and Samuel, even when a name is missing from `voices`. Clara and Lachlan are selectable when they are in `voices`. The other seven are shown disabled, struck through, and tagged "voice not ready", and cannot be submitted.
- [x] Briefs are schema 2: `source.type` is `topic`, `source.research` is `web` or `none`, and `content_style` is `v2.5` or `v2.3`. The slug comes from the topic. Older briefs already on disk are left alone.
- [x] Tone, depth, optional notes. Briefs always include `"quiz": false`. The page does not ask, and a client-supplied quiz value is ignored.
- [x] Speech is fixed: Fish Audio Drama 3, fallback VibeVoice-7B. The page has no control for it, and a client-supplied engine is ignored.
- [x] Submit validates, writes `brief_<slug>_<timestamp>.json`, and starts `launcher_cmd`. On Windows the flags are `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` (`0x08000200`). `DETACHED_PROCESS` is not used. Still running, or exit code 0 within about 2 seconds, counts as launched. A non-zero exit in that window is a failure and the message includes the code. The brief is kept. `--dry-run` / `-DryRun` writes the brief and does not launch.
- [x] Status panel reads `status_file` on load and every 10 seconds.
- [x] Unittest coverage for validation, brief writing, uploads, the guest roster, the launcher, and the loopback bind.

## Uploads and the guest roster

Books can come from the library or from an upload. An upload is stored under `uploads_dir` (default `uploads/books` next to `config.json`) with a sanitized unique name, and the brief stores that absolute path the same way it stores a library path. `library_enabled` defaults to true. Setting it to false hides the library and rejects library paths. Uploads still work.

The guest list is the roster in code, not whoever happens to be in `voices`. A config whose `voices` are only Carter, Clara, Lachlan, and Elliot still shows Isla, Marcus, Willa, Zara, Imogen, Frank, and Samuel, greyed out and struck through, with the tag "voice not ready". The guest section is the name plus that tag. The old Hugh/Elliot/config paragraph is gone.

```text
python3 -m unittest discover -s tests -v
```

Result: **73 tests, OK**.

Live server, dry run, port 47221, with `voices` set to Carter, Clara, Lachlan, and Elliot, and `not_ready_voices` set to the other seven. Elliot was not on the page. Clara and Lachlan could be selected. Clicking Isla did not select her. Uploading `harbor.md` added it beside the library picker, inside the same two-book limit. Submitting the topic "How the lamp changed the coast", that upload, Clara, calm, and deep wrote a schema 2 brief whose file path is inside the uploads folder. The page said the pipeline was not started. At about 390px wide the book row stacks and the form sits above the status panel.

## Quiz removed

The page no longer asks whether the episode ends with a quiz. Briefs still include `"quiz": false` so the pipeline can read the key. A payload that sends `quiz` is accepted and the value is ignored.

```text
python3 -m unittest discover -s tests -v
```

Result: **63 tests, OK**.

A dry-run submit in the browser (topic "On lighthouses", Clara, calm, deep, and a note) wrote a brief and said the pipeline was not started. Depth is followed by Speech. There is no Quiz control.

## Topic-first briefs

Unit tests, from the repo root on Python 3.12.3:

```text
python3 -m unittest discover -s tests -v
```

Result: **62 tests, OK**.

Live server, dry run, port 47221, using the sample roster (Clara, Lachlan, Isla, Marcus, Willa, Zara, Imogen, Frank, Samuel, plus Carter, Hugh, and the banned names). Elliot is not in the roster.

- `GET /api/options` offers Clara and Lachlan as ready guests. Isla, Marcus, Willa, Zara, Imogen, Frank, and Samuel are in `voice_choices` with `ready: false` and the note "voice not ready for Drama 3 yet". Carter, Hugh, Elliot, Maya, Declan, Alice, and Mary are absent. `skip.exe` was not on the shelf.
- The page opens on **What's the episode about?**, with the counter at 0/600. **Research the web** is checked. Script style is v2.5.
- An empty submit showed errors for the topic, guests, tone, and depth.
- A topic with research turned off and no book showed "Attach a book or PDF, or turn on web research."
- A third book and a third guest would not stay selected.
- Submitting the topic "AI is built on all of human knowledge: will it inherit our capacity for evil?", Coast Notes.txt, On Lighthouses.pdf, Clara, Lachlan, debate, standard, and script style v2.5 wrote a schema 2 brief. `source.type` is `topic`, `source.research` is `web`, `content_style` is `v2.5`, `host` is Carter, and the engine is Fish Audio Drama 3. The page said the pipeline was not started.
- A status line `step=gen research ...` is shown as "Researching the web...". `ABORT research too thin` is shown unchanged.
- On the page, Clara and Lachlan can be selected. Isla, Marcus, Willa, Zara, Imogen, Frank, and Samuel are disabled, each with the note "voice not ready for Drama 3 yet". Clicking Isla does not select her.
- At about 390px wide the form sits above the status panel and the submit button spans the form.

## Earlier verification (books or a theme)

Unit tests, from the repo root on Python 3.12.3:

```text
python3 -m unittest discover -s tests -v
```

Result: **47 tests, OK**.

Live server, dry run, port 47221:

- `/proc/net/tcp` showed one LISTEN socket for that port. The local address was `0100007F`, which is `127.0.0.1`. There was no IPv6 listener for the port.
- `GET /api/health` returned `{"ok": true, "bind": "127.0.0.1", "port": 47221, "dry_run": true}`.
- `GET /api/options` offered Elena, Jonah, Priya, Sam, Noah, and Ruth. Carter, Hugh, Maya, Declan, Alice, and Mary were absent. `skip.exe` was not on the shelf. pdf, epub, txt, and md files were.
- `POST /api/brief` with two books and guests Elena and Jonah wrote a brief and returned `"launched": false`. The file's `host` is Carter and `tts.engine` is Fish Audio Drama 3. The fallback is VibeVoice-7B.

The page was exercised in a browser against `http://127.0.0.1:47221/` (dry run). An empty submit showed errors for books, guests, tone, and depth. A third book and a third guest would not stay selected. Submitting On Lighthouses.pdf, Coast Notes.txt, Elena, Jonah, calm, deep, quiz yes, and a note wrote `brief_on-lighthouses_20261025_130629.json` and the page said the pipeline was not started. The status text was already visible, and the "Checked" time advanced on its own across the 10 second poll. At about 390px wide the form sits above the status panel and the submit button spans the form. Stop server was not used, so the desk stayed up.

`ss` was not installed in this environment. The bind check used `/proc/net/tcp` instead.

## Launcher fix

On Windows PowerShell 5.1, `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` (`0x208`) makes `powershell.exe` exit without running `-Command`. `Popen` still returns a pid, so the desk was reporting success. The flags are now `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` (`0x08000200`), which was the combination that kept the command running on that PC.

The 2 second wait does not treat a finished process as a failure. `start_brief.ps1` registers a scheduled task and exits 0 in about 1 second, and that is a successful launch. Still running after 2 seconds is also success. Only a non-zero exit in that window is an error, and the message includes the code. The brief file is left in place.

The `0x208` silent exit also returns code 0, with no output that identifies it. A stdout marker would have to be captured for the whole life of the pipeline, including launchers that stay running, so the desk does not try to tell those two exit-0 cases apart. Not using `DETACHED_PROCESS` is what prevents the silent exit.

The symlink shelf test calls `skipTest` when creating the link raises `OSError`, which is what Windows does without permission to create symlinks. Extension filtering stays in its own test and still runs.

Verified here with:

```text
python3 -m unittest discover -s tests -v
```

Result: **52 tests, OK**. That includes the flag value `0x08000200` (and that bit `0x8` is off), a still-running process reported as launched, an exit code 0 reported as launched, and a non-zero exit reported as failure with the code and the brief still written. This machine is Linux, so `powershell.exe` itself was not launched here. Symlink creation works on this machine, so the skip path was not taken.
