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
   be downloaded): accurate sentence segments, word timings estimated. **Whisper model not exercised here**: Hugging Face was unreachable in the sandbox, so the
   faster-whisper path is untested end-to-end; the sidecar transcript path is fully tested. On your
   machine the model downloads on first use (or set `WHISPER_MODEL_PATH`).
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
