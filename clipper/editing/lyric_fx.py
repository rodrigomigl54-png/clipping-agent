"""Lyric-edit effects drawn on the final 1080x1920 frames (after the picture is placed in the vertical canvas).

Learned from the 2026-11-17 references (@gta6og "This doesn't feel real", "This must be heaven"; @kairoxxofficial
"2 DAYS LEFT"):
* `word`    one lyric word at a time, centred on the picture. style "white" = condensed caps, soft and slightly
            transparent; style "red" = the key words of the line, huge red condensed caps with a motion-blur punch-in.
* `mask`    a word filled with the footage on a black screen (the picture is visible only inside the letters).
* `window`  black screen with the picture visible in a centred rectangle that grows (intro reveal).
* `caption` small white line with emoji at the top of the picture (the joke of the video), stays on.
* `type`    small subtitle typed letter by letter (dialogue subtitle), optional highlighted word.

Events use seconds of the output video. All drawing is numpy/PIL; fonts are OFL fonts in assets/fonts.
"""
from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "assets" / "fonts"
W, H = 1080, 1920
RED = (28, 22, 205)          # BGR of the references' red (#cd161c)
YELLOW = (60, 215, 255)


def _font_path(name: str) -> str:
    p = {"anton": FONTS / "Anton-Regular.ttf", "bebas": FONTS / "BebasNeue-Regular.ttf",
         "inter": Path("/usr/share/fonts/opentype/inter/Inter-Bold.otf"),
         "serif": Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
         "serif_it": Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf")}[name]
    if not p.exists():
        p = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    return str(p)


def _is_emoji(ch: str) -> bool:
    o = ord(ch)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF or o in (0x200D, 0xFE0F)


@lru_cache(maxsize=256)
def text_mask(text: str, font: str, size: int, tracking: float = 0.0) -> np.ndarray:
    """Alpha mask (float32 0..1) of one line of text, tight box + small padding."""
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(_font_path(font), size)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    widths = [probe.textlength(c, font=f) for c in text]
    tw = sum(widths) + tracking * size * max(0, len(text) - 1)
    asc, desc = f.getmetrics()
    pad = int(size * 0.25)
    img = Image.new("L", (int(tw) + 2 * pad, asc + desc + 2 * pad), 0)
    d = ImageDraw.Draw(img)
    x = pad
    for c, w in zip(text, widths):
        d.text((x, pad), c, font=f, fill=255)
        x += w + tracking * size
    a = np.array(img, np.float32) / 255
    ys, xs = np.where(a > 0.02)
    if len(ys):
        a = a[max(0, ys.min() - pad):ys.max() + pad, max(0, xs.min() - pad):xs.max() + pad]
    return a


def fit_size(text: str, font: str, size: int, max_w: int, tracking: float = 0.0) -> int:
    while size > 12 and text_mask(text, font, size, tracking).shape[1] > max_w:
        size = int(size * 0.92)
    return size


@lru_cache(maxsize=64)
def caption_rgba(text: str, size: int) -> np.ndarray:
    """White text with colour emoji (Noto Color Emoji), soft shadow; RGBA uint8."""
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(_font_path("inter"), size)
    ef = ImageFont.truetype("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", 109)
    runs, cur, emo = [], "", False
    for ch in text:
        e = _is_emoji(ch)
        if cur and e != emo:
            runs.append((cur, emo))
            cur = ""
        cur, emo = cur + ch, e
    if cur:
        runs.append((cur, emo))
    pieces = []
    for s, e in runs:
        if e:
            s = s.replace("‍", "").replace("️", "")
            for ch in s:
                im = Image.new("RGBA", (140, 140), (0, 0, 0, 0))
                ImageDraw.Draw(im).text((0, 0), ch, font=ef, embedded_color=True)
                bb = im.getbbox() or (0, 0, 1, 1)
                im = im.crop(bb)
                k = size * 1.05 / max(1, im.height)
                pieces.append(im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS))
        else:
            probe = ImageDraw.Draw(Image.new("L", (1, 1)))
            w = int(probe.textlength(s, font=f)) + 2
            asc, desc = f.getmetrics()
            im = Image.new("RGBA", (w, asc + desc), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((0, 0), s, font=f, fill=(255, 255, 255, 255))
            pieces.append(im)
    hh = max(p.height for p in pieces) + 16
    ww = sum(p.width for p in pieces) + 16
    canvas = Image.new("RGBA", (ww, hh), (0, 0, 0, 0))
    x = 8
    for p in pieces:
        canvas.alpha_composite(p, (x, (hh - p.height) // 2))
        x += p.width
    arr = np.array(canvas)
    sh = cv2.GaussianBlur(arr[..., 3].astype(np.float32), (0, 0), size * 0.12) * 0.7
    out = np.zeros_like(arr)
    a = arr[..., 3:4].astype(np.float32) / 255
    out[..., :3] = (arr[..., :3] * a).astype(np.uint8)
    out[..., 3] = np.clip(np.maximum(arr[..., 3], sh), 0, 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_RGBA2BGRA)


def _blend(frame: np.ndarray, alpha: np.ndarray, color, cx: float, cy: float, opacity: float = 1.0) -> None:
    h, w = alpha.shape
    x, y = int(cx - w / 2), int(cy - h / 2)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    a = alpha[y0 - y:y1 - y, x0 - x:x1 - x, None] * opacity
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    col = np.array(color, np.float32)[None, None, :] if not isinstance(color, np.ndarray) else color[y0:y1, x0:x1]
    frame[y0:y1, x0:x1] = (roi * (1 - a) + col * a).astype(np.uint8)


def _bgra_over_impl(frame, img, cx, cy, opacity):
    h, w = img.shape[:2]
    x, y = int(cx - w / 2), int(cy - h / 2)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    part = img[y0 - y:y1 - y, x0 - x:x1 - x]
    a = part[..., 3:4].astype(np.float32) / 255 * opacity
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (roi * (1 - a) + part[..., :3].astype(np.float32) * a).astype(np.uint8)


class Overlay:
    """Draws lyric events on vertical frames. `pic` = (top, height) of the picture inside the canvas."""

    def __init__(self, events: list[dict], pic: tuple[int, int] = (0, H)):
        self.events = events
        self.top, self.ph = pic
        self.cy = self.top + self.ph / 2

    def draw(self, frame: np.ndarray, t: float) -> np.ndarray:
        for ev in self.events:
            if ev["t0"] <= t < ev["t1"]:
                frame = getattr(self, "_" + ev["type"])(frame, ev, t)
        return frame

    # -- events -------------------------------------------------------------------------------------------
    def _word(self, frame, ev, t):
        style = ev.get("style", "white")
        k = t - ev["t0"]
        cy = self.top + self.ph * ev.get("y", 0.5)
        if style == "red":
            size = fit_size(ev["text"], "anton", int(ev.get("size", 300)), int(W * 0.94), 0.0)
            m = text_mask(ev["text"], "anton", size)
            punch = max(0.0, 1 - k / 0.12)                 # 0.12 s punch-in: bigger + horizontal blur
            if punch > 0:
                s = 1 + 0.18 * punch
                m = cv2.resize(m, None, fx=s, fy=s, interpolation=cv2.INTER_LINEAR)
                L = int(5 + 60 * punch)
                m = cv2.filter2D(m, -1, np.ones((1, L), np.float32) / L)
            glow = cv2.GaussianBlur(m, (0, 0), 14) * 0.55
            _blend(frame, np.clip(glow, 0, 1), (10, 8, 120), W / 2, cy, 0.8)
            _blend(frame, m, RED, W / 2, cy, min(1.0, 0.35 + k / 0.05))
        else:
            size = fit_size(ev["text"], "bebas", int(ev.get("size", 150)), int(W * 0.9), 0.02)
            m = text_mask(ev["text"], "bebas", size, 0.02)
            fade_in = min(1.0, k / 0.08)
            fade_out = min(1.0, (ev["t1"] - t) / 0.06)
            sh = cv2.GaussianBlur(m, (0, 0), 10)
            _blend(frame, np.clip(sh * 0.9, 0, 1), (0, 0, 0), W / 2 + 3, cy + 4, 0.55 * fade_in)
            soft = cv2.GaussianBlur(m, (0, 0), 1.2)
            _blend(frame, soft, (245, 245, 245), W / 2, cy, ev.get("opacity", 0.9) * fade_in * fade_out)
        return frame

    def _mask(self, frame, ev, t):
        size = fit_size(ev["text"], "anton", int(ev.get("size", 330)), int(W * 0.96))
        m = text_mask(ev["text"], "anton", size)
        k = t - ev["t0"]
        op = min(1.0, k / 0.06) * min(1.0, (ev["t1"] - t) / ev.get("fade", 0.06))
        full = np.zeros(frame.shape[:2], np.float32)
        h, w = m.shape
        cy = int(self.top + self.ph * ev.get("y", 0.5))
        x, y = W // 2 - w // 2, cy - h // 2
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + w), min(frame.shape[0], y + h)
        full[y0:y1, x0:x1] = m[y0 - y:y1 - y, x0 - x:x1 - x] * op
        # the footage seen through the letters, brightened a little so the word reads
        pic = cv2.convertScaleAbs(frame, alpha=1.25, beta=12)
        return (pic.astype(np.float32) * full[..., None]).astype(np.uint8)

    def _window(self, frame, ev, t):
        p = (t - ev["t0"]) / max(0.01, ev["t1"] - ev["t0"])
        p = p * p * (3 - 2 * p)                                   # smoothstep
        s = ev.get("from", 0.12) + (ev.get("to", 1.0) - ev.get("from", 0.12)) * p
        out = np.zeros_like(frame)
        hw, hh = int(W * s / 2), int(self.ph * s / 2)
        cx, cy = W // 2, int(self.cy)
        out[cy - hh:cy + hh, cx - hw:cx + hw] = frame[cy - hh:cy + hh, cx - hw:cx + hw]
        return out

    def _caption(self, frame, ev, t):
        img = caption_rgba(ev["text"], int(ev.get("size", 46)))
        if img.shape[1] > W - 60:
            k = (W - 60) / img.shape[1]
            img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        y = ev.get("abs_y") or (self.top + self.ph * ev.get("y", 0.07))
        _bgra_over_impl(frame, img, W / 2, y, 1.0)
        return frame

    def _type(self, frame, ev, t):
        """Typed subtitle: `text` appears letter by letter over `dur` s; `hl` = word drawn in yellow italic serif."""
        txt = ev["text"]
        n = int(len(txt) * min(1.0, (t - ev["t0"]) / max(0.05, ev.get("dur", 0.6)))) + 1
        shown = txt[:n]
        size = int(ev.get("size", 34))
        cy = self.top + self.ph * ev.get("y", 0.55)
        hl = ev.get("hl")
        fade = min(1.0, (ev["t1"] - t) / 0.15)
        if hl and hl in shown:
            m = text_mask(hl, "serif_it", int(size * 1.9))
            _blend(frame, cv2.GaussianBlur(m, (0, 0), 6), (0, 0, 0), W / 2 + 2, cy - size * 1.1 + 3, 0.5 * fade)
            _blend(frame, m, YELLOW, W / 2, cy - size * 1.1, fade)
            shown = shown.replace(hl, "").strip()
        if shown:
            m = text_mask(shown.upper(), "serif", size, 0.25)
            _blend(frame, cv2.GaussianBlur(m, (0, 0), 5), (0, 0, 0), W / 2 + 2, cy + 3, 0.5 * fade)
            _blend(frame, m, (235, 240, 245), W / 2, cy, 0.95 * fade)
        return frame


def apply(src: Path, dst: Path, overlay: Overlay, *, fps: int = 30, grade: str | None = None) -> None:
    """Read the vertical silent video, draw the overlay on every frame, write `dst` (silent, crf 15)."""
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                           "-of", "csv=p=0", str(src)], capture_output=True, text=True, check=True).stdout.strip()
    w, h = map(int, info.split(","))
    vf = f"fps={fps}" + (f",{grade}" if grade else "")
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(src), "-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                            "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "15",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)], stdin=subprocess.PIPE)
    n, i = w * h * 3, 0
    while True:
        buf = dec.stdout.read(n)
        if len(buf) < n:
            break
        fr = np.frombuffer(buf, np.uint8).reshape(h, w, 3).copy()
        fr = overlay.draw(fr, i / fps)
        enc.stdin.write(np.ascontiguousarray(fr).tobytes())
        i += 1
    enc.stdin.close()
    dec.wait()
    if enc.wait() != 0:
        raise RuntimeError("encode failed")


def mux(video: Path, audio_from: str, out: Path, duration: float | None = None) -> None:
    from .template_edit import audio_fix
    base = ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", audio_from, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
            "-shortest"]
    if subprocess.run(base + ["-c:a", "copy", str(out)]).returncode != 0:
        subprocess.run(base + [*audio_fix(audio_from), "-c:a", "aac", "-b:a", "192k", str(out)], check=True)
