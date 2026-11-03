"""Builds the full metadata record for a clip."""
from __future__ import annotations

from typing import Any

from ..config import Settings
from ..core.logger import get_logger
from ..detection.text_signals import count_terms
from .description_generator import description, fmt_ts
from .hashtag_generator import hashtags
from .title_generator import heuristic_title, validate_ai_title

log = get_logger("metadata")


def build_metadata(settings: Settings, *, source: dict, candidate: dict, participants: list[str],
                   segments_text: list[str], start: float, end: float, attribution: list[str],
                   trend_terms: set[str], gemini=None, title: str | None = None) -> dict[str, Any]:
    prof = settings.profile(source["profile"])
    max_chars = int(prof.metadata.get("title_max_chars", 90))
    transcript = " ".join(segments_text)
    fixed_title = title
    title = fixed_title or heuristic_title(segments_text, participants, candidate.get("hook_type") or "statement",
                                           prof.group_name, max_chars)
    title_source = "fixed" if fixed_title else "heuristic"
    ai = candidate.get("ai_analysis") or {}
    summary = (ai.get("summary") if isinstance(ai, dict) else None) or candidate.get("summary") or ""
    if gemini is not None and gemini.available() and not fixed_title:
        try:
            res = gemini.generate_json(
                "Write ONE short, punchy on-screen title for a vertical short clip, in the style clip channels "
                "use (e.g. 'Kai Cenat Gets Roasted By His Own Chat'): 3-9 words, max 50 characters, starts with "
                "who it is about, says what happens, makes people want to watch. Strictly truthful: use ONLY "
                "facts in this transcript, no clickbait implying something that did not happen; any quote must "
                "be verbatim. List every person the title names in people_mentioned. "
                "IMPORTANT: the transcript has several speakers and is NOT labelled by speaker. Only say a "
                "named person did or said something if the transcript makes it unambiguous; otherwise "
                "describe the situation (e.g. 'Kai Cenat's TikTok Guest Claims...'). Guests and other "
                "speakers are not the creator. "
                f"People in the clip: {', '.join(participants) or 'unknown'}.\nTranscript:\n{transcript[:4000]}",
                {"type": "object", "properties": {"title": {"type": "string"},
                                                 "people_mentioned": {"type": "array", "items": {"type": "string"}}},
                 "required": ["title", "people_mentioned"]})
            cand = str((res or {}).get("title", "")).strip()
            people = [str(x) for x in (res or {}).get("people_mentioned", [])]
            if validate_ai_title(cand, transcript, participants + [c.name for c in prof.creators], max_chars, people):
                title, title_source = cand, f"gemini:{settings.global_.google_ai.model}"
            else:
                log.info("AI title rejected by truthfulness validator: %r", cand)
        except Exception as e:
            log.warning("AI title failed, using heuristic: %s", e)
    spoken_trends = [t for t in trend_terms if count_terms(transcript, [t])]
    tags = hashtags(prof, participants, candidate.get("category") or "", spoken_trends)
    desc = description(summary, source, start, end, attribution, tags)
    return {
        "title": title, "title_source": title_source, "description": desc, "hashtags": tags,
        "summary": summary, "creators": participants, "profile": prof.display_name,
        "source": {"id": source["id"], "title": source.get("title"), "url": source.get("url"),
                   "published_at": source.get("published_at")},
        "original_timestamp": {"start": round(start, 2), "end": round(end, 2),
                               "start_hms": fmt_ts(start), "end_hms": fmt_ts(end)},
        "duration": round(end - start, 2), "hook_type": candidate.get("hook_type"),
        "category": candidate.get("category"), "attribution": attribution,
    }
