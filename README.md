# AI Clipping Machine (local-first)

Researches, detects, edits and quality-checks vertical clips (1080×1920 H.264/AAC MP4) for three
independent brands — **AMP Clipper**, **CORE Clipper** and **LosPollosTV Clipper** — and exports
approved clips to local folders for **manual** publishing on YouTube Shorts / TikTok.

Nothing is uploaded, published or hosted. There is no dashboard: it is operated from Claude Code
through `python main.py …`. Google Gemini is the only external AI service (optional).

> **Publicly accessible does not mean free to use.** Media is only processed when the local
> permission registry contains evidence-backed approval for every participant. See *Rights*.

## Setup

```bash
python3 -m pip install -r requirements.txt   # Python 3.12+, plus FFmpeg/FFprobe on PATH
cp .env.example .env                          # add GEMINI_API_KEY to enable AI research (optional)
python main.py doctor
python main.py init
```

* **Whisper**: `faster-whisper` downloads the `small.en` model from Hugging Face on first use.
  Offline: download a model folder and set `WHISPER_MODEL_PATH` in `.env`. You can also supply
  transcripts yourself (`.json`, `.srt`, `.vtt` next to the video), e.g. from a diarization tool —
  JSON segments may carry `speaker` labels, which power interaction / group-chemistry scoring.
* **Gemini**: model name lives in `config/global.yaml` (`google_ai.model`). Without a key the
  machine still works with local signals; research runs are recorded as `skipped`, never faked.

## Daily workflow

1. **Add authorized media.** Drop recordings into `sources/inbox/<amp|core|lospollostv>/` with a
   sidecar `<name>.source.yaml` (see `assets/templates/example.source.yaml`), or register one:
   ```bash
   python main.py sources add --profile amp --file /path/stream.mp4 --creators "Kai Cenat,Fanum" --third-party none
   ```
2. **Record permissions** (evidence required for approval):
   ```bash
   python main.py rights add --scope creator --value "Kai Cenat" --holder "Kai Cenat" --status APPROVED --evidence "agreement-2026-10.pdf" --ops download_or_import,edit,distribute,commercial_use
   ```
3. **Run** once (`python main.py process amp`) or continuously (`python main.py start`).
4. **Collect** clips from `outputs/<BRAND>/<YYYY-MM-DD>/{clips,thumbnails,metadata}/`.
   `python main.py clips --decision approved` lists exact file paths.
5. **Review** `NEEDS_REVIEW` clips: `python main.py review list`, then `review approve <id>` or
   `review reject <id>`. Human approval never overrides a failing rights or technical check.
6. **Feed back performance**: `python main.py analytics template --profile amp`, fill in the
   numbers you have, `python main.py analytics import file.csv`. Blank cells stay blank.

## Commands

| Goal | Command |
|---|---|
| Start / single cycle | `python main.py start [--profile amp] [--once]` |
| Pause / resume | `python main.py pause` / `python main.py resume` |
| Research a profile | `python main.py research amp [--gemini]` |
| Process approved sources | `python main.py process [amp\|core\|lospollostv]` |
| Candidate moments | `python main.py candidates --profile core --status new` / `candidate <id>` |
| Approved / rejected clips | `python main.py clips --decision approved` / `--decision rejected` / `clip <id>` |
| Rights status | `python main.py rights list` / `rights check <source_id>` |
| Errors | `python main.py errors` |
| Analytics | `python main.py analytics --profile amp` |
| Import performance CSV | `python main.py analytics import perf.csv` |
| Compare LosPollosTV formats | `python main.py compare-formats` |
| Quality threshold | `python main.py set-threshold core 65 --reason "..."` |
| Duration limits | `python main.py set-duration amp --min 20 --max 150` |
| Learning | `python main.py learning analyze` / `learning list` / `learning apply <id>` / `learning history` |
| Status | `python main.py status` |
| Transcript search | `python main.py search "race"` |
| Creator attention | `python main.py attention` |
| GTA 6 trends + daily plan | `python main.py trends research` / `trends plan` |
| Hype / countdown edit | `python main.py hype make trailer1.mp4 trailer2.mp4 --profile gta6` (`hype templates` lists sounds) |
| Learn a viral edit's template | `python main.py hype learn <tiktok url>` / `hype learn-trending --top 3` |
| Day's template edits | `python main.py hype daily` (or `hype render <template id>`) |
| Reaction memes | `python main.py meme add <tiktok url> --what ... --emotion ...` / `meme daily --n 8` / `meme list` |
| Durable memory | `python main.py memory save` / `memory load` |

