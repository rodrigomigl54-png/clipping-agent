# Project Status

_Last updated: 2026-11-03 — all 7 phases implemented. 40 automated tests passing (`python -m pytest -q`)._

## Completed (implemented and tested)

| Phase | Component | Module | Verified by |
|---|---|---|---|
| 1 | YAML + Pydantic config, CLI-managed overrides with change history | `clipper/config.py` | unit + CLI tests |
| 1 | SQLite schema (WAL, transactions, FTS5 transcript search) | `core/database.py` | all tests |
| 1 | Structured JSON logging with secret redaction | `core/logger.py` | unit test |
| 1 | CLI (all operations listed in README) | `cli.py`, `main.py` | CLI test + manual run |
| 2 | Permission registry (scopes, evidence-required approval, history) | `rights/permission_registry.py` | `test_rights.py` |
| 2 | Rights gate (all participants, ops, expiry, restrictions, attribution, third-party content, assets) | `rights/rights_gate.py` | `test_rights.py`, pipeline tests |
| 2 | Monetization suitability (lexicon flags, reuse risk, gambling block) | `rights/monetization_check.py` | unit test |
| 2 | Source index + local inbox discovery with sidecars | `research/source_discovery.py` | pipeline tests |
| 2 | YouTube RSS metadata discovery (no downloads) | `research/source_discovery.py` | parser test (offline) |
| 2 | Gemini client: grounded search + JSON output, retries, failure recording | `research/google_ai.py` | fake-client tests |
| 2 | Research engine: 7-day window, leads, trends, research-run log | `research/research_engine.py`, `trend_analysis.py` | fake-client tests |
| 2 | Dynamic creator attention (weights, not quotas) | `research/attention.py` | CLI |
| 3 | Transcription: faster-whisper (word timestamps, VAD) + JSON/SRT/VTT sidecars with speakers | `transcription/` | sidecar tests |
| 3 | Audio analysis (baseline-relative arousal, silence, SNR, clipping) | `detection/audio_analyzer.py` | unit test |
| 3 | Visual analysis (scene change, motion, faces, sharpness) | `detection/visual_analyzer.py` | pipeline tests |
| 3 | Context analysis (setup → moment → payoff, sentence snapping, duration adaptation) | `detection/context_analyzer.py` | unit + pipeline tests |
| 3 | Viral detection + 12-component configurable scoring, optional Gemini semantic blend | `detection/viral_detector.py` | pipeline tests |
| 3 | Group-chemistry scoring (speakers, turns, faces, roast/argument/challenge) | `detection/viral_detector.py` | CORE test |
| 3 | Cross-streamer event grouping + best-source selection | `detection/cross_stream_detector.py` | pipeline test |
| 3 | Duplicate prevention (time overlap, transcript similarity, frame dHash, audio envelope) | `clipping/` | pipeline test |
| 4 | Authorized ingestion (local files; direct-media URLs with download permission only) | `ingestion/media_ingest.py` | pipeline tests |
| 4 | Face tracking with dead-zone + EMA smoothing | `editing/face_tracker.py` | mocked-detection test |
| 4 | Layouts: focus, fit-blur, split GTA (A), hybrid (C); emphasis zoom | `editing/layout_engine.py` | unit + render tests |
| 4 | ASS captions (per-profile style, emphasis colour, safe zones, low-confidence reporting) | `editing/caption_engine.py` | unit test |
| 4 | Renderer: 1080×1920 H.264/AAC, loudnorm, faststart | `editing/renderer.py` | ffprobe checks |
| 4 | LosPollosTV A/B/C experiment, one format per moment, licensed-gameplay gate | `editing/format_experiment.py` | 3 tests |
| 5 | Technical QC (resolution, codecs, A/V sync, full decode, black, silence, duration) | `quality/technical_checks.py` | pipeline tests |
| 5 | Content QC (context, hook, ending, edge dialogue, caption fidelity, confidence) | `quality/content_checks.py` | pipeline tests |
| 5 | Decision engine (rights/technical failures cannot be overridden) | `quality/quality_controller.py` | review test |
| 5 | Metadata: truthful titles (validator for AI titles), description, hashtags, attribution | `metadata/` | unit test |
| 5 | Thumbnail suggestion (sharp frame + face + title overlay) | `metadata/thumbnail_generator.py` | pipeline test |
| 5 | Export with checksum verification, permanent export registry | `export/export_manager.py` | pipeline tests |
| 5 | Human review workflow (`review approve/reject`) | `core/orchestrator.py` | pipeline test |
| 6 | CSV import (blank = unknown), template prefilled from our own records | `analytics/performance_import.py` | unit test |
| 6 | Per-profile analytics normalised to the profile's own median | `analytics/analytics_engine.py` | unit test |
| 6 | Format comparison (length-adjusted, ≥20 samples/format gate) | `analytics/format_comparison.py` | unit test |
| 6 | Learning recommendations (pending → apply/dismiss, logged) | `analytics/learning_engine.py` | unit test |
| 7 | Orchestrator with checkpoints, crash recovery, per-item failure isolation | `core/orchestrator.py` | recovery test |
| 7 | Scheduler: interval cycles, pause/resume, SIGINT/SIGTERM shutdown, single-runner lock, heartbeat | `core/scheduler.py` | manual `start --once` |

