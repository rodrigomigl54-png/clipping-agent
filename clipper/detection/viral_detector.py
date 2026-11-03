"""Viral moment detection and candidate scoring.

Signals combined: transcript semantics (hooks, surprise, laughter, arguments, stories, challenges),
audio arousal relative to the local baseline, scene changes / motion, faces, speaker turns,
current trend terms, and (optionally) Gemini semantic analysis of the transcript window.
Loudness alone never makes a candidate: a quiet but surprising statement scores through its text.

Scores are AI-estimated potential (0–10 per component, 0–100 total), not predictions of views.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..config import ProfileCfg, Settings
from ..core.logger import get_logger
from ..models import SCORE_KEYS, CandidateMoment, Transcript
from .audio_analyzer import AudioFeatures
from .context_analyzer import ContextParams, context_completeness, find_window
from .text_signals import ends_sentence, starts_dangling, text_signals
from .visual_analyzer import VisualFeatures

log = get_logger("detector")


def _sat(x: float, k: float) -> float:
    """Saturating map of a non-negative quantity to 0..10."""
    return 10.0 * (1 - math.exp(-max(0.0, x) / k))


def _clamp(x: float) -> float:
    return float(max(0.0, min(10.0, x)))


@dataclass
class DetectionInputs:
    source: dict
    transcript: Transcript
    audio: AudioFeatures | None
    visual: VisualFeatures | None
    media_duration: float
    trend_terms: set[str]
    exported_texts: list[str]          # for originality estimate (full check in duplicate detector)


class ViralDetector:
    def __init__(self, settings: Settings, gemini=None):
        self.settings = settings
        self.gemini = gemini

    # ---------------------------------------------------------------- interest curve
    def interest_curve(self, inp: DetectionInputs, prof: ProfileCfg) -> np.ndarray:
        n = max(1, int(math.ceil(inp.media_duration)))
        curve = np.zeros(n, np.float64)
        for s in inp.transcript.segments:
            sig = text_signals(s.text, inp.trend_terms)
            c = sig.counts
            lex = (1.4 * c["surprise"] + 1.6 * c["laughter"] + 1.0 * c["hook"] + 1.2 * c["argument"]
                   + 0.8 * c["emotion"] + 1.0 * c["challenge"] + 0.8 * c["confusion"] + 0.6 * c["roast"]
                   + 0.5 * sig.exclamations + 0.4 * sig.questions + 2.0 * sig.caps_ratio + 0.8 * sig.trend_hits)
            a, b = int(s.start), max(int(s.start) + 1, int(math.ceil(s.end)))
            curve[a:min(b, n)] += lex / max(1.0, (b - a) ** 0.5)
        if inp.audio is not None:
            for t in range(n):
                curve[t] += 0.35 * max(0.0, inp.audio.peak_z(t, t + 1))
        if inp.visual is not None and inp.visual.scene.size:
            for t in range(n):
                curve[t] += 1.5 * inp.visual.stat("scene", t, t + 1, np.max) + 4 * inp.visual.stat("motion", t, t + 1)
        # speaker turns (only when the transcript has speaker labels)
        segs = inp.transcript.segments
        for i in range(1, len(segs)):
            if segs[i].speaker and segs[i - 1].speaker and segs[i].speaker != segs[i - 1].speaker:
                t = int(segs[i].start)
                if t < n:
                    curve[t] += 0.6
        k = np.ones(5) / 5
        return np.convolve(curve, k, mode="same")

    @staticmethod
    def pick_peaks(curve: np.ndarray, k: int, min_sep: int = 12) -> list[int]:
        order = np.argsort(-curve)
        chosen: list[int] = []
        thr = float(np.percentile(curve, 75)) if curve.size > 4 else 0.0
        for idx in order:
            if curve[idx] <= max(thr, 1e-6):
                break
            if all(abs(int(idx) - c) >= min_sep for c in chosen):
                chosen.append(int(idx))
            if len(chosen) >= k:
                break
        return chosen   # strongest first: the best moment claims its context window first

    # ---------------------------------------------------------------- scoring
    def score_window(self, inp: DetectionInputs, prof: ProfileCfg, start: float, end: float, peak: float,
                     win=None, params: ContextParams | None = None) -> tuple[dict[str, float], dict[str, Any], str, str]:
        tr = inp.transcript
        segs = tr.window(start, end)
        text = " ".join(s.text for s in segs)
        aliases = {c.name: c.aliases for c in prof.creators}
        sig = text_signals(text, inp.trend_terms, aliases)
        first = " ".join(s.text for s in segs if s.start < start + 4.0) or (segs[0].text if segs else "")
        fsig = text_signals(first)
        dur = end - start
        a = inp.audio
        v = inp.visual
        c = sig.counts

        peak_z = a.peak_z(start, end) if a else 0.0
        early_z = a.mean_z(start, start + 3) if a else 0.0
        speech_words = tr.words_in(start, end)
        speech_time = sum(w.end - w.start for w in speech_words)
        coverage = min(1.0, speech_time / max(dur, 1e-6))
        speakers = {s.speaker for s in segs if s.speaker}
        turns = sum(1 for i in range(1, len(segs)) if segs[i].speaker and segs[i].speaker != segs[i - 1].speaker)
        faces_mean = v.stat("faces", start, end) if v else 0.0
        multi_face = v.stat("faces", start, end, lambda x: float(np.mean(x >= 2))) if v else 0.0

        s: dict[str, float] = {}
        s["hook_strength"] = _clamp(
            _sat(fsig.counts["hook"] + 1.3 * fsig.counts["surprise"] + 0.8 * fsig.questions + 0.5 * fsig.exclamations
                 + 1.2 * fsig.counts["challenge"] + fsig.counts["confusion"], 2.0) * 0.8
            + 1.5 * max(0.0, min(2.0, early_z)) - (2.0 if starts_dangling(first) else 0.0))
        s["entertainment"] = _clamp(_sat(sig.density("laughter") * 1.5 + sig.density("surprise")
                                         + sig.density("argument") + sig.density("roast") + sig.density("challenge"), 6.0))
        s["emotional_impact"] = _clamp(0.55 * _sat(peak_z, 3.0) + 0.45 * _sat(
            sig.density("emotion") * 2 + sig.exclamations * 100 / max(20, sig.words) + sig.caps_ratio * 20, 6.0))
        params = params or ContextParams()
        s["context_completeness"] = context_completeness(win, tr, params) if win is not None else _clamp(
            (3 if not starts_dangling(first) else 0) + (3 if segs and ends_sentence(segs[-1].text) else 0) + 2)
        story_build = 0.0
        if a is not None and dur > 10:
            pre = a.mean_z(start, start + (peak - start) / 2) if peak > start + 1 else 0
            near = a.mean_z(max(start, peak - 3), peak + 1)
            story_build = max(0.0, near - pre)
        s["story_progression"] = _clamp(_sat(c["story"] * 2 + story_build + (1 if dur >= 30 else 0)
                                             + 0.3 * max(0, len(segs) - 3), 3.0))
        tail_txt = " ".join(x.text for x in segs if x.start >= peak - 1)
        tsig = text_signals(tail_txt)
        rel_pos = (peak - start) / max(dur, 1e-6)
        pos_bonus = 2.0 if 0.35 <= rel_pos <= 0.92 else 0.5
        s["payoff_strength"] = _clamp(pos_bonus + 0.6 * _sat(tsig.counts["laughter"] * 1.5 + tsig.counts["surprise"]
                                                             + tsig.exclamations * 0.5 + max(0.0, peak_z - 1), 2.5) * 1.3)
        s["originality"] = 7.0  # refined against the export registry by the duplicate detector
        if inp.exported_texts:
            from .text_signals import containment, shingles
            mine = shingles(text)
            sim = max((containment(mine, shingles(t)) for t in inp.exported_texts), default=0.0)
            s["originality"] = _clamp(10 * (1 - sim))
        quotable = any(4 <= len(x.text.split()) <= 14 and ("!" in x.text or "?" in x.text) for x in segs)
        s["shareability"] = _clamp(0.5 * s["entertainment"] + 0.3 * s["hook_strength"]
                                   + (1.5 if quotable else 0) + min(2.0, sig.trend_hits * 0.7))
        if v is not None and v.sharpness.size:
            sharp = v.stat("sharpness", start, end)
            bright = v.stat("brightness", start, end)
            s["visual_quality"] = _clamp(_sat(math.log1p(sharp), 4.0) * 0.6
                                         + (3 if 0.12 < bright < 0.9 else 0) + min(1.0, faces_mean))
        else:
            s["visual_quality"] = 5.0
        if a is not None:
            snr = a.snr_db()
            s["audio_quality"] = _clamp(_sat(snr, 15) * 0.8 + 2 * coverage - 30 * a.clipped_fraction)
        else:
            s["audio_quality"] = 5.0
        lo, hi = prof.duration.min_seconds, prof.duration.max_seconds
        in_range = lo <= dur <= hi
        s["platform_suitability"] = _clamp((4 if in_range else 0) + 4 * min(1.0, coverage / 0.6)
                                           + (2 if dur <= 60 else 1 if dur <= 120 else 0.5))
        chem_raw = (min(3, len(speakers)) * 0.8 + min(6, turns) * 0.4 + 2 * multi_face
                    + sig.density("argument") * 0.5 + sig.density("roast") * 0.6 + sig.density("challenge") * 0.4
                    + sig.density("laughter") * 0.3 + sig.density("confusion") * 0.3 + 0.5 * len(sig.mentions))
        s["group_chemistry"] = _clamp(_sat(chem_raw, 4.0)) if prof.feature("group_chemistry") else 0.0

        hook_type = self.hook_type(fsig, sig)
        category = self.category(prof, inp.source, len(speakers), multi_face, sig)
        signals = {"peak_z": round(peak_z, 2), "speech_coverage": round(coverage, 3), "speakers": len(speakers),
                   "speaker_turns": turns, "faces_mean": round(faces_mean, 2), "multi_face": round(multi_face, 2),
                   "lexicon": c, "trend_hits": sig.trend_hits, "mentions": sig.mentions,
                   "rel_peak_position": round(rel_pos, 2)}
        return {k: round(s[k], 2) for k in SCORE_KEYS}, signals, hook_type, category

    @staticmethod
    def hook_type(first, whole) -> str:
        c = whole.counts
        options = {
            "question": first.questions * 2 + first.counts["confusion"],
            "surprise": first.counts["surprise"] * 2 + c["surprise"] * 0.5,
            "argument": c["argument"] + c["roast"],
            "story": c["story"] * 1.5,
            "challenge": c["challenge"] * 1.5,
            "funny": c["laughter"],
            "emotional": c["emotion"],
        }
        best = max(options, key=options.get)
        return best if options[best] > 0 else "statement"

    @staticmethod
    def category(prof: ProfileCfg, source: dict, n_speakers: int, multi_face: float, sig) -> str:
        if source.get("category") and source["category"] in prof.content_categories:
            return source["category"]
        group = n_speakers >= 3 or multi_face >= 0.5 or len(sig.mentions) >= 2
        duo = n_speakers == 2 or (0.2 <= multi_face < 0.5) or len(sig.mentions) == 1
        c = sig.counts
        cats = set(prof.content_categories)
        def first(*names):
            return next((n for n in names if n in cats), prof.content_categories[0] if prof.content_categories else "general")
        if c["challenge"] >= 2:
            return first("challenge", "AMP challenges", "gaming")
        if c["argument"] + c["roast"] >= 2:
            return first("argument_debate", "conversation", "funny_interaction", "conversation")
        if group:
            return first("full_group", "group_reaction", "unexpected_group_moment", "conversation")
        if duo:
            return first("duo_interaction", "conversation", "funny_interaction")
        if c["surprise"] + c["laughter"] >= 2:
            return first("reaction", "funny_moment", "individual_stream", "individual")
        return first("individual_stream", "individual", "just_chatting")

    @staticmethod
    def total(scores: dict[str, float], weights: dict[str, float]) -> float:
        num = sum(scores.get(k, 0) * weights.get(k, 1.0) for k in SCORE_KEYS if weights.get(k, 1.0) > 0)
        den = sum(weights.get(k, 1.0) for k in SCORE_KEYS if weights.get(k, 1.0) > 0)
        return round(10.0 * num / max(den, 1e-6), 2)

    # ---------------------------------------------------------------- main entry
    def detect(self, inp: DetectionInputs, prof: ProfileCfg, max_candidates: int) -> list[CandidateMoment]:
        params = ContextParams(min_duration=prof.duration.min_seconds, max_duration=prof.duration.max_seconds,
                               max_payoff=min(25.0, prof.duration.max_seconds / 3))
        curve = self.interest_curve(inp, prof)
        peaks = self.pick_peaks(curve, k=max_candidates * 2)
        scored: list[CandidateMoment] = []
        participants = [p for p in (inp.source.get("participants_list") or [])]
        windows = set()
        for pk in peaks:
            win = find_window(inp.transcript, float(pk) + 0.5, inp.audio, params, inp.media_duration)
            if win is None or (win.start, win.end) in windows:
                continue
            windows.add((win.start, win.end))
            scores, signals, hook, cat = self.score_window(inp, prof, win.start, win.end, win.peak, win, params)
            signals.update({"interest_peak": round(float(curve[pk]), 3), "context_notes": win.notes,
                            "setup_seconds": win.setup_seconds, "payoff_seconds": win.payoff_seconds})
            text = " ".join(s.text for s in inp.transcript.window(win.start, win.end))
            total = self.total(scores, prof.scoring_weights)
            scored.append(CandidateMoment(
                source_id=inp.source["id"], profile=prof.id, start=win.start, end=win.end, peak=win.peak,
                scores=scores, total_score=total, hook_type=hook, category=cat, transcript_text=text,
                summary=self.heuristic_summary(inp.transcript, win.start, win.end, win.peak),
                signals=signals, participants=participants))
        # non-maximum suppression by total score: overlapping windows compete, the best complete
        # moment (setup + payoff) wins rather than whichever peak happened to be loudest
        out: list[CandidateMoment] = []
        for cand in sorted(scored, key=lambda c: -c.total_score):
            if any(min(cand.end, o.end) - max(cand.start, o.start) > 0.4 * min(cand.duration, o.duration) for o in out):
                continue
            out.append(cand)
        out.sort(key=lambda c: -c.total_score)
        out = out[:max_candidates]
        if self.gemini is not None and self.settings.global_.google_ai.semantic_scoring and self.gemini.available():
            self.semantic_refine(inp, prof, out, params)
        return out

    @staticmethod
    def heuristic_summary(tr: Transcript, start: float, end: float, peak: float) -> str:
        segs = tr.window(start, end)
        if not segs:
            return ""
        near = min(segs, key=lambda s: abs((s.start + s.end) / 2 - peak))
        quote = near.text.strip()
        if len(quote) > 140:
            quote = quote[:137].rsplit(" ", 1)[0] + "..."
        return f'Moment at {int(peak // 60)}:{int(peak % 60):02d} — "{quote}"'

    # ---------------------------------------------------------------- Gemini layer
    SEMANTIC_SCHEMA = {
        "type": "object",
        "properties": {
            "scores": {"type": "object", "properties": {k: {"type": "number"} for k in (
                "hook_strength", "entertainment", "emotional_impact", "context_completeness",
                "story_progression", "payoff_strength", "shareability", "group_chemistry")}},
            "self_contained": {"type": "boolean"},
            "hook_type": {"type": "string"},
            "summary": {"type": "string"},
            "suggested_start": {"type": "number"},
            "suggested_end": {"type": "number"},
            "concerns": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["scores", "self_contained", "summary"],
    }

    def semantic_refine(self, inp: DetectionInputs, prof: ProfileCfg, cands: list[CandidateMoment],
                        params: ContextParams) -> None:
        cfg = self.settings.global_.google_ai
        w = cfg.semantic_weight
        for cand in cands[: cfg.max_candidates_for_semantic]:
            ctx_s, ctx_e = max(0.0, cand.start - 30), min(inp.media_duration, cand.end + 20)
            lines = [f"[{s.start:.1f}-{s.end:.1f}]{' ' + s.speaker + ':' if s.speaker else ''} {s.text}"
                     for s in inp.transcript.window(ctx_s, ctx_e)]
            prompt = (
                "You evaluate stream transcripts for short-form vertical clips (YouTube Shorts / TikTok).\n"
                f"Profile: {prof.display_name}. Creators: {', '.join(c.name for c in prof.creators)}.\n"
                f"Proposed clip: {cand.start:.1f}s to {cand.end:.1f}s. Context lines are timestamped in seconds.\n"
                "Score each dimension 0-10 based ONLY on the transcript. Do not invent events, quotes or "
                "visuals that are not in the text. The summary must describe only what the transcript shows. "
                "If the clip would need more setup or a later ending to make sense, give suggested_start / "
                "suggested_end (seconds, within the context shown); otherwise repeat the proposed times.\n\n"
                + "\n".join(lines))
            try:
                res = self.gemini.generate_json(prompt, self.SEMANTIC_SCHEMA)
            except Exception as e:
                log.warning("semantic scoring failed for %s@%.0f: %s", cand.source_id, cand.start, e)
                cand.signals["semantic_error"] = str(e)[:300]
                continue
            if not isinstance(res, dict):
                continue
            ai_scores = res.get("scores") or {}
            for k, val in ai_scores.items():
                if k in cand.scores and isinstance(val, (int, float)):
                    cand.scores[k] = round((1 - w) * cand.scores[k] + w * _clamp(float(val)), 2)
            ss, se = res.get("suggested_start"), res.get("suggested_end")
            if isinstance(ss, (int, float)) and isinstance(se, (int, float)) and ctx_s <= ss < se <= ctx_e:
                if params.min_duration <= se - ss <= params.max_duration and ss <= cand.peak <= se:
                    segs = inp.transcript.window(ss, se)
                    if segs:  # snap AI suggestions to real speech boundaries
                        cand.start = round(max(0.0, segs[0].start - params.lead_in), 3)
                        cand.end = round(min(inp.media_duration, segs[-1].end + params.tail), 3)
                        cand.transcript_text = " ".join(s.text for s in segs)
                        if res.get("self_contained") is False:
                            res["self_contained"] = None   # its concern applied to the old boundaries
                            res.setdefault("concerns", []).append("boundaries adjusted to AI suggestion")
            if res.get("self_contained") is False:
                cand.scores["context_completeness"] = round(cand.scores["context_completeness"] * 0.7, 2)
            cand.ai_analysis = {"model": cfg.model, "summary": str(res.get("summary", ""))[:500],
                                "hook_type": res.get("hook_type"), "self_contained": res.get("self_contained"),
                                "concerns": res.get("concerns", []), "raw_scores": ai_scores}
            cand.total_score = self.total(cand.scores, prof.scoring_weights)
        cands.sort(key=lambda c: -c.total_score)