## GTA 6 niche + learning formats from example clips

The `gta6` profile (`config/gta6.yaml`) is topic-based: any streamer or video about GTA 6, with
GTA-specific categories (funny_gameplay, chaos_moment, police_chase, heist_mission, glitch_bug,
easter_egg, streamer_reaction, story_moment, tips_tricks, news_trailer). Its layout policy is
`style_examples`: each clip copies the editing format of your example clips for that category.

```bash
python main.py examples add example1.mp4 --profile gta6 --category funny_gameplay --label "split cam + gameplay"
python main.py examples list --profile gta6
python main.py examples choose --profile gta6 --category police_chase   # which format a new clip would get
```

Each example is measured locally (layout: split screen / blurred bands / full screen, split height,
camera position, cuts per minute, length, loudness) and, when Gemini is available, described from 4
frames (caption position/colours/case/words per line, title banner, effects). The result is a style
preset. Without an example for a category, the most common learned format is used. Profiles are any
`config/<id>.yaml` with an `id:` — add new brands without code changes.

## How it works

```
discover (inbox · YouTube RSS metadata · Gemini grounded search leads)
  → rights gate (processing) → ingest authorized media → transcribe (faster-whisper / sidecar)
  → analyze (audio arousal · scene/motion/faces · transcript semantics · speaker turns · trends · Gemini)
  → candidates + context windows (setup → moment → payoff, snapped to sentences)
  → cross-stream event grouping → duplicate check
  → adaptive edit (face-tracked crop / fit-blur / LosPollosTV A·B·C) + captions + loudnorm
  → QC (technical · content · rights at export · monetization) → APPROVED | NEEDS_REVIEW | REJECTED
  → export (only APPROVED) → manual performance import → per-profile analytics → recommendations
```

* **Scores** (0–10 components, 0–100 total) are AI-estimated potential, not predicted views.
  Components: hook, entertainment, emotion, context completeness, story, payoff, originality,
  shareability, visual quality, audio quality, platform suitability, group chemistry. Weights and
  thresholds are per profile in `config/<profile>.yaml`.
* **Adaptive duration**: 15–180 s (configurable). Weak moments are not padded; a moment that
  cannot stand alone within the limits is dropped rather than cut short.
* **Cross-stream detection** (AMP/CORE): candidates from different sources are grouped by
  wall-clock overlap (`recorded_start`) or shared dialogue; the best-quality source is kept.
* **LosPollosTV**: each distinct moment is assigned exactly one of Format A (split GTA),
  B (streamer focus) or C (hybrid), balanced by sample count. A and C require gameplay in
  `assets/approved_gameplay/` registered as an APPROVED **asset** permission:
  ```bash
  python main.py rights add --scope asset --value assets/approved_gameplay/my_run.mp4 --holder "Me" --status APPROVED --evidence "recorded on my own copy" --ops edit,distribute,commercial_use
  ```
  `compare-formats` recommends a format only with ≥20 samples per format and a length-adjusted lead.

## Rights

Permission records (`rights add`) have a scope (`creator`, `channel`, `source`, `category`,
`asset`, `user_owned`), a status (`APPROVED`, `APPROVED_WITH_CONDITIONS`, `PENDING_VERIFICATION`,
`REJECTED`, `EXPIRED`), evidence, operations, attribution, expiry and restrictions
(`{"max_clip_seconds": 60, "allowed_profiles": ["amp"]}`). The gate:

* requires coverage for **every participant** (or a source-level record with `--all-participants`);
* checks `download_or_import` + `edit` before processing and `edit` + `distribute` +
  `commercial_use` before export;
* blocks export while a source's third-party content (music, video, overlays) is `unknown`
  (→ NEEDS_REVIEW) or `present_uncleared` (→ REJECTED);
* verifies attribution text is present in the clip metadata;
* never downloads web pages: `--direct-download` URLs must be direct media files your permission
  allows you to download. No DRM, login, or rate-limit circumvention exists in this codebase.

The monetization assessment is an internal heuristic. It does not guarantee YouTube Partner
Program or TikTok monetization. Clips primarily promoting gambling are blocked.

## Layout

```
main.py  clipper/{core,research,rights,ingestion,transcription,detection,clipping,editing,metadata,quality,analytics,export}
config/  database/  sources/{inbox,approved,pending,rejected}/  assets/  outputs/  work/  logs/  tests/
```

Tests: `python -m pytest -q` (renders real clips from synthetic media; ~3–4 minutes).
