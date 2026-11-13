"""Unit tests for transcripts, detection, captions, analytics, learning and config changes."""
import csv
import json
import random

import numpy as np
import pytest
import yaml

from clipper.analytics.analytics_engine import overview
from clipper.analytics.format_comparison import compare_formats
from clipper.analytics.learning_engine import LearningEngine
from clipper.analytics.performance_import import import_csv
from clipper.cli import main as cli_main
from clipper.config import load_settings
from clipper.core.logger import redact
from clipper.core.retry import TransientError, retry_call
from clipper.detection.audio_analyzer import analyze_samples, envelope_fingerprint, fingerprint_similarity
from clipper.detection.context_analyzer import ContextParams, find_window
from clipper.detection.text_signals import starts_dangling
from clipper.editing.caption_engine import build_ass, chunk_words
from clipper.editing.layout_engine import LayoutPlan, compose, zoom_at
from clipper.metadata.title_generator import heuristic_title, validate_ai_title
from clipper.models import Transcript, Word
from clipper.research.google_ai import GeminiClient, extract_json
from clipper.research.source_discovery import YouTubeRSSDiscovery, SourceStore
from clipper.transcription.transcription_engine import parse_json_transcript, parse_srt_vtt

from conftest import SCRIPT


def _transcript():
    segs, _ = parse_json_transcript({"segments": [
        {"start": s, "end": e, "text": t, "speaker": spk} for s, e, spk, t in SCRIPT]})
    return Transcript("src", "test", "en", segs, "estimated")


def test_srt_parsing_with_speakers():
    srt = "1\n00:00:01,000 --> 00:00:03,500\nA: Hello chat what is up\n\n2\n00:00:04,000 --> 00:00:06,000\n<v Bob>No way bro!\n"
    segs = parse_srt_vtt(srt)
    assert [s.speaker for s in segs] == ["A", "Bob"]
    assert segs[1].text == "No way bro!" and segs[1].words[0].start == pytest.approx(4.0)


def test_context_window_keeps_setup_and_payoff():
    tr = _transcript()
    win = find_window(tr, 37.0, None, ContextParams(), 82)
    assert win.start < 6.5 and win.end >= 47
    assert win.starts_clean


def test_context_window_respects_max_duration():
    tr = _transcript()
    win = find_window(tr, 37.0, None, ContextParams(min_duration=15, max_duration=25), 82)
    assert win is not None and win.duration <= 25 and win.start <= 37 <= win.end


def test_dangling_start_detection():
    assert starts_dangling("And then he left") and not starts_dangling("Bro listen")


def test_audio_features_and_fingerprint():
    sr = 16000
    x = np.random.default_rng(0).normal(0, 0.01, sr * 20).astype(np.float32)
    x[sr * 10: sr * 12] *= 20
    f = analyze_samples(x, sr)
    assert f.peak_z(9, 13) > 3 and f.peak_z(0, 5) < 3
    fp = envelope_fingerprint(f, 0, 20)
    assert fingerprint_similarity(fp, fp) > 0.99


def test_caption_chunks_and_ass(tmp_path, settings):
    words = [Word(i * 0.4, i * 0.4 + 0.35, w, 0.9 if i != 3 else 0.2) for i, w in enumerate(
        "No way bro what did you do!".split())]
    chunks = chunk_words(words, 3, 22)
    assert all(len(c) <= 3 for c in chunks)
    rep = build_ass(words, 0, 3, settings.profile("amp").editing.caption, width=1080, height=1920, y_fraction=0.66,
                    safe=settings.editing.safe_zones, low_conf=0.55, out_path=tmp_path / "c.ass")
    txt = (tmp_path / "c.ass").read_text()
    assert "PlayResY: 1920" in txt and "WAY" in txt and rep.low_confidence_words == 1
    assert rep.words == len(words)        # captions = transcript words, nothing invented


def test_layouts_produce_vertical_frames():
    frame = np.random.default_rng(0).integers(0, 255, (720, 1280, 3), dtype=np.uint8)
    gp = np.zeros((1080, 1920, 3), np.uint8)
    for name in ("focus", "fit_blur", "split_gta", "hybrid"):
        plan = LayoutPlan(name, streamer_fraction=0.66 if name == "hybrid" else 0.5, needs_gameplay=name in ("split_gta", "hybrid"))
        out = compose(frame, plan, 0.0, gp if plan.needs_gameplay else None)
        assert out.shape == (1920, 1080, 3)
    with pytest.raises(RuntimeError):
        compose(frame, LayoutPlan("split_gta", needs_gameplay=True), 0.0, None)
    p = LayoutPlan("focus", zoom_times=[2.0], zoom_cfg={"enabled": True, "base": 1.0, "emphasis": 1.12})
    assert zoom_at(p, 2.0) == pytest.approx(1.12) and zoom_at(p, 10.0) == 1.0


