# Known issues

This file is about Episode Desk, the local page that writes a brief and launches a pipeline. The pipeline is a separate project and is not in this repository.

## Release validation

Content style v2.6 and the Humanity field are covered by this repo's unit tests. The separate pipeline's technical template v1.14 and content template v2.6 have passed short tests only. No new full episode has been rendered with them. A complete passing episode is still a release gate for the pipeline, and it needs an explicit go-ahead before anyone runs it. This desk does not render audio, and a later desk patch does not repair episodes that were already delivered.

## Desk

- Windows spawn flags: `DETACHED_PROCESS` (`0x8`) made Windows PowerShell 5.1 exit 0 without running `-Command`, and the desk reported success. Fixed on 2026-10-25. The flags are `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` (`0x08000200`).
- False startup failure: a launcher that registers work and exits 0 within about two seconds was reported as a failure. Fixed on 2026-10-25. Still running, or exit code 0, counts as launched. A non-zero exit in that window is a failure and the message includes the code. The brief stays on disk.
- The desk reads `config.json` at startup. Restart it to pick up changes.
- A name marked ready in a local config is not proof of a right to use that voice.
- The symlink shelf test calls `skipTest` when creating the link raises `OSError`. That is what Windows does without permission to create symlinks. On a machine that can create symlinks, the skip is not taken.

## Voices

- Lachlan and Elliot are not ready.
- Elliot is excluded in code, including when a local `config.json` lists him. He is not on the page. His Drama 3 delivery is monotone.
- The sample config lists Lachlan in `voices` and in `not_ready_voices`, so he is shown and cannot be picked. Clara is the ready guest in the sample.
- If `not_ready_voices` is omitted, the code default is Isla, Marcus, Willa, Zara, Imogen, Frank, and Samuel. That default does not include Lachlan, so a config that lists him and omits the key will still offer him. The sample does not omit the key.
- Maya, Declan, Alice, and Mary are the default banned guests. Carter is always the host. Hugh is never paired with Carter and is never selectable.
- VibeVoice-7B is an optional fallback named on the brief. Its installed weights' license and provenance are unverified. Do not publish an episode that depended on that fallback until the local model origin, revision, and license have been checked. This repository does not contain those weights.

## Content

The desk does not check facts. A Humanity setting does not make a scripted guest's personal angle authentic. Facts, quotations, fictional anecdotes, and sources need a person to check them, and someone needs to listen before publication.

## Separate pipeline (not in this repository)

These notes are from the owner's 7 November 2026 pipeline review. They are not bugs in this desk, and they were not re-tested here.

- Carter tempo: a fixed 0.86 previously produced 177–180.5 words per minute in full episodes, above the unchanged 145–175 gate. A per-segment plan of 156 (bounds 0.72–0.95) measured about 162–165 words per minute in a short test. Large atempo corrections may smear sound. Listening approval is pending.
- Flat delivery: sentence-aware chunks, delivery directions, and a pitch-variation gate reduce resets. After two retries, the best flat take is retained and flagged, not certified natural. The real-audio retry path was not triggered in the short test.
- Previous-take continuity is not enabled. Its per-chunk reload overhead was estimated at about one additional hour per episode.
- Spoken labels, duplicate endings, and part-join echoes have guards and regression fixtures. That does not prove error-free production. Existing completed audio is not regenerated.
- Old delivered episodes can retain known issues. A later patch is not a retroactive repair.

## History

`.gitignore` stops new audio, weights, local configs, and runtime output from being added. It does not remove anything already committed. See the history scan before making this repository public.
