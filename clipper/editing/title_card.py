"""On-screen title card rendered as an image (Pillow): rounded box, bold text, colour emojis.

libass draws emojis in monochrome, so the clip-channel style headline ("Kai Cenat is OFFICIALLY the
first streamer to PLAY GTA6 😨👀") is drawn here and alpha-blended onto every frame instead.
"""
from __future__ import annotations

import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

TEXT_FONTS = ["assets/fonts/title.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"]
EMOJI_FONTS = ["assets/fonts/emoji.ttf", "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
               "/System/Library/Fonts/Apple Color Emoji.ttc", "C:/Windows/Fonts/seguiemj.ttf"]


def _first(paths: list[str], root: Path) -> str | None:
    for p in paths:
        q = Path(p) if Path(p).is_absolute() else root / p
        if q.exists():
            return str(q)
    return None


def is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2B00 <= cp <= 0x2BFF
            or cp in (0xFE0F, 0x200D) or unicodedata.category(ch) == "So")


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


class _Fonts:
    def __init__(self, root: Path, size: int):
        tf = _first(TEXT_FONTS, root)
        self.text = ImageFont.truetype(tf, size) if tf else ImageFont.load_default()
        self.size = size
        ef = _first(EMOJI_FONTS, root)
        self.emoji = None
        if ef:
            try:   # Noto Color Emoji is a bitmap font that only renders at size 109
                self.emoji = ImageFont.truetype(ef, 109)
            except OSError:
                self.emoji = None

    def width(self, draw: ImageDraw.ImageDraw, s: str) -> float:
        w = 0.0
        for ch in s:
            if is_emoji(ch):
                if ord(ch) in (0xFE0F, 0x200D):
                    continue
                w += self.size * 1.15
            else:
                w += draw.textlength(ch, font=self.text)
        return w


def _wrap(draw, fonts: _Fonts, text: str, max_w: float) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if cur and fonts.width(draw, test) > max_w:
            lines.append(cur); cur = word
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def make_title_card(text: str, cfg: dict, width: int, root: Path) -> np.ndarray:
    """Return an RGBA uint8 array (h, width, 4) with the title card, transparent around the box."""
    size = int(cfg.get("size", 62))
    pad = int(cfg.get("box_padding", 22))
    radius = int(cfg.get("radius", 28))
    max_line_w = width * float(cfg.get("max_width", 0.86)) - 2 * pad
    text_color = _hex(cfg.get("text_color", "#000000"))
    box = cfg.get("box_color", "#FFFFFF")
    if cfg.get("uppercase", False):
        text = text.upper()
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    fonts = _Fonts(root, size)
    lines = _wrap(probe, fonts, text, max_line_w)[: int(cfg.get("max_lines", 3))]
    # emojis-only trailing line, as clip channels do
    line_h = int(size * 1.25)
    widths = [fonts.width(probe, l) for l in lines]
    box_w = int(min(width * 0.96, max(widths or [0]) + 2 * pad))
    box_h = line_h * len(lines) + 2 * pad - int(size * 0.15)
    img = Image.new("RGBA", (width, box_h + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x0 = (width - box_w) // 2
    if box and str(box).lower() not in ("none", "transparent"):
        d.rounded_rectangle([x0, 0, x0 + box_w, box_h], radius=radius, fill=(*_hex(box), 255))
    y = pad - int(size * 0.08)
    for line, lw in zip(lines, widths):
        x = (width - lw) / 2
        for ch in line:
            if ord(ch) in (0xFE0F, 0x200D):
                continue
            if is_emoji(ch) and fonts.emoji is not None:
                glyph = Image.new("RGBA", (136, 128), (0, 0, 0, 0))
                ImageDraw.Draw(glyph).text((0, 0), ch, font=fonts.emoji, embedded_color=True)
                bbox = glyph.getbbox()
                if bbox:
                    glyph = glyph.crop(bbox)
                es = int(size * 1.05)
                glyph = glyph.resize((es, int(es * glyph.height / max(1, glyph.width))), Image.LANCZOS)
                img.alpha_composite(glyph, (int(x), int(y + size * 0.12)))
                x += size * 1.15
            else:
                d.text((x, y), ch, font=fonts.text, fill=(*text_color, 255))
                x += d.textlength(ch, font=fonts.text)
        y += line_h
    return np.array(img)


def blend(frame: np.ndarray, card: np.ndarray, y: int) -> np.ndarray:
    """Alpha-blend an RGBA card onto an RGB frame at vertical offset y (full width)."""
    h = min(card.shape[0], frame.shape[0] - y)
    if h <= 0:
        return frame
    a = card[:h, :, 3:4].astype(np.float32) / 255.0
    region = frame[y:y + h].astype(np.float32)
    frame[y:y + h] = (region * (1 - a) + card[:h, :, :3].astype(np.float32) * a).astype(np.uint8)
    return frame