## Added 2026-11-11 (GTA 6 pivot)
- `gta6` topic profile; profiles are now auto-discovered from `config/*.yaml`.
- Style library (`clipper/styles/`): learn editing formats from example clips (local analysis + Gemini
  vision), choose per category, applied by the editor (`layout_policy: style_examples`): split camera +
  gameplay, blurred bands, full screen; caption position/colours/case/words; title banner style.
- On-screen title banner, Gemini semantic moment discovery, Gemini transcription fallback,
  private-test command, stacked-region layout. 45 tests passing.
- Limits: local split detection is heuristic (static graphic patterns can look like a split; Gemini
  vision overrides it); camera detection uses the largest/steady face — set `facecam_region` per
  channel for exact placement; Gemini free tier ≈20 requests/model/day.

## Added 2026-11-12
- Text safety (`clipper/editing/text_safety.py`): title card and captions are placed only outside
  protected areas — every face found in sample output frames, the real picture in blurred/black-band
  layouts, the centre of gameplay panels. Title shrinks before captions move; captions are turned off
  rather than covering content; QC reports `text_clear_of_content`.
- Letterbox (black bars) layout, image title card with colour emojis, examples from written analyses.
- Style library: 3 analysed GTA 6 examples (meme skit, streamer clip, hype montage — montage marked
  not yet supported); 21 more saved as pending (TikTok cannot be downloaded here; vidIQ credits used up).

## Added 2026-11-12 (later)
- All reachable reference clips analysed: 22 TikToks downloaded from their public pages (author, caption,
  engagement), Gemini video blueprints (hook, beat structure, every on-screen text, captions, effects, audio,
  pacing, ending, recipe) + local measurements. Library persisted in `config/style_examples/gta6.json`
  (auto-loaded); human summary in `docs/GTA6_PLAYBOOK.md`. 2 clips unavailable on TikTok.
- Detail tools: zoom-to-point, animated circle/arrow, label (placed off faces), freeze frame with audio pause;
  used automatically only when Gemini finds a key visual detail (category or "look at…" cues).
- Retention timeline: dead-air jump cuts; adaptive length scored against engagement-weighted example lengths
  per content type (gta6 hard limits widened to 6–180 s).
- AI headlines follow the real headline style of the same content type.
- (Hype-edit engine added 2026-11-13, see below.)

## Added 2026-11-13
- **Trend research, free** (`research/trends.py`, `trends research|show`): TikTok creator embeds + public
  video pages (views, likes, shares, saves, sound, post time) and YouTube search (this week). Velocity
  (views/h), engagement, outlier vs creator median, type, topics, trending sounds, official events.
  New creators discovered from @mentions. No Gemini / vidIQ quota used.
- **Daily plan** (`research/planner.py`, `trends plan`): phase (pre-release / launch week / post-launch),
  allocation per type, series, angles, sounds, A/B variants, hook rule; saved in `memory/plans/`.
