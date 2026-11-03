"""Content QC: does the clip make sense on its own, and do captions match the speech?"""
from __future__ import annotations

from ..detection.text_signals import ends_sentence, starts_dangling
from ..models import Transcript
from .technical_checks import CheckReport


def content_checks(*, transcript: Transcript, start: float, end: float, scores: dict, cfg: dict,
                   caption_report, ai_analysis: dict | None) -> CheckReport:
    rep = CheckReport()
    segs = transcript.window(start, end)
    words = transcript.words_in(start, end)
    dur = max(1e-6, end - start)
    ctx = float(scores.get("context_completeness", 0))
    rep.add("context_sufficient", ctx >= cfg.get("min_context_score", 5.0), f"context score {ctx:.1f}", "review")
    speech = sum(w.end - w.start for w in words) / dur
    rep.add("meaningful_content", speech >= cfg.get("min_speech_coverage", 0.35) and len(words) >= 12,
            f"speech coverage {speech:.0%}, {len(words)} words", "review")
    if segs:
        hook_ok = not starts_dangling(segs[0].text)
        rep.add("hook_understandable", hook_ok, f"opens with: {segs[0].text[:60]!r}", "review")
        if cfg.get("require_sentence_boundaries", True):
            rep.add("natural_ending", ends_sentence(segs[-1].text), f"ends with: {segs[-1].text[-60:]!r}", "review")
        cut = [w for w in transcript.words if w.start < start - 0.05 < w.end or w.start < end - 0.05 < w.end - 0.05]
        rep.add("no_missing_dialogue_at_edges", not cut, f"{len(cut)} words cut at clip edges", "review")
    else:
        rep.add("meaningful_content", False, "no speech in clip", "review")
    if caption_report is not None:
        rep.add("captions_match_speech", caption_report.words == len([w for w in words if w.text.strip()]),
                f"{caption_report.words} caption words vs {len(words)} transcript words")
        frac = caption_report.low_confidence_fraction
        rep.add("transcription_confidence", frac <= cfg.get("max_low_confidence_fraction", 0.15),
                f"{frac:.0%} low-confidence words (shown verbatim, never invented)", "review")
    if transcript.word_timing == "estimated":
        rep.add("word_timing_native", False, "word timings estimated from segment timings", "warn")
    if ai_analysis and ai_analysis.get("self_contained") is False:
        rep.add("ai_self_contained", False, "Gemini judged the clip not self-contained: "
                + "; ".join(ai_analysis.get("concerns") or [])[:200], "review")
    return rep
