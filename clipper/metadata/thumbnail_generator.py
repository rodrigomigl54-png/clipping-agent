"""Thumbnail suggestion: sharpest frame with a visible face, plus short title overlay."""
from __future__ import annotations

import textwrap
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..core.media import media_info, read_frames
from ..detection.visual_analyzer import detect_faces

FONT_CANDIDATES = ["assets/fonts/thumbnail.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                   "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                   "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"]


def _font(root: Path, size: int):
    for c in FONT_CANDIDATES:
        p = Path(c) if Path(c).is_absolute() else root / c
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def pick_frame(video: Path, samples: int = 12) -> tuple[np.ndarray, float]:
    dur = media_info(video)["duration"]
    best, best_s, best_t = None, -1.0, 0.0
    for i in range(samples):
        t = dur * (0.1 + 0.8 * i / max(1, samples - 1))
        fr = next(iter(read_frames(video, t, 0.05, 25, 540, 960)), None)
        if fr is None:
            continue
        gray = cv2.cvtColor(fr, cv2.COLOR_RGB2GRAY)
        sharp = cv2.Laplacian(gray, cv2.CV_64F).var()
        bright = gray.mean() / 255
        faces = detect_faces(fr)
        s = np.log1p(sharp) + (2.0 if faces else 0) + (0 if 0.15 < bright < 0.9 else -3)
        if s > best_s:
            best, best_s, best_t = fr, s, t
    if best is None:
        raise RuntimeError("could not read frames for thumbnail")
    return best, best_t


def make_thumbnail(video: Path, title: str, out: Path, root: Path, size=(1080, 1920)) -> Path:
    frame, _ = pick_frame(video)
    img = Image.fromarray(frame).resize(size, Image.LANCZOS)
    draw = ImageDraw.Draw(img)
    text = title.split(":")[-1].strip().strip('"').upper() or title.upper()
    font = _font(root, 92)
    lines = textwrap.wrap(text, width=16)[:3]
    y = int(size[1] * 0.12)
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((size[0] - w) / 2, y), line, font=font, fill=(255, 255, 255), stroke_width=8,
                  stroke_fill=(0, 0, 0))
        y += 110
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, "JPEG", quality=90)
    return out
