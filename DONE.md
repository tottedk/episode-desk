# Done

Episode desk is a local page for writing a podcast brief and handing it to a pipeline on the same PC.

- [x] Python standard library only. No pip packages and no build step.
- [x] Listens on `127.0.0.1` only. `server.py` has no wildcard bind.
- [x] Manual start: `start_ui.ps1` runs the server in that window and opens the browser. Close the window, or use **Stop server**. No service, startup item, or scheduled task.
- [x] `config.example.json` is the committed sample, with dummy `C:\PodcastPipeline` paths. `config.json` is gitignored. No secrets in the repo.
- [x] Source is up to two shelf files (pdf, epub, txt, md) or a theme.
- [x] Length is 20, 30, or 40 minutes, default 40.
- [x] One or two guest voices. Carter is always the host and is not a guest. Hugh is never selectable. `banned_voices` defaults to Maya, Declan, Alice, Mary when the key is omitted.
- [x] Tone, depth, quiz, optional notes.
- [x] Speech is fixed: Fish Audio Drama 3, fallback VibeVoice-7B. The page has no control for it, and a client-supplied engine is ignored.
- [x] Submit validates, writes `brief_<slug>_<timestamp>.json`, and starts `launcher_cmd` detached. `--dry-run` / `-DryRun` writes the brief and does not launch.
- [x] Status panel reads `status_file` on load and every 10 seconds.
- [x] Unittest coverage for validation, brief writing, the launcher, and the loopback bind.

## Verification

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