- **Quality gate**: `max_upscale` 2.0 — layouts that would enlarge the source too much switch to a sharper
  layout or are rejected (`sharp_enough` QC); `strong_hook` QC.
- **A/B variants** (variant B = alternative title + alternate layout), **durable memory** in `memory/`
  (`memory save|load`, loaded automatically on start).
- **Hype-edit engine** (`editing/hype_editor.py`, `python main.py hype make <videos...>`): shot detection
  (rejects text cards, logos, black/fades, soft shots), crop centred on faces/action, opener (cinematic,
  optional ≤0.6x interpolated slow motion) → first cut on the drop → one shot per beat starting on its
  motion peak, alternating look (brightness/hue), punch-in on every cut, white flashes on the kicks,
  countdown text from the release date, cut to black on the last beat. Cut on the measured beat grid of a
  reference edit whose TikTok sound is known (`hype templates`); output is silent and comes with music
  instructions (sound, start 0:00, BPM, drop second). Layout: 4:5 picture (1.34x from 1080p) with text
  only in the black bands. Output goes to `outputs/_PRIVATE_TEST/` (third-party trailer footage).
- **Automatic morning run**: a scheduled task (07:43 Europe/Belgrade) runs trends research + plan +
  memory save and reports the day's plan in the chat.

## Added 2026-11-13 (later): template edits — the machine copies viral edit structures by itself
- **Template learning** (`editing/template_edit.py`, `hype learn <TikTok URL|file>` / `hype learn-trending`):
  from the day's research the machine downloads the top hype edits, measures every cut frame-accurately, the look
  of each shot (brightness, colour, motion, faces), the sound's tempo (librosa), the fade-out and the orientation,
  and reads the on-screen text with one free Gemini call (rolling countdowns become `{days}+N -> {days}`).
  Saved in `config/hype_templates/*.json`.
