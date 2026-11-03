"""Context analysis: find natural clip boundaries around a moment.

The analyzer looks at what happened before the moment (setup), what triggered the reaction, and
how the moment resolves (payoff), then snaps the clip to speech/sentence boundaries. It never
removes essential setup just to make a clip shorter, and never pads a weak moment.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Segment, Transcript
from .audio_analyzer import AudioFeatures
from .text_signals import LEXICON, count_terms, ends_sentence, jaccard, shingles, starts_dangling

OPENERS = ["let me tell you", "story time", "so basically", "you won't believe", "guess what",
           "listen to this", "one time", "remember when", "so yesterday", "so last night"]


def is_opener(text: str) -> bool:
    return count_terms(text, OPENERS) > 0


def is_reaction(text: str) -> bool:
    return count_terms(text, LEXICON["argument"] + LEXICON["laughter"] + LEXICON["surprise"] + LEXICON["roast"]) > 0


@dataclass
class ContextWindow:
    start: float
    end: float
    peak: float
    setup_seconds: float
    payoff_seconds: float
    starts_clean: bool
    ends_clean: bool
    notes: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class ContextParams:
    min_duration: float = 15.0
    max_duration: float = 180.0
    min_setup: float = 4.0
    max_setup: float = 60.0
    min_payoff: float = 3.0
    max_payoff: float = 25.0
    topic_pause: float = 2.5          # silence long enough to be a natural break
    reaction_calm_z: float = 0.6
    calm_seconds: float = 1.5
    lead_in: float = 0.15
    tail: float = 0.4


def _seg_index_at(segs: list[Segment], t: float) -> int:
    for i, s in enumerate(segs):
        if s.start <= t < s.end or t < s.start:
            return i
    return len(segs) - 1


def find_window(tr: Transcript, peak: float, audio: AudioFeatures | None, p: ContextParams,
                media_duration: float) -> ContextWindow | None:
    segs = tr.segments
    if not segs:
        return None
    pi = _seg_index_at(segs, peak)
    notes: list[str] = []

    # ---- setup: walk backwards until a natural topic boundary
    si = pi
    peak_ctx = shingles(" ".join(s.text for s in segs[max(0, pi - 1): pi + 2]), 1)
    while si > 0:
        prev, cur = segs[si - 1], segs[si]
        setup = peak - prev.start
        if setup > p.max_setup:
            break
        gap = cur.start - prev.end
        if setup >= p.min_setup:
            # a story/topic opener in the current segment is the natural start
            if is_opener(cur.text) and not starts_dangling(cur.text):
                break
            # stop at a long pause when the current segment starts cleanly
            if gap >= p.topic_pause and not starts_dangling(cur.text):
                break
            # stop at a topic change: a pause plus low lexical cohesion with the moment
            cohesion = jaccard(shingles(prev.text, 1), peak_ctx)
            if gap >= 1.0 and cohesion < 0.05 and ends_sentence(prev.text) and not starts_dangling(cur.text):
                break
        si -= 1
    # never start on a dangling reference if one more segment fixes it
    guard = 0
    while si > 0 and starts_dangling(segs[si].text) and peak - segs[si - 1].start <= p.max_setup and guard < 3:
        si -= 1
        guard += 1
    if starts_dangling(segs[si].text):
        notes.append("start may reference earlier context")

    # ---- payoff: walk forwards until the reaction subsides at a sentence end
    ei = pi
    while ei < len(segs) - 1:
        cur, nxt = segs[ei], segs[ei + 1]
        after = cur.end - peak
        if after >= p.max_payoff:
            break
        calm = True
        if audio is not None:
            a, b = cur.end, cur.end + p.calm_seconds
            calm = audio.mean_z(a, b) < p.reaction_calm_z
        gap = nxt.start - cur.end
        continues = gap < 1.0 and is_reaction(nxt.text)   # the exchange is still going
        if after >= p.min_payoff and ends_sentence(cur.text) and (calm or gap >= p.topic_pause) and not continues:
            break
        ei += 1

    start = max(0.0, segs[si].start - p.lead_in)
    end = segs[ei].end + p.tail
    # let a non-verbal reaction (laughter, screaming) finish after the last words
    if audio is not None:
        t = end
        limit = min(media_duration, end + 4.0)
        while t < limit and audio.mean_z(t, t + 0.5) >= p.reaction_calm_z and audio.silence_fraction(t, t + 0.5) < 0.8:
            t += 0.5
        end = t
    end = min(end, media_duration)

    # ---- adapt to duration limits (snap to segment boundaries)
    while end - start < p.min_duration and (si > 0 or ei < len(segs) - 1):
        grow_back = si > 0 and (peak - segs[si - 1].start <= p.max_setup or ei >= len(segs) - 1)
        if grow_back:
            si -= 1
            start = max(0.0, segs[si].start - p.lead_in)
        elif ei < len(segs) - 1:
            ei += 1
            end = min(media_duration, segs[ei].end + p.tail)
        else:
            break
    if end - start < p.min_duration:
        return None  # moment too short to stand alone; do not pad with silence
    while end - start > p.max_duration and si < pi:
        si += 1
        start = max(0.0, segs[si].start - p.lead_in)
    while end - start > p.max_duration and ei > pi:
        ei -= 1
        end = segs[ei].end + p.tail
    if end - start > p.max_duration:
        return None

    return ContextWindow(
        start=round(start, 3), end=round(end, 3), peak=peak,
        setup_seconds=round(peak - start, 2), payoff_seconds=round(end - peak, 2),
        starts_clean=not starts_dangling(segs[si].text),
        ends_clean=ends_sentence(segs[ei].text), notes=notes)


def context_completeness(win: ContextWindow, tr: Transcript, p: ContextParams) -> float:
    """0..10 score: does the clip make sense without the full stream?"""
    score = 0.0
    score += 3.0 if win.starts_clean else 0.5
    score += 2.0 if win.ends_clean else 0.5
    score += min(3.0, 3.0 * win.setup_seconds / max(p.min_setup * 2, 1))
    score += min(2.0, 2.0 * win.payoff_seconds / max(p.min_payoff * 2, 1))
    # penalise cutting through speech at the boundaries
    words = tr.words
    cut_in = any(w.start < win.start - 0.05 < w.end for w in words)
    cut_out = any(w.start < win.end - 0.05 < w.end - 0.1 for w in words)
    if cut_in:
        score -= 1.5
    if cut_out:
        score -= 1.5
    return max(0.0, min(10.0, score))
