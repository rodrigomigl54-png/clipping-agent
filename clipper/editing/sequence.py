"""Hand-timed vertical edits (1080x1920): a list of segments (video shot / still image) on a timeline, with
dissolve or flash transitions, per-segment looks (sepia, grain, pixelate, grey, fade), logo stamps, captions and
a sharpening pass. Two layouts:

* "full":   picture fills the 1080x1920 frame (only for >=1080p sources: 1.78x max, never blurry)
* "window": a 4:3 picture (1080x810) in the middle of a blurred, darkened copy of itself (fits 720p sources at 1.125x)

Shots are read with clipper.editing.longform.read_frames (letterbox removed, <=2x upscale); stills come from the
4K official images and are only ever scaled down.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np

from . import longform as LF
from .lyric_fx import caption_rgba

W, H, FPS = 1080, 1920, 30
WIN_W, WIN_H = 1080, 810


def _sharpen(img: np.ndarray, amount: float = 0.6) -> np.ndarray:
    blur = cv2.GaussianBlur(img, (0, 0), 1.2)
    return cv2.addWeighted(img, 1 + amount, blur, -amount, 0)


def _look(img: np.ndarray, fx: dict, k: float) -> np.ndarray:
    """k = 0..1 progress inside the segment."""
    if not fx:
        return img
    out = img
    if fx.get("gray") or fx.get("sepia"):
        g = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
        g3 = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR).astype(np.float32)
        if fx.get("sepia"):
            g3 = g3 * np.array([0.72, 0.9, 1.08], np.float32)
        amt = float(fx.get("gray", fx.get("sepia", 1.0)))
        out = np.clip(out.astype(np.float32) * (1 - amt) + g3 * amt, 0, 255).astype(np.uint8)
    if fx.get("pixel"):
        p = int(fx["pixel"] if not isinstance(fx["pixel"], (list, tuple)) else fx["pixel"][0] + (fx["pixel"][1] - fx["pixel"][0]) * k)
        if p > 1:
            h, w = out.shape[:2]
            out = cv2.resize(cv2.resize(out, (max(1, w // p), max(1, h // p)), interpolation=cv2.INTER_AREA), (w, h),
                             interpolation=cv2.INTER_NEAREST)
    if fx.get("grain"):
        n = np.random.default_rng(int(k * 1000)).normal(0, fx["grain"], out.shape[:2]).astype(np.float32)
        out = np.clip(out.astype(np.float32) + n[..., None], 0, 255).astype(np.uint8)
    if fx.get("vivid"):
        hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 1] *= fx["vivid"]
        out = cv2.convertScaleAbs(cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR), alpha=1.06, beta=-4)
    if fx.get("fade_out"):
        f = max(0.0, (k - (1 - fx["fade_out"])) / fx["fade_out"])
        out = (out.astype(np.float32) * (1 - f)).astype(np.uint8)
    return out


def _image_frames(path: str, dur: float, w: int, h: int, zoom=(1.0, 1.08), cx=0.5, cy=0.5):
    img = cv2.imread(str(path))
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih)
    base_w, base_h = w / s, h / s                          # crop size in source pixels at zoom 1
    n = int(round(dur * FPS))
    for i in range(n):
        z = zoom[0] + (zoom[1] - zoom[0]) * (i / max(1, n - 1))
        cw, ch = base_w / z, base_h / z
        x0 = min(max(cx * iw - cw / 2, 0), iw - cw)
        y0 = min(max(cy * ih - ch / 2, 0), ih - ch)
        crop = img[int(y0):int(y0 + ch), int(x0):int(x0 + cw)]
        yield cv2.resize(crop, (w, h), interpolation=cv2.INTER_AREA)


def _segment_frames(seg: dict, w: int, h: int):
    dur = seg["t1"] - seg["t0"]
    if seg.get("image"):
        yield from _image_frames(seg["image"], dur, w, h, seg.get("zoom", (1.0, 1.06)), seg.get("cx", 0.5), seg.get("cy", 0.5))
        return
    info = LF.shot_info(seg["ref"])
    if "cx" in seg:
        info = {**info, "cx": seg["cx"]}
    if "start" in seg:
        info = {**info, "start": seg["start"], "end": seg.get("end", seg["start"] + dur + 1)}
    z0, z1 = seg.get("zoom", (1.0, 1.04))
    n = int(round(dur * FPS))
    for i, f in enumerate(LF.read_frames(info, dur, w, h, seg.get("offset", 0.0))):
        z = z0 + (z1 - z0) * (i / max(1, n - 1))
        if z > 1.001:
            f = cv2.resize(f, None, fx=z, fy=z, interpolation=cv2.INTER_CUBIC)
            y0, x0 = (f.shape[0] - h) // 2, (f.shape[1] - w) // 2
            f = f[y0:y0 + h, x0:x0 + w]
        yield _sharpen(np.ascontiguousarray(f), seg.get("sharp", 0.5))


def _blend_rgba(frame, img, x, y, alpha=1.0):
    LF.over(frame, img, x, y, alpha, anchor="c")


def render(spec: dict, out: Path, audio_from: str | None = None) -> dict:
    """spec = {layout, duration, segments:[...], captions:[...], logos:[...], vivid}"""
    layout = spec.get("layout", "full")
    pw, ph = (W, H) if layout == "full" else (WIN_W, WIN_H)
    py = 0 if layout == "full" else (H - WIN_H) // 2 + spec.get("window_dy", 0)
    out.parent.mkdir(parents=True, exist_ok=True)
    silent = out.with_name(out.stem + "_silent.mp4")
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p",
                            "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE)
    logos = {}
    for lg in spec.get("logos", []):
        if lg["img"] not in logos:
            logos[lg["img"]] = cv2.imread(lg["img"], cv2.IMREAD_UNCHANGED)
    caps = {}
    total = int(round(spec["duration"] * FPS))
    fi = 0
    prev_last = None
    for seg in spec["segments"]:
        n_target = int(round(seg["t1"] * FPS)) - fi
        produced = 0
        last = None
        for f in _segment_frames(seg, pw, ph):
            if produced >= n_target:
                break
            t = fi / FPS
            k = produced / max(1, n_target - 1)
            f = _look(f, {**({"vivid": spec["vivid"]} if spec.get("vivid") else {}), **seg.get("fx", {})}, k)
            tr = seg.get("trans", "cut")
            if tr == "dissolve" and prev_last is not None and produced < 5:
                a = (produced + 1) / 6
                f = cv2.addWeighted(f, a, prev_last, 1 - a, 0)
            if tr == "flash" and produced < 4:
                a = 0.8 * (1 - produced / 4)
                f = cv2.addWeighted(f, 1 - a, np.full_like(f, 255), a, 0)
            if layout == "full":
                frame = f
            else:
                bg = cv2.resize(cv2.GaussianBlur(cv2.resize(f, (W // 10, H // 10)), (0, 0), 3), (W, H))
                frame = (bg.astype(np.float32) * 0.35).astype(np.uint8)
                frame[py:py + ph, 0:pw] = f
            for lg in spec.get("logos", []):
                if lg["t0"] <= t < lg["t1"]:
                    img = logos[lg["img"]]
                    kk = (t - lg["t0"]) / max(0.01, lg["t1"] - lg["t0"])
                    s0, s1 = lg.get("scale", (0.5, 0.5))
                    pop = 1 - (1 - min(1.0, (t - lg["t0"]) / 0.12)) ** 3
                    sc = (s0 + (s1 - s0) * kk) * (1.25 - 0.25 * pop if lg.get("pop") else 1.0)
                    wpx = int(W * sc)
                    li = cv2.resize(img, (wpx, int(img.shape[0] * wpx / img.shape[1])), interpolation=cv2.INTER_AREA)
                    x, y = lg.get("pos", (0.5, 0.5))
                    yy = py + ph * y if lg.get("in_window") else H * y
                    fade = min(1.0, (lg["t1"] - t) / 0.08) * (pop if lg.get("pop") else min(1.0, (t - lg["t0"]) / 0.25))
                    _blend_rgba(frame, li, W * x, yy, fade * lg.get("alpha", 1.0))
            for c in spec.get("captions", []):
                if c["t0"] <= t < c["t1"]:
                    key = (c["text"], c.get("size", 54))
                    if key not in caps:
                        im = caption_rgba(c["text"], c.get("size", 54))
                        if im.shape[1] > W - 80:
                            r = (W - 80) / im.shape[1]
                            im = cv2.resize(im, None, fx=r, fy=r, interpolation=cv2.INTER_AREA)
                        caps[key] = im
                    y = c["y"] if c.get("abs") else (py + ph * c.get("y", 0.5) if c.get("in_window", True) else H * c["y"])
                    a = min(1.0, (t - c["t0"]) / 0.1) * min(1.0, (c["t1"] - t) / 0.1)
                    _blend_rgba(frame, caps[key], W / 2, y, a)
            enc.stdin.write(np.ascontiguousarray(frame).tobytes())
            last = f
            fi += 1
            produced += 1
        while produced < n_target:
            enc.stdin.write(np.ascontiguousarray(frame).tobytes())
            fi += 1
            produced += 1
        prev_last = last
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("encode failed")
    res = {"file": str(silent), "frames": fi, "duration": round(fi / FPS, 2)}
    if audio_from:
        from .lyric_fx import mux
        mux(silent, audio_from, out)
        res["preview_with_sound"] = str(out)
    return res
