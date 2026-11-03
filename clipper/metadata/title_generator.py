"""Truthful, engaging English titles.

Heuristic titles quote the actual transcript. Gemini titles (when enabled) are validated: any
quoted text must appear verbatim in the transcript and named people must be real participants
or mentioned in the clip; otherwise the heuristic title is used.
"""
from __future__ import annotations

import re

from ..detection.text_signals import LEXICON, count_terms

HOOK_LEADS = {
    "question": "{who} asks", "surprise": "{who} can't believe it", "argument": "{who} gets into it",
    "story": "{who} tells the story", "challenge": "{who} takes the challenge", "funny": "{who} loses it",
    "emotional": "{who} gets real", "statement": "{who}",
}


def _who(participants: list[str], group: str | None) -> str:
    if not participants:
        return group or "Streamer"
    if len(participants) == 1:
        return participants[0]
    if len(participants) == 2:
        return f"{participants[0]} & {participants[1]}"
    return group or f"{participants[0]} & crew"


def best_quote(segments_text: list[str], max_len: int = 60) -> str | None:
    best, best_s = None, 0.0
    for t in segments_text:
        t = t.strip().strip('"')
        n = len(t.split())
        if n < 3 or len(t) > max_len:
            continue
        s = sum(count_terms(t, LEXICON[k]) for k in ("hook", "surprise", "argument", "challenge", "laughter")) \
            + t.count("!") * 0.5 + t.count("?") * 0.5 + (0.5 if 4 <= n <= 10 else 0)
        if s > best_s:
            best, best_s = t, s
    return best


def heuristic_title(segments_text: list[str], participants: list[str], hook_type: str,
                    group: str | None, max_chars: int = 90) -> str:
    who = _who(participants, group)
    quote = best_quote(segments_text, max_len=max_chars - len(who) - 6)
    if quote:
        title = f'{who}: "{quote.rstrip(".")}"'
    else:
        title = HOOK_LEADS.get(hook_type, "{who}").format(who=who)
    return title[:max_chars].rstrip()


def validate_ai_title(title: str, transcript: str, allowed_names: list[str], max_chars: int,
                      people: list[str] | None = None) -> bool:
    """Accept an AI title only if it fits, every quote is verbatim from the transcript, and every
    person it names (as reported by the model) is a known creator/participant or is named in the clip."""
    if not title or len(title) > max_chars:
        return False
    norm = re.sub(r"\s+", " ", transcript.lower())
    for q in re.findall(r'"([^"]+)"', title):
        if re.sub(r"\s+", " ", q.lower().strip(" .!?")) not in norm:
            return False
    known = {w.lower() for n in allowed_names for w in n.split()}
    for person in people or []:
        words = [w for w in re.findall(r"[a-z0-9]+", person.lower()) if len(w) > 1]
        if words and not all(w in known or w in norm for w in words):
            return False
    return True