- **Template rendering** (`hype render <id>` / `hype daily`): each slot gets the most similar shot from the official
  trailers (`assets/footage/gta6`, imported free via vidIQ), cut on the same frames as the reference, whip
  transitions, rolling counter / word-by-word lines with glow / letter scatter, fade-out. Cinematic black bars are
  cropped away (landscape) or avoided (vertical). Preview with the reference sound + silent upload copy. Shots used
  in the last 3 days are avoided (`memory/hype_used.json`). Lines copied from another creator are flagged
  CHECK TEXT. First learned templates: mfx.3dits countdown (owner's example), havoceeditz ×2, norage_ae.
- **Local Whisper works** (free): Hugging Face hosts allowed; model `small.en` downloaded; audio is decoded with
  ffmpeg (the faster-whisper PyAV decoder failed with this PyAV version).
- Morning scheduled task now runs the full production: research -> plan -> learn templates -> daily edits ->
  review -> send to the owner -> memory commit.

## Added 2026-11-14
- **Post kit** (`metadata/post_kit.py`): TikTok caption/hashtags/cover text/sound steps, YouTube Shorts title/
  description/tags/settings, X text and posting time — written next to every video as `<video>.post.txt`.
- **Shot tags** (`config/footage_tags/<set>/`): iconic score + UI flag for every trailer shot, one free Gemini call per
  footage file using a numbered grid of mid-frames (exact mapping); UI shots (social media, TV news, HUD, title
  cards) are never used; recently used shots are excluded when alternatives exist.
- **Meme maker** (`editing/meme_maker.py`, `meme add|daily|list`): clean reaction clips are extracted from reference
  memes (moving band = footage, still caption/bars dropped), described in `config/meme_clips/gta6.json`; daily
  captions are written by one free Gemini call per batch from trends + viral headline style; render = caption in
  the top bar + clip (max 2x upscale) + clip audio, 1080x1920, same file for TikTok and Shorts.
- **Niko Bellic edits**: GTA IV official trailers (`assets/footage/gta4`, 720p, imported free), templates with
  `footage: gta4`, square 1080x1080 output (1.5x) and GTA IV hashtags; shot cache keyed by folder + file name.
- 12 template edits/day, no channel tag on videos.
- **Every video goes to TikTok AND YouTube Shorts**: all outputs are 1080x1920; landscape/square template edits are
  rendered with bigger text and centred on a blurred copy (`to_vertical_video`, `hype.all_vertical: true`).
- YouTube channel guide `docs/YOUTUBE_SETUP.md` + banner `docs/brand/youtube_banner_2560x1440.jpg`.

## In progress
- Nothing partially implemented.

## Not started / out of scope by design
- Automatic publishing, social-account connections, cloud hosting, dashboards, third-party
  clipping services, scraping/downloader tools — excluded by requirements.
- Twitch discovery (needs Twitch API credentials — add only if you want it).

## Known limitations (honest)
1. **Gemini verified live (2026-11-03)**: plain/JSON calls work; `gemini-2.5-flash` is retired, so
   the default is `gemini-3.8-flash` with automatic fallbacks (`gemini-3.5-flash`, ...) because
   3.8 often returns 503 "high demand". **Google Search grounding returns 429 quota exceeded** on
   this key (free tier without billing) — grounded research/trends are recorded as `failed` until
   billing is enabled in Google AI Studio. Never replaced with ungrounded "research".
2. **Gemini transcription engine added and verified live** (fallback when the Whisper model can't
   be downloaded): accurate sentence segments, word timings estimated. **Local Whisper verified 2026-11-13**
   (`small.en`, free, ~32 s for a 2 min clip on CPU).
3. **Face tracking uses OpenCV's Haar frontal-face cascade**: misses profiles, tiny facecams and
   heavy lighting. Tested with mocked detections (synthetic test media has no faces). For streams
   with a facecam overlay, set `facecam_region` in the sidecar — it is far more reliable.
4. **No built-in speaker diarization**. Speaker labels come from sidecar transcripts; without them
   group chemistry relies on faces, dialogue patterns and lexicon.
5. **Laughter / reaction detection** is lexical + loudness-relative; there is no audio event model.
6. **Audio fingerprint** is a coarse loudness contour (good for near-identical re-uploads, not for
   re-encoded audio with different mixing).
7. **YouTube RSS discovery verified live**: all 19 configured handles resolved to channel IDs; first
   run indexed 90 videos from the 7-day window as metadata-only leads (PENDING_VERIFICATION).
   Leads list only the channel owner as participant; guests must be added before rights can pass.
8. **Speed**: rendering ≈ real-time for 1080×1920 at preset `medium` on 4 cores; visual analysis
   of a multi-hour VOD at 1 fps takes minutes. `start` runs in the foreground (use tmux/nohup).
9. Learning recommendations need ≥8 clips with retention data per profile; format verdicts need
   ≥20 per format.
10. Scores are heuristic estimates of potential, not predictions of views or retention.

## Bugs
- Fixed (2026-11-03, found on a 113 s synthetic stream): overlapping windows now compete by total
  score (a setup-only window no longer blocks the full story); clips end at the story wrap-up before
  the next topic change; lead-in no longer catches the previous sentence's last word.
- Fixed: peaks were processed in time order, letting a weak early peak claim the context window
  of a stronger moment (regression asserted in `test_lospollos_split_format_with_licensed_gameplay`).
- No known open bugs.

## Required configuration (by you)
- `.env`: `GEMINI_API_KEY` (optional but needed for AI research/semantic scoring/AI titles).
- Permission records with real evidence for each creator/participant/source (`rights add`).
- `third_party_content` per source (music/TV/videos on screen), otherwise clips go to review.
- LosPollosTV Formats A/C: your own or licensed GTA V gameplay in `assets/approved_gameplay/` +
  an APPROVED asset permission for each file.
- Optional: YouTube channel IDs in `config/<profile>.yaml`; fonts in `assets/fonts/`.

## Next development tasks
1. First live run with a real Gemini key and a real recording; tune `min_quality_threshold` per
   profile using `candidates` output.
2. Optional: YuNet/DNN face detector for better tracking (needs a bundled ONNX model).
3. Optional: diarization integration (e.g. a local pyannote step writing sidecar speakers).
4. Optional: Twitch Helix discovery adapter (metadata only), if wanted.
5. After 8+ clips per profile have performance data: `learning analyze`.