def test_titles_are_truthful():
    segs = [s[3] for s in SCRIPT[:12]]
    t = heuristic_title(segs, ["Kai Cenat"], "surprise", "AMP")
    quote = t.split('"')[1]
    assert quote.lower() in " ".join(segs).lower()
    assert not validate_ai_title('Kai Cenat: "he stole my car"', " ".join(segs), ["Kai Cenat"], 90)
    assert validate_ai_title('Kai Cenat: "No way bro"', " ".join(segs), ["Kai Cenat"], 90)
    assert not validate_ai_title("Kai Cenat and Drake race in the store", " ".join(segs), ["Kai Cenat"], 90,
                                 people=["Kai Cenat", "Drake"])
    assert validate_ai_title("Kai Cenat Gets Destroyed In A Store Race", " ".join(segs), ["Kai Cenat"], 90,
                             people=["Kai Cenat"])


def test_extract_json_and_redaction(monkeypatch):
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"items": []} done') == {"items": []}
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTESTKEY1234567890abcdef")
    assert "AIza" not in redact("key=AIzaSyTESTKEY1234567890abcdef and api_key: secretvalue")


def test_gemini_unavailable_without_key(settings, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert not GeminiClient(settings.global_.google_ai).available()


def test_gemini_research_with_fake_client(settings, db):
    """Grounded research results are stored as unverified leads with citations; nothing is downloaded."""
    from types import SimpleNamespace as NS
    from clipper.research.research_engine import ResearchEngine
    from clipper.rights.permission_registry import PermissionRegistry
    from clipper.rights.rights_gate import RightsGate
    payload = {"items": [{"title": "Kai stream", "url": "https://example.com/v/1", "published_at": None,
                          "participants": ["Fanum"], "summary": "s", "notable_moments": []},
                         {"title": "bad", "url": "not-a-url"}]}
    resp = NS(text=json.dumps(payload), candidates=[NS(grounding_metadata=NS(
        grounding_chunks=[NS(web=NS(uri="https://example.com/v/1", title="ex", domain="example.com"))],
        web_search_queries=["kai cenat stream"]))])
    fake = NS(models=NS(generate_content=lambda **kw: resp))
    g = GeminiClient(settings.global_.google_ai, client=fake)
    eng = ResearchEngine(db, settings, g, RightsGate(PermissionRegistry(db), settings), rss_fetch=lambda u: b"")
    out = eng.research_profile("amp", use_gemini=True)
    kinds = {r["kind"]: r for r in out["results"]}
    assert kinds["gemini_leads"]["status"] == "ok"
    leads = db.query("SELECT * FROM sources WHERE kind='research_lead'")
    assert len(leads) == 1 and leads[0]["rights_status"] == "PENDING_VERIFICATION" and leads[0]["local_path"] is None
    assert db.one("SELECT count(*) n FROM research_notes WHERE citations LIKE '%example.com%'")["n"] >= 1


def test_gemini_failure_is_recorded_not_faked(settings, db):
    from types import SimpleNamespace as NS
    from clipper.research.research_engine import ResearchEngine
    def boom(**kw):
        raise RuntimeError("503 unavailable")
    g = GeminiClient(settings.global_.google_ai.model_copy(update={"max_retries": 1}), client=NS(models=NS(generate_content=boom)))
    eng = ResearchEngine(db, settings, g, None, rss_fetch=lambda u: b"")
    out = eng.research_profile("core", use_gemini=True)
    assert any(r["status"] == "failed" for r in out["results"])
    assert db.one("SELECT status FROM research_runs WHERE kind='gemini_leads'")["status"] == "failed"


def test_retry_backoff():
    calls = []
    def f():
        calls.append(1)
        if len(calls) < 3:
            raise TransientError("x")
        return "ok"
    assert retry_call(f, attempts=3, backoff=0, sleep=lambda s: None) == "ok" and len(calls) == 3


def test_rss_parse_and_window(settings, db):
    xml = b"""<feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
    <entry><yt:videoId>abc</yt:videoId><title>New stream</title><link href="https://www.youtube.com/watch?v=abc"/>
    <published>2099-01-01T00:00:00+00:00</published><author><name>Kai</name></author></entry>
    <entry><yt:videoId>old</yt:videoId><title>Old</title><link href="https://www.youtube.com/watch?v=old"/>
    <published>2001-01-01T00:00:00+00:00</published></entry></feed>"""
    store = SourceStore(db, settings)
    settings.profile("amp").creators[0].youtube_channel_ids.append("UC" + "a" * 22)
    created = YouTubeRSSDiscovery(store, settings, fetch=lambda u: xml).scan("amp")
    assert len(created) == 1 and store.get(created[0])["kind"] == "research_lead"


def _perf_csv(path, rows):
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def test_csv_import_keeps_missing_values_empty(tmp_path, settings, db):
    p = tmp_path / "perf.csv"
    _perf_csv(p, [{"profile": "amp", "platform": "youtube", "views": "1,200", "avg_pct_viewed": "62%",
                   "shares": "", "video_length": "34", "format": "", "hook_type": "surprise"},
                  {"profile": "amp", "platform": "tiktok", "views": "-5", "avg_pct_viewed": "", "shares": "",
                   "video_length": "20", "format": "", "hook_type": ""}])
    res = import_csv(db, settings, p)
    assert res["inserted"] == 1 and len(res["errors"]) == 1
    r = db.one("SELECT * FROM performance")
    assert r["views"] == 1200 and r["avg_pct_viewed"] == 62 and r["shares"] is None and r["completion_rate"] is None
    assert overview(db, "amp")["clips_with_data"] == 1
    assert overview(db, "core")["clips_with_data"] == 0          # profiles stay independent


def test_format_comparison_needs_evidence(tmp_path, settings, db):
    rng = random.Random(3)
    rows = []
    for f, base in (("A", 55), ("B", 45), ("C", 50)):
        for _ in range(8):
            rows.append({"profile": "lospollostv", "views": "1000", "avg_pct_viewed": str(base + rng.uniform(-3, 3)),
                         "video_length": str(rng.uniform(20, 60)), "format": f})
    p = tmp_path / "f.csv"; _perf_csv(p, rows); import_csv(db, settings, p)
    assert compare_formats(db, settings)["verdict"]["status"] == "insufficient_data"
    rows2 = [dict(r) for r in rows for _ in range(2)]
    for r in rows2:
        r["avg_pct_viewed"] = str(float(r["avg_pct_viewed"]) + rng.uniform(-1, 1))
    _perf_csv(p, rows2); import_csv(db, settings, p)        # now 24 per format
    res = compare_formats(db, settings)
    assert res["verdict"]["status"] == "recommend" and res["verdict"]["format"] == "A"
    assert db.one("SELECT count(*) n FROM recommendations WHERE kind='format_choice'")["n"] == 1


def test_learning_apply_is_recorded(project, db):
    settings = load_settings(project)
    db.insert("recommendations", {"profile": "amp", "kind": "scoring_weight", "description": "test",
                                  "proposed_change": json.dumps({"path": ["profiles", "amp", "scoring_weights", "hook_strength"],
                                                                 "value": 1.5}), "status": "pending", "created_at": "x"})
    le = LearningEngine(db, settings)
    rid = le.list("amp", "pending")[0]["id"]
    le.apply(rid)
    assert load_settings(project).profile("amp").scoring_weights["hook_strength"] == 1.5
    assert db.one("SELECT * FROM config_changes")["origin"] == "learning"
    assert le.analyze("amp")[0]["info"].startswith("only 0")


def test_cli_threshold_and_duration_changes(project, monkeypatch, capsys):
    monkeypatch.setenv("CLIPPER_ROOT", str(project))
    assert cli_main(["set-threshold", "core", "70", "--reason", "test"]) == 0
    assert cli_main(["set-duration", "amp", "--min", "20", "--max", "150"]) == 0
    s = load_settings(project)
    assert s.profile("core").min_quality_threshold == 70
    assert (s.profile("amp").duration.min_seconds, s.profile("amp").duration.max_seconds) == (20, 150)
    assert cli_main(["set-duration", "amp", "--max", "5"]) == 1          # invalid -> reverted
    assert load_settings(project).profile("amp").duration.max_seconds == 150
    assert cli_main(["status"]) == 0
    out = capsys.readouterr().out
    assert "CORE Clipper" in out and "threshold=70.0" in out


def test_face_tracker_smooths_and_holds_through_misses(monkeypatch):
    from clipper.editing import face_tracker
    frames = [np.zeros((360, 640, 3), np.uint8) for _ in range(12)]
    # face at x≈0.25, missing for two samples, then jitter of ±2px, then the speaker moves to x≈0.7
    dets = [[(150, 100, 60, 60)]] * 4 + [[]] * 2 + [[(152, 100, 60, 60)], [(148, 100, 60, 60)]] + [[(430, 100, 60, 60)]] * 4
    it = iter(dets)
    monkeypatch.setattr(face_tracker, "read_frames", lambda *a, **k: iter(frames))
    monkeypatch.setattr(face_tracker, "detect_faces", lambda img, ms: next(it))
    cam = face_tracker.track("x.mp4", 0, 3, sample_fps=4, smoothing=0.5, dead_zone=0.05)
    assert cam.face_found == pytest.approx(10 / 12)
    assert abs(cam.cx[5] - cam.cx[3]) < 1e-6          # held during misses
    assert abs(cam.cx[7] - cam.cx[6]) < 1e-6          # jitter inside dead zone ignored
    assert cam.cx[-1] > cam.cx[7] and cam.cx[-1] < 0.75  # moves toward new position smoothly, no jump


def test_youtube_handle_resolution_and_config(settings, db):
    assert "@KaiCenatLive" in settings.profile("amp").creator("Kai Cenat").youtube_handles
    assert settings.profile("core").group_youtube_handles == ["@createownruneverything"]
    store = SourceStore(db, settings)
    html = b'<html>..."externalId":"UCabcdefghijklmnopqrstuv"...</html>'
    calls = []
    d = YouTubeRSSDiscovery(store, settings, fetch=lambda u: calls.append(u) or html)
    assert d.resolve_handle("@KaiCenatLive") == "UCabcdefghijklmnopqrstuv"
    assert d.resolve_handle("@KaiCenatLive") == "UCabcdefghijklmnopqrstuv" and len(calls) == 1   # cached
