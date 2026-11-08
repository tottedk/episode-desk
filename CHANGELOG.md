# Changelog

Entries describe changes in this repository. The pipeline that renders episodes lives elsewhere. Nothing under Unreleased is on `main` until its pull request is merged.

## Unreleased

### 2026-11-08 — public readiness

- README install and usage updated for content style v2.6 and the Humanity field, with an LLM-limits section.
- Sample config: Lachlan is listed under `not_ready_voices`. Clara is the ready guest in the sample. Elliot stays off the page. This matches a 2026-11-03 quality review that took Lachlan out of production casting and kept Elliot out for flat delivery. Voice assets are not part of this source release. The code default used when `not_ready_voices` is omitted still does not name Lachlan.
- Prominent "Built with Fish Audio" attribution on the page and in the README. Drama 3 is identified as Fish Audio Community License v1.0, not MIT. No model weights are included. VibeVoice-7B is documented as an optional fallback whose installed weights' license is unverified.
- `LICENSE`: MIT for original Episode Desk code by Thomas Jensen. An audit found no vendored third-party source and no package dependencies.
- `.gitignore` extended for secrets, weights, voice references, audio, and local runtime folders. That does not rewrite history.
- `KNOWN_ISSUES.md` added.

### 2026-11-07 — desk, content template v2.6

- Default script style is v2.6. v2.5 and v2.3 remain available.
- Humanity field: `low`, `medium`, or `high`, with `medium` when the field is omitted. The brief stores it next to tone and depth. `GET /api/options` returns `humanity_levels` and `default_humanity`.
- Unit tests after that change: 76 passed on Python 3.12.3. The admin-dependent symlink skip was not taken on that run, because symlink creation succeeded.
- After the public-readiness docs and sample-config correction, the suite is 78 passed on the same interpreter. The symlink skip was again not taken.

## 2026-11-01

- Replaced the notes field with Angle and Skip. Each is optional, at most 2000 characters. A request that still sends `notes` stores that text as `angle` when `angle` is empty. New briefs do not include `notes`.
- Book uploads (pdf, epub, txt, md, up to 200 MB) and a guest roster that stays on the page when names are missing from `voices`. `library_enabled` can hide the library. Not-ready guests are shown and cannot be submitted.
- Removed the quiz control. Briefs still write `"quiz": false`.
- Topic-first schema 2 briefs: required topic, optional books, web research on by default.

## 2026-10-25

- Added the loopback desk: one static page, a standard-library HTTP server on `127.0.0.1`, and `start_ui.ps1`. No service and no scheduled task.
- Fixed the Windows launcher flags. `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` (`0x208`) made PowerShell 5.1 exit without running `-Command` while `Popen` still returned a pid. The flags are now `CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP` (`0x08000200`).
- Fixed the false startup failure. A short launcher that exits 0 (the brief launcher registers a scheduled task and returns in about a second) is a successful handoff. A non-zero exit inside the two-second wait is reported with the code, and the brief is kept.

## Separate pipeline, not released from this repo

These local pipeline changes were recorded on 2026-11-07 and 2026-11-01. Their files are not in Episode Desk. Landing a desk pull request does not release them.

- Technical v1.14: sentence- and emotion-aware Drama 3 chunk boundaries, 240-character internal chunks, whitelisted delivery directions, flat-pitch detection, and up to two retries.
- Carter: per-segment tempo calibration (plan 156, bounds 0.72–0.95) instead of a fixed 0.86. Mix QC stays 145–175 words per minute, with no intra-line pause over 1.5 seconds. A short test was about 162–165 words per minute. A full episode is still pending.
- Content v2.6, as consumed by the pipeline: Humanity low/medium/high (medium default), everyday beats, fictional personal angles, one returning tangent, a jargon cap, and shorter turns.
- 2026-11-01: pre/post episode QC, duplicate and label guards, part-join echo removal, and guarded fact-check replacement. The regression fixtures were 32 cases, with zero misses and zero false alarms in that finite set. Technical v1.13 / content v2.5: topic-first briefs with web research and optional books.
