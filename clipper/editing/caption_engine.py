"""English caption generation (ASS subtitles burned in with libass).

Captions use only the transcribed words — dialogue is never invented. Low-confidence words are
kept verbatim and reported so QC can route the clip to NEEDS_REVIEW.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..config import CaptionCfg
from ..detection.text_signals import LEXICON
from ..models import Word

_EMPHASIS = {w for k in ("hook", "surprise", "emotion", "argument", "challenge") for p in LEXICON[k]
             for w in p.split() if len(w) > 3} | {"no", "way", "what", "never", "insane", "crazy"}


@dataclass
class CaptionReport:
    chunks: int
    words: int
    low_confidence_words: int
    low_confidence_fraction: float
    first_time: float | None
    last_time: float | None


def _ass_color(hex_color: str, alpha: int = 0) -> str:
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def chunk_words(words: list[Word], max_words: int, max_chars: int, pause: float = 0.45) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur:
            text_len = sum(len(x.text) + 1 for x in cur) + len(w.text)
            gap = w.start - cur[-1].end
            sentence_end = bool(re.search(r"[.!?]$", cur[-1].text))
            if len(cur) >= max_words or text_len > max_chars or gap > pause or sentence_end:
                chunks.append(cur); cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def is_emphasis(word: str) -> bool:
    w = re.sub(r"[^a-z0-9']", "", word.lower())
    return w in _EMPHASIS or word.rstrip(",.").endswith("!") or (word.isupper() and len(word) > 2) or w.isdigit()


def build_ass(words: list[Word], clip_start: float, clip_end: float, style: CaptionCfg, *,
              width: int, height: int, y_fraction: float, safe: dict, low_conf: float,
              out_path: Path) -> CaptionReport:
    """Write an ASS file with times relative to ``clip_start``."""
    top = safe.get("top", 0.08); bottom = safe.get("bottom", 0.2); right = safe.get("right", 0.12)
    y_fraction = min(max(y_fraction, top + 0.06), 1 - bottom - 0.04)
    y = int(height * y_fraction)
    x = int(width * (1 - right) / 2 + width * 0.02)   # shift left of the platform action rail
    words = [w for w in words if w.end > clip_start and w.start < clip_end and w.text.strip()]
    chunks = chunk_words(words, style.max_words, style.max_chars)
    primary = _ass_color(style.primary_color)
    hi = _ass_color(style.highlight_color)
    font = style.font
    header = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Main,{font},{style.size},{primary},{primary},{_ass_color(style.outline_color)},"
        f"&H64000000,{-1 if style.bold else 0},0,0,0,100,100,0,0,1,{style.outline},{style.shadow},5,60,"
        f"{int(width * right)},0,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines = []
    low = 0
    for i, ch in enumerate(chunks):
        st = ch[0].start - clip_start
        en = ch[-1].end - clip_start
        nxt = chunks[i + 1][0].start - clip_start if i + 1 < len(chunks) else clip_end - clip_start
        en = min(max(en + 0.15, st + 0.35), nxt)   # readable minimum, never overlapping the next chunk
        parts = []
        for w in ch:
            if w.probability < low_conf:
                low += 1
            t = w.text.strip()
            t = t.upper() if style.uppercase else t
            t = _escape(t)
            parts.append(f"{{\\c{hi}}}{t}{{\\c{primary}}}" if is_emphasis(w.text) else t)
        lines.append(f"Dialogue: 0,{_ts(st)},{_ts(en)},Main,,0,0,0,,{{\\pos({x},{y})\\fad(40,40)}}" + " ".join(parts))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    nwords = sum(len(c) for c in chunks)
    return CaptionReport(len(chunks), nwords, low, low / nwords if nwords else 0.0,
                         chunks[0][0].start - clip_start if chunks else None,
                         chunks[-1][-1].end - clip_start if chunks else None)
