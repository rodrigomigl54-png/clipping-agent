"""Detail / easter-egg tools and retention timeline.

* Timeline: the clip is rendered as a list of source segments plus optional holds (freeze frames).
  Used to remove dead air inside a clip (jump cuts) and to freeze on a detail without losing any
  footage or desynchronising the audio (the audio pauses during the hold).
* Detail events: zoom into a point of the picture, draw an animated circle or arrow and a short label,
  optionally freezing the frame. Applied in *source* coordinates before the vertical layout, so they
  work with every layout.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np


# ----------------------------------------------------------------------------- timeline
@dataclass
class Timeline:
    """Ordered pieces relative to the clip start: ("seg", a, b) source spans and ("hold", seconds)."""
    pieces: list[tuple] = field(default_factory=list)

    @classmethod
    def whole(cls, duration: float) -> "Timeline":
        return cls([("seg", 0.0, duration)])

    @property
    def duration(self) -> float:
        return sum((p[2] - p[1]) if p[0] == "seg" else p[1] for p in self.pieces)

    def map_time(self, t: float) -> float | None:
        """Source clip time -> output time (None if that moment was cut)."""
        out = 0.0
        for p in self.pieces:
            if p[0] == "hold":
                out += p[1]
                continue
            _, a, b = p
            if a <= t < b:
                return out + (t - a)
            out += b - a
        return None

    def insert_hold(self, at: float, seconds: float) -> None:
        """Freeze at source time ``at`` for ``seconds`` (splits the segment containing it)."""
        new = []
        done = False
        for p in self.pieces:
            if not done and p[0] == "seg" and p[1] <= at < p[2]:
                _, a, b = p
                if at > a:
                    new.append(("seg", a, at))
                new.append(("hold", seconds))
                new.append(("seg", at, b))
                done = True
            else:
                new.append(p)
        self.pieces = new

    @property
    def is_trivial(self) -> bool:
        return len(self.pieces) == 1 and self.pieces[0][0] == "seg" and self.pieces[0][1] == 0.0


def remove_dead_air(words, clip_start: float, clip_end: float, audio=None, *, min_gap: float = 0.75,
                    keep: float = 0.22) -> Timeline:
    """Cut pauses longer than ``min_gap`` between words (keep ``keep`` s of breath on each side),
    unless the audio is loud during the gap (a reaction, laughter or an explosion is not dead air)."""
    dur = clip_end - clip_start
    ws = sorted((w.start - clip_start, w.end - clip_start) for w in words if w.end > clip_start and w.start < clip_end)
    cuts = []
    for (a0, a1), (b0, b1) in zip(ws, ws[1:]):
        gap = b0 - a1
        if gap <= min_gap:
            continue
        if audio is not None:
            g0, g1 = clip_start + a1, clip_start + b0
            if audio.silence_fraction(g0, g1) < 0.6 or audio.peak_z(g0, g1) > 1.5:
                continue        # something audible is happening: keep it
        cuts.append((a1 + keep, b0 - keep))
    pieces, t = [], 0.0
    for c0, c1 in cuts:
        if c1 - c0 < 0.3:
            continue
        pieces.append(("seg", t, c0))
        t = c1
    pieces.append(("seg", t, dur))
    return Timeline([p for p in pieces if p[2] - p[1] > 0.05])


# ----------------------------------------------------------------------------- detail events
@dataclass
class DetailEvent:
    t: float                       # source clip time (seconds from clip start)
    x: float                       # point of interest, normalised in the SOURCE frame
    y: float
    label: str = ""
    shape: str = "circle"          # circle | arrow | none
    zoom: float = 1.8              # 1.0 = no zoom
    freeze: float = 0.0            # seconds to hold the frame (audio pauses)
    show: float = 2.2              # seconds the annotation stays (output time)
    color: tuple[int, int, int] = (255, 40, 40)

    def window(self) -> tuple[float, float]:
        return self.t - 0.15, self.t + max(self.show, self.freeze + 0.8)


def _ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def apply_detail(frame: np.ndarray, ev: DetailEvent, local_t: float, font_path: str | None) -> np.ndarray:
    """Draw one event on a SOURCE frame. ``local_t`` = seconds since the event started (output time)."""
    H, W = frame.shape[:2]
    cx, cy = ev.x * W, ev.y * H
    out = frame
    # zoom in over 0.35 s, hold, zoom out over the last 0.35 s
    total = max(ev.show, ev.freeze + 0.8)
    k = _ease(local_t / 0.35) * _ease((total - local_t) / 0.35)
    z = 1.0 + (ev.zoom - 1.0) * k
    if z > 1.01:
        cw, ch = W / z, H / z
        x0 = min(max(0.0, cx - cw / 2), W - cw)
        y0 = min(max(0.0, cy - ch / 2), H - ch)
        out = cv2.resize(frame[int(y0):int(y0 + ch), int(x0):int(x0 + cw)], (W, H), interpolation=cv2.INTER_CUBIC)
        cx, cy = (cx - x0) * z, (cy - y0) * z
    else:
        out = frame.copy()
    r = int(min(W, H) * 0.09)
    draw = _ease((local_t - 0.25) / 0.4)            # circle draws on after the zoom starts
    thick = max(3, W // 160)
    if ev.shape == "circle" and draw > 0:
        cv2.ellipse(out, (int(cx), int(cy)), (r, int(r * 0.85)), -90, 0, 360 * draw, ev.color, thick, cv2.LINE_AA)
    elif ev.shape == "arrow" and draw > 0:
        sx, sy = cx - r * 2.2, cy - r * 2.2
        ex, ey = sx + (cx - r * 0.6 - sx) * draw, sy + (cy - r * 0.6 - sy) * draw
        cv2.arrowedLine(out, (int(sx), int(sy)), (int(ex), int(ey)), ev.color, thick + 1, cv2.LINE_AA, tipLength=0.3)
    if ev.label and draw > 0.6:
        size = max(18, H // 18)
        if not hasattr(ev, "_label_xy"):
            ev._label_xy = _label_spot(out, ev.label, cx, cy, r, font_path, size)
        out = _label(out, ev.label, *ev._label_xy, font_path, size=size)
    return out


def _label_spot(frame: np.ndarray, text: str, cx: float, cy: float, r: int, font_path: str | None,
                size: int) -> tuple[int, int]:
    """Pick below / above / right / left of the circle — the first spot that covers no face."""
    from PIL import ImageFont
    from ..detection.visual_analyzer import detect_faces
    font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
    w = font.getlength(text)
    faces = detect_faces(frame, 0.04)
    H, W = frame.shape[:2]

    def clear(x, y):
        x0 = min(max(8, x - w / 2), W - w - 8)
        return all(x0 + w < fx or x0 > fx + fw or y + size < fy or y > fy + fh for fx, fy, fw, fh in faces)

    for x, y in ((cx, cy + r * 1.05), (cx, cy - r * 1.05 - size), (cx + r + w / 2 + 10, cy - size / 2),
                 (cx - r - w / 2 - 10, cy - size / 2)):
        if 0 <= y <= H - size and clear(x, y):
            return int(x), int(y)
    return int(cx), int(min(H - size - 8, cy + r * 1.05))


def _label(frame: np.ndarray, text: str, x: int, y: int, font_path: str | None, size: int) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.fromarray(frame)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
    w = d.textlength(text, font=font)
    H, W = frame.shape[:2]
    x = int(min(max(8, x - w / 2), W - w - 8))
    y = int(min(max(8, y), H - size - 8))
    d.text((x, y), text, font=font, fill=(255, 255, 255), stroke_width=max(2, size // 9), stroke_fill=(0, 0, 0))
    return np.array(img)


def font_for_labels(root: Path) -> str | None:
    for p in ("assets/fonts/title.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        q = Path(p) if Path(p).is_absolute() else root / p
        if q.exists():
            return str(q)
    return None


# ----------------------------------------------------------------------------- deciding when to use them
DETAIL_CATEGORIES = {"easter_egg", "fun_fact", "comparison", "story_moment", "news_trailer", "tips_tricks", "glitch_bug"}
CUE_WORDS = ["look at", "did you see", "do you see", "see that", "notice", "behind him", "behind her", "in the back",
             "right there", "over there", "detail", "check this", "zoom in", "watch this", "look closely", "in the corner"]

DETAIL_SCHEMA = {"type": "object", "properties": {"details": {"type": "array", "items": {"type": "object", "properties": {
    "t": {"type": "number"}, "x": {"type": "number"}, "y": {"type": "number"}, "label": {"type": "string"},
    "shape": {"type": "string", "enum": ["circle", "arrow", "none"]}, "zoom": {"type": "number"},
    "freeze": {"type": "number"}, "why": {"type": "string"}}, "required": ["t", "x", "y", "label"]}}},
    "required": ["details"]}


def needs_detail_tools(category: str | None, text: str) -> bool:
    from ..detection.text_signals import count_terms
    return (category in DETAIL_CATEGORIES) or count_terms(text, CUE_WORDS) > 0


def plan_details(src_path: str, start: float, end: float, text: str, gemini, max_events: int = 3) -> list[DetailEvent]:
    """Ask Gemini (frames + transcript) whether a KEY visual detail must be pointed out; [] if not."""
    import io
    from PIL import Image
    from google.genai import types
    from ..core.media import read_frames
    dur = end - start
    parts, times = [], []
    for i in range(6):
        t = dur * (0.08 + 0.84 * i / 5)
        fr = next(iter(read_frames(src_path, start + t, 0.05, 25, 640)), None)
        if fr is None:
            continue
        buf = io.BytesIO(); Image.fromarray(fr).save(buf, "JPEG", quality=85)
        parts.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")); times.append(round(t, 1))
    prompt = (f"These {len(parts)} frames are from one clip at times {times} (seconds). Transcript: {text[:2500]}\n"
              "Is there a specific visual DETAIL that viewers must notice to get the moment (an easter egg, a hidden "
              "object, a reflection, a sign, something behind someone, a bug)? Only answer with details that are "
              f"truly key; return an empty list otherwise. Up to {max_events}. For each: time t (seconds, near one of "
              "the frame times), x and y of the detail as fractions of the frame (0..1, from top-left), a label of at "
              "most 4 words, shape circle or arrow, zoom 1.0-2.2 (how much to zoom in), freeze seconds 0-1.5 (pause "
              "on it when it is fleeting), and why.")
    try:
        res = gemini.generate_json([*parts, prompt], DETAIL_SCHEMA, temperature=0.1)
    except Exception:
        return []
    out = []
    for d in (res or {}).get("details", [])[:max_events]:
        try:
            t, x, y = float(d["t"]), float(d["x"]), float(d["y"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= t <= dur and 0 <= x <= 1 and 0 <= y <= 1):
            continue
        out.append(DetailEvent(t=t, x=x, y=y, label=str(d.get("label", ""))[:28],
                               shape=d.get("shape") if d.get("shape") in ("circle", "arrow", "none") else "circle",
                               zoom=float(min(2.2, max(1.0, d.get("zoom") or 1.6))),
                               freeze=float(min(1.5, max(0.0, d.get("freeze") or 0.0)))))
    return out
