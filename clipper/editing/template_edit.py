"""Template edits: learn the exact structure of a viral edit and rebuild it with our footage.

A template is learned from a reference video (`learn_template`): every cut (frame-accurate), the look of
each shot (brightness, colour, motion, faces), the beat of its sound, the fade-out, the orientation.
On-screen text events (rolling countdown, word-by-word lines, letter scatter) are stored with their exact
timing. `render_template` then fills every slot with the most similar shot from our sources, cuts on
exactly the same frames, adds whip transitions (directional motion blur) on the cuts, the text events
with glow, the fade-out, and muxes the reference sound for the preview (the upload copy is silent:
the owner adds the same TikTok sound from 0:00).
"""
from __future__ import annotations

import json
import math
import random
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .hype_editor import Shot, _font, analyze_shots

FPS = 30
TEMPLATE_DIR = "config/hype_templates"
MAX_UPSCALE = 2.0


# ------------------------------------------------------------------ learning
def _probe(path: str) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    return {"w": v["width"], "h": v["height"], "duration": float(d["format"]["duration"]),
            "audio": any(s["codec_type"] == "audio" for s in d["streams"])}


def learn_template(ref: str | Path, tid: str, *, cut_thr: float = 0.35, merge_s: float = 0.15) -> dict:
    """Frame-accurate structure of a reference edit (cuts, per-shot look, beat, fade-out, orientation)."""
    from ..detection.visual_analyzer import detect_faces
    ref = str(ref)
    info = _probe(ref)
    aw, ah = 240, max(2, int(round(240 * info["h"] / info["w"] / 2)) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", ref, "-vf", f"fps={FPS},scale={aw}:{ah}", "-f", "rawvideo",
                          "-pix_fmt", "bgr24", "-"], capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, ah, aw, 3)
    hists = []
    for f in frames:
        h = cv2.calcHist([cv2.cvtColor(f, cv2.COLOR_BGR2HSV)], [0, 1, 2], None, [12, 6, 6], [0, 180, 0, 256, 0, 256])
        cv2.normalize(h, h)
        hists.append(h)
    d = np.array([0.0] + [cv2.compareHist(hists[i - 1], hists[i], cv2.HISTCMP_BHATTACHARYYA)
                          for i in range(1, len(hists))])
    bright = frames.reshape(len(frames), -1).mean(1)
    # cluster detections (whip transitions produce 2-3 high frames): one cut at the strongest frame
    cuts, i = [], 1
    while i < len(d):
        if d[i] > cut_thr:
            j = i
            while j + 1 < len(d) and (d[j + 1] > cut_thr * 0.8 or (j + 1 - i) < merge_s * FPS and d[j + 1] > 0.3):
                j += 1
            k = i + int(np.argmax(d[i:j + 1]))
            if bright[max(0, k - 1)] > 8 or bright[min(len(d) - 1, k)] > 8:     # not inside a fade to black
                cuts.append(round(k / FPS, 3))
            i = j + 1
        else:
            i += 1
    dur = len(frames) / FPS
    merged: list[float] = []
    for c in cuts:                       # a whip transition can register twice: keep one cut per 0.2 s
        if not merged or c - merged[-1] >= 0.2:
            merged.append(c)
    cuts = merged
    # fade-out: last point where brightness starts a steady decline to near black
    fade_from = None
    if bright[-1] < 15:
        k = len(bright) - 1
        while k > 0 and bright[k - 1] >= bright[k] - 1:
            k -= 1
        fade_from = round(k / FPS, 2)
        cuts = [c for c in cuts if c < fade_from - 0.2 or c < dur - 1.5]
    times = [0.0] + cuts + [dur]
    slots = []
    for a, b in zip(times[:-1], times[1:]):
        fa, fb = int(a * FPS), max(int(a * FPS) + 1, int(b * FPS))
        seg = frames[fa:fb]
        hsv = cv2.cvtColor(seg[len(seg) // 2], cv2.COLOR_BGR2HSV)
        sat_mask = hsv[..., 1] > 60
        mid = cv2.resize(cv2.cvtColor(seg[len(seg) // 2], cv2.COLOR_BGR2RGB), (640, int(640 * ah / aw)))
        mot = float(np.mean([cv2.absdiff(seg[i], seg[i - 1]).mean() for i in range(1, len(seg))])) / 255 \
            if len(seg) > 1 else 0.0
        slots.append({"t0": round(a, 3), "t1": round(b, 3), "bright": round(float(seg.mean()), 1),
                      "sat": round(float(hsv[..., 1].mean()), 1),
                      "hue": round(float(np.median(hsv[..., 0][sat_mask])), 1) if sat_mask.any() else -1,
                      "motion": round(mot, 4), "faces": len(detect_faces(mid, 0.08))})
    tpl = {"id": tid, "reference_file": Path(ref).name, "orientation": "landscape" if info["w"] > info["h"] else "vertical",
           "duration": round(dur, 3), "cuts": cuts, "slots": slots, "fade_out_from": fade_from,
           "transition": "whip", "text": [], "text_style": {}}
    if info["audio"]:
        tpl.update(_beats(ref))
    return tpl


def _beats(ref: str) -> dict:
    try:
        import librosa
    except ImportError:
        return {}
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", ref, "-ac", "1", "-ar", "22050", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    y = np.frombuffer(raw, np.float32)
    tempo, beats = librosa.beat.beat_track(y=y, sr=22050, units="time")
    return {"bpm": round(float(np.atleast_1d(tempo)[0]), 1), "beats": [round(float(b), 3) for b in beats]}


def save_template(root: Path, tpl: dict) -> Path:
    p = root / TEMPLATE_DIR / f"{tpl['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(tpl, indent=1, ensure_ascii=False))
    return p


def load_template(root: Path, tid: str) -> dict:
    return json.loads((root / TEMPLATE_DIR / f"{tid}.json").read_text())


def list_templates(root: Path) -> list[dict]:
    d = root / TEMPLATE_DIR
    return [json.loads(p.read_text()) for p in sorted(d.glob("*.json"))] if d.exists() else []


# ------------------------------------------------------------------ shot matching
def _dist(sig: dict, s: Shot) -> float:
    dh = 0.0
    if sig["hue"] >= 0 and s.hue >= 0:
        dh = min(abs(sig["hue"] - s.hue), 180 - abs(sig["hue"] - s.hue)) / 45
    face = 0.8 if (sig["faces"] > 0) != (s.faces > 0) else 0.0
    return abs(sig["bright"] - s.bright) / 50 + abs(sig["sat"] - s.sat) / 90 + dh * 0.6 + face + \
        abs(sig["motion"] - s.motion) * 6


@dataclass
class Fill:
    t0: float
    t1: float
    shot: Shot
    src_start: float
    speed: float = 1.0


def assign(tpl: dict, shots: list[Shot], min_speed: float = 0.6, exclude: set | None = None) -> list[Fill]:
    """Fill each slot with the most similar unused shot. `exclude` = shots used in recent videos (avoided
    when possible so daily videos do not repeat the same shots)."""
    pool = [s for s in shots if s.usable and not s.ui]          # never shots with social-media / phone UI
    exclude = exclude or set()
    used: set[tuple[str, float]] = set()
    fills = []
    for sig in tpl["slots"]:
        dur = sig["t1"] - sig["t0"]
        ok = [s for s in pool if (s.src, s.start) not in used and s.length >= dur * min_speed + 0.1]
        if not ok:                       # allow re-use of a different part of a long shot before failing
            ok = [s for s in pool if s.length >= dur * min_speed + 0.1]
        if not ok:
            raise ValueError(f"no shot long enough for slot {sig['t0']:.2f}-{sig['t1']:.2f}")
        vertical = tpl.get("orientation") == "vertical"
        best = min(ok, key=lambda s: _dist(sig, s) + (0.0 if s.length >= dur + 0.1 else 0.6)
                   + (2.5 if vertical and s.bar else 0.0)            # vertical: avoid letterboxed shots
                   - (s.iconic - 5.0) * 0.15                          # prefer the most iconic shots
                   + (1.5 if (Path(s.src).name, round(s.start, 2)) in exclude else 0.0))
        used.add((best.src, best.start))
        speed = min(1.0, (best.length - 0.1) / dur)
        need = dur * speed
        start = min(max(best.start + 0.05, best.peak - 0.1), best.end - need - 0.05)
        fills.append(Fill(sig["t0"], sig["t1"], best, max(best.start, start), speed))
    return fills


# ------------------------------------------------------------------ text
def _text_rgba(text: str, size: int, glow: float = 0.0, tracking: float = 0.0) -> np.ndarray:
    """White text (one or more lines, centred) with an optional soft white glow, as RGBA."""
    from PIL import Image, ImageDraw
    f = _font(size)
    lines = text.split("\n")
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))

    def line_w(s: str) -> float:
        return sum(probe.textlength(c, font=f) for c in s) + tracking * size * max(0, len(s) - 1)
    lh = int(size * 0.98)
    pad = int(size * 0.8)
    W = int(max(line_w(l) for l in lines)) + 2 * pad
    H = lh * len(lines) + 2 * pad
    img = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        x = (W - line_w(l)) / 2
        for c in l:
            d.text((x, pad + i * lh), c, font=f, fill=255)
            x += probe.textlength(c, font=f) + tracking * size
    a = np.array(img).astype(np.float32)
    if glow > 0:
        g = cv2.GaussianBlur(a, (0, 0), size * 0.25) * glow
        a = np.maximum(a, np.clip(g, 0, 255))
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[..., :3] = 255
    rgba[..., 3] = np.clip(a, 0, 255).astype(np.uint8)
    return rgba


def _over(frame: np.ndarray, layer: np.ndarray, cx: float, cy: float, alpha: float = 1.0,
          angle: float = 0.0, scale: float = 1.0) -> None:
    if scale != 1.0 or angle:
        h, w = layer.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
        layer = cv2.warpAffine(layer, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    H, W = frame.shape[:2]
    h, w = layer.shape[:2]
    x, y = int(cx - w / 2), int(cy - h / 2)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    part = layer[y0 - y:y1 - y, x0 - x:x1 - x]
    a = part[..., 3:4].astype(np.float32) / 255 * alpha
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (roi * (1 - a) + part[..., :3].astype(np.float32) * a).astype(np.uint8)


def _fmt(s: str, vars: dict) -> str:
    return s.format(**vars)


def _num(x, vars: dict) -> float:
    """Evaluate a tiny arithmetic expression such as "{days}+986" (digits and + - * / only)."""
    import re
    expr = _fmt(str(x), vars)
    if not re.fullmatch(r"[0-9+\-*/. ()]+", expr):
        raise ValueError(f"bad counter expression: {expr!r}")
    return float(eval(expr, {"__builtins__": {}}))


def _counter_value(ev: dict, t: float, vars: dict) -> int:
    start, end = _num(ev["from"], vars), _num(ev["to"], vars)
    n = max(1, int(round((ev["t1"] - ev["t0"]) / ev["every"])) - 1)
    k = min(n, int((t - ev["t0"]) / ev["every"] + 1e-6))
    return int(round(start + (end - start) * k / n))


class TextRenderer:
    def __init__(self, tpl: dict, vars: dict, H: int, W: int | None = None):
        self.tpl, self.vars, self.H = tpl, vars, H
        self.max_w = int((W or H) * 0.86)
        st = tpl.get("text_style", {})
        self.size = int(H * st.get("size", 0.058))
        self.line_size = int(H * st.get("line_size", 0.040))
        self.glow = float(st.get("glow", 0.9))
        self.track = float(st.get("tracking", 0.04))
        self.y = float(st.get("y", 0.5))
        self.cache: dict[tuple, np.ndarray] = {}
        self.scatter_seed = 7

    def layer(self, text: str, size: int) -> np.ndarray:
        key = (text, size)
        if key not in self.cache:
            img = _text_rgba(text, size, self.glow, self.track)
            pad = int(size * 0.8) * 2
            while img.shape[1] - pad > self.max_w and size > 20:      # never run off the screen
                size = int(size * 0.9)
                pad = int(size * 0.8) * 2
                img = _text_rgba(text, size, self.glow, self.track)
            self.cache[key] = img
        return self.cache[key]

    def draw(self, frame: np.ndarray, t: float) -> None:
        H, W = frame.shape[:2]
        cy = H * self.y
        wm = self.vars.get("watermark")
        if wm and t < self.tpl["duration"] - 0.4:           # small channel tag below the centre, like the references
            if "_wm" not in self.cache:
                self.cache["_wm"] = _text_rgba(wm, max(16, int(H * 0.02)), 0.0, 0.08)
            _over(frame, self.cache["_wm"], W / 2, H * 0.62, alpha=0.55)
        for ev in self.tpl.get("text", []):
            if not ev["t0"] <= t < ev["t1"]:
                continue
            kind = ev.get("type", "line")
            if kind == "counter":
                v = _counter_value(ev, t, self.vars)
                _over(frame, self.layer(f"{v}\n{_fmt(ev.get('suffix', 'DAYS'), self.vars)}", self.size), W / 2, cy)
            elif kind == "line":
                txt = _fmt(ev["text"], self.vars)
                pop = 1.0 + 0.10 * max(0.0, 1 - (t - ev["t0"]) * FPS / 4)
                _over(frame, self.layer(txt, self.line_size), W / 2, cy, scale=pop)
            elif kind == "scatter":
                self._scatter(frame, _fmt(ev["text"], self.vars), (t - ev["t0"]) / (ev["t1"] - ev["t0"]), W, cy)

    def _scatter(self, frame: np.ndarray, text: str, p: float, W: int, cy: float) -> None:
        """Letters of the line fly apart (spin + fade), as at the end of the reference's question."""
        from PIL import Image, ImageDraw
        f = _font(self.line_size)
        probe = ImageDraw.Draw(Image.new("L", (1, 1)))
        total = sum(probe.textlength(c, font=f) for c in text) + self.track * self.line_size * (len(text) - 1)
        x = W / 2 - total / 2
        rnd = random.Random(self.scatter_seed)
        ease = 1 - (1 - p) ** 2
        for c in text:
            cw = probe.textlength(c, font=f)
            if c.strip():
                ang = rnd.uniform(0, 2 * math.pi)
                dist = rnd.uniform(0.10, 0.32) * W * ease
                rot = rnd.uniform(-220, 220) * ease
                _over(frame, self.layer(c, self.line_size), x + cw / 2 + math.cos(ang) * dist,
                      cy + math.sin(ang) * dist * 0.8, alpha=max(0.0, 1 - p * 1.1), angle=rot)
            x += cw + self.track * self.line_size


# ------------------------------------------------------------------ rendering
def _grade(img: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.10, 0, 255)
    img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    return cv2.convertScaleAbs(img, alpha=1.06, beta=-6)


def _whip(img: np.ndarray, strength: float, direction: int) -> np.ndarray:
    """Directional motion blur + push, like a whip-pan transition (strength 0-1)."""
    if strength <= 0.02:
        return img
    H, W = img.shape[:2]
    small = cv2.resize(img, (W // 2, H // 2), interpolation=cv2.INTER_AREA)
    L = max(3, int(strength * W * 0.07))
    k = np.zeros((1, L), np.float32)
    k[0, :] = 1.0 / L
    blurred = cv2.filter2D(small, -1, k)
    shift = int(direction * strength * W * 0.04)
    M = np.float32([[1, 0, shift], [0, 1, 0]])
    blurred = cv2.warpAffine(blurred, M, (W // 2, H // 2), borderMode=cv2.BORDER_REFLECT)
    return cv2.resize(blurred, (W, H), interpolation=cv2.INTER_LINEAR)


def _read_segment(src: str, start: float, dur: float, speed: float, W: int, H: int, src_w: int, src_h: int,
                  bar: float = 0.0, cx: float = 0.5):
    """Frames of one shot filling W x H: cinematic black bars are cropped away, then the largest centred
    crop with the output aspect ratio is scaled up (never letterboxed)."""
    if bar and H / (src_h * (1 - 2 * bar)) > MAX_UPSCALE and W < H:
        bar = 0.0                       # vertical crop of a letterboxed shot would be too soft: keep its bars
    vis_h = int(src_h * (1 - 2 * bar)) // 2 * 2
    if W / H > src_w / vis_h:
        cw, ch = src_w, int(src_w * H / W) // 2 * 2
    else:
        cw, ch = int(vis_h * W / H) // 2 * 2, vis_h
    x = int(min(max(cx * src_w - cw / 2, 0), src_w - cw))      # vertical crops follow the face / action
    vf = f"crop={cw}:{ch}:{x}:{(src_h - ch) // 2},scale={W}:{H}:flags=lanczos,"
    vf += f"setpts=PTS/{speed:.4f},minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir" \
        if speed < 0.999 else f"fps={FPS}"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{(dur + 0.15) * speed:.3f}", "-i", src,
                          "-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True, check=True).stdout
    n = W * H * 3
    return [np.frombuffer(raw[i:i + n], np.uint8).reshape(H, W, 3) for i in range(0, len(raw) - n + 1, n)]


def render_template(tpl: dict, fills: list[Fill], out: Path, vars: dict, *, audio_from: str | None = None,
                    src_size: tuple[int, int] = (1920, 1080)) -> dict:
    W, H = (1920, 1080) if tpl["orientation"] == "landscape" else (1080, 1920)
    sw, sh = src_size
    upscale = max(W / sw, H / sh)
    out.parent.mkdir(parents=True, exist_ok=True)
    silent = out.with_name(out.stem + "_silent.mp4")
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE)
    text = TextRenderer(tpl, vars, H, W)
    cuts = [f.t0 for f in fills[1:]]
    whip_on = tpl.get("transition") == "whip"
    fade = tpl.get("fade_out_from")
    total = tpl["duration"]
    n_frames = int(round(total * FPS))
    cache: dict[int, list[np.ndarray]] = {}
    log = []
    for fi in range(n_frames):
        t = fi / FPS
        si = next((i for i, f in enumerate(fills) if f.t0 <= t < f.t1), len(fills) - 1)
        f = fills[si]
        if si not in cache:
            cache.clear()
            cache[si] = _read_segment(f.shot.src, f.src_start, f.t1 - f.t0, f.speed, W, H, sw, sh, f.shot.bar, f.shot.cx)
            b = f.shot.bar if not (f.shot.bar and H / (sh * (1 - 2 * f.shot.bar)) > MAX_UPSCALE and W < H) else 0.0
            upscale = max(upscale, H / (sh * (1 - 2 * b)))
            log.append({"t": round(f.t0, 2), "dur": round(f.t1 - f.t0, 2), "src": Path(f.shot.src).name,
                        "src_t": round(f.src_start, 2), "speed": round(f.speed, 2), "bar": f.shot.bar})
        frs = cache[si]
        img = _grade(frs[min(len(frs) - 1, int((t - f.t0) * FPS))]) if frs else np.zeros((H, W, 3), np.uint8)
        if whip_on and cuts:
            c = min(cuts, key=lambda c: abs(c - t))
            dist = abs(t - c) * FPS
            if dist < 2.5:
                direction = -1 if cuts.index(c) % 2 else 1
                img = _whip(img, 1 - dist / 2.5, direction if t < c else -direction)
        if fade is not None and t >= fade:
            img = (img * max(0.0, 1 - (t - fade) / max(0.1, total - fade))).astype(np.uint8)
        text.draw(img, t)
        enc.stdin.write(img.tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg encode failed")
    res = {"file": str(silent), "duration": round(n_frames / FPS, 2), "shots": log, "upscale": round(upscale, 2),
           "size": f"{W}x{H}"}
    if audio_from:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", audio_from, "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True)
        res["preview_with_sound"] = str(out)
    return res


def make_template_edit(tpl: dict, sources: list[str], out: Path, vars: dict, *, audio_from: str | None = None,
                       shot_cache: Path | None = None, exclude: set | None = None, tags_dir: Path | None = None,
                       gemini=None) -> dict:
    shots: list[Shot] = []
    for s in sources:
        cp = shot_cache / (Path(s).name + ".shots.json") if shot_cache else None
        if cp and cp.exists() and cp.stat().st_mtime >= Path(s).stat().st_mtime:
            shots += [Shot(**d) for d in json.loads(cp.read_text())]
            continue
        found = analyze_shots(s)
        if cp:
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps([d.__dict__ for d in found]))
        shots += found
    if tags_dir is not None:
        for src in sources:
            tag_shots(src, [x for x in shots if x.src == src], tags_dir, gemini)
    info = _probe(sources[0])
    fills = assign(tpl, shots, exclude=exclude)
    res = render_template(tpl, fills, out, vars, audio_from=audio_from, src_size=(info["w"], info["h"]))
    res.update({"template": tpl["id"], "shots_usable": sum(s.usable for s in shots), "source_height": info["h"],
                "used_shots": [[Path(f.shot.src).name, round(f.shot.start, 2)] for f in fills]})
    return res


# ------------------------------------------------------------------ on-screen text (learned)
TEXT_SCHEMA = {"type": "object", "properties": {
    "items": {"type": "array", "items": {"type": "object", "properties": {
        "text": {"type": "string"}, "start": {"type": "number"}, "end": {"type": "number"},
        "position_y": {"type": "number"}}, "required": ["text", "start", "end"]}},
    "text_size": {"type": "string", "enum": ["small", "medium", "large"]}}, "required": ["items"]}

TEXT_PROMPT = """List EVERY on-screen text overlay of this {duration:.1f}s edit with exact timing in seconds.
- One item per distinct text state: if a number counts down/up quickly, report each value you can read as its own
  item (e.g. "993 DAYS", "963 DAYS", ...).
- If words appear one by one ("ARE" -> "ARE YOU" -> "ARE YOU READY"), report each state.
- Ignore the creator watermark, TikTok UI and text that is part of the game picture (signs, HUD).
- position_y = vertical centre of the text as a fraction of the height (0 top, 1 bottom).
Known cut times (s): {cuts}."""

_NUM = re.compile(r"^\s*(\d[\d,\.]*)\s*(DAYS?|HOURS?|WEEKS?)?\s*$", re.I)


def text_events(items: list[dict], cuts: list[float], duration: float) -> list[dict]:
    """Turn timed text states into template events: runs of numbers become a rolling counter that ends at
    the real number of days; lines keep their words (a day count inside becomes {days})."""
    items = sorted([i for i in items if (i.get("text") or "").strip()], key=lambda i: i["start"])

    def snap(t: float) -> float:
        c = min(cuts or [t], key=lambda c: abs(c - t))
        return round(c if abs(c - t) <= 0.12 else t, 3)
    out, i = [], 0
    while i < len(items):
        m = _NUM.match(items[i]["text"].replace("\n", " "))
        if m:
            j = i
            while j + 1 < len(items) and _NUM.match(items[j + 1]["text"].replace("\n", " ")):
                j += 1
            run = items[i:j + 1]
            vals = [float(_NUM.match(r["text"].replace("\n", " ")).group(1).replace(",", "")) for r in run]
            unit = (m.group(2) or "DAYS").upper()
            if len(run) >= 3:
                every = max(0.033, (run[-1]["start"] - run[0]["start"]) / (len(run) - 1))
                out.append({"type": "counter", "t0": snap(run[0]["start"]), "t1": snap(run[-1]["end"]), "every": round(every, 3),
                            "from": f"{{days}}+{int(vals[0] - vals[-1])}", "to": "{days}", "suffix": unit})
            else:
                for r in run:
                    out.append({"type": "line", "t0": snap(r["start"]), "t1": snap(r["end"]), "text": f"{{days}} {unit}"})
            i = j + 1
            continue
        txt = re.sub(r"\b\d+\s+(DAYS?)\b", r"{days} \1", items[i]["text"], flags=re.I)
        out.append({"type": "line", "t0": snap(items[i]["start"]), "t1": snap(items[i]["end"]), "text": txt.replace("{", "{{")
                    .replace("}", "}}").replace("{{days}}", "{days}")})
        i += 1
    for e in out:
        e["t1"] = min(max(e["t1"], e["t0"] + 0.1), duration)
    return out


def learn_text(ref: str, tpl: dict, gemini) -> list[dict]:
    """One Gemini call per new template (free tier): timed on-screen text -> template events."""
    from google.genai import types
    small = Path(ref).with_suffix(".small.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", ref, "-vf", "scale=-2:480", "-c:v", "libx264", "-crf", "28",
                    "-an", str(small)], check=True)
    part = types.Part.from_bytes(data=small.read_bytes(), mime_type="video/mp4")
    res = gemini.generate_json([part, TEXT_PROMPT.format(duration=tpl["duration"], cuts=tpl["cuts"])], TEXT_SCHEMA,
                               temperature=0.1)
    items = res.get("items", []) if isinstance(res, dict) else []
    ys = [i["position_y"] for i in items if isinstance(i.get("position_y"), (int, float))]
    if ys:
        tpl.setdefault("text_style", {})["y"] = round(float(np.median(ys)), 3)
    size = (res or {}).get("text_size") if isinstance(res, dict) else None
    if size:
        tpl["text_style"]["line_size"] = {"small": 0.032, "medium": 0.042, "large": 0.06}[size]
        tpl["text_style"]["size"] = {"small": 0.045, "medium": 0.058, "large": 0.08}[size]
    return text_events(items, tpl["cuts"], tpl["duration"])


# ------------------------------------------------------------------ ranking / daily production
def template_score(tpl: dict, now: float | None = None) -> float:
    """Higher = more viral reference: views per hour since posting (fallback: views), outlier bonus."""
    import time
    views = float(tpl.get("views") or tpl.get("views_when_learned") or 0)
    age_h = max(1.0, ((now or time.time()) - float(tpl.get("created") or 0)) / 3600) if tpl.get("created") else None
    v = views / age_h if age_h else views / 500
    return v * (1 + 0.3 * float(tpl.get("outlier") or 1))


# ------------------------------------------------------------------ shot tags (AI, cached per footage file)
TAG_SCHEMA = {"type": "object", "properties": {"shots": {"type": "array", "items": {"type": "object", "properties": {
    "i": {"type": "integer"}, "iconic": {"type": "number"}, "ui_overlay": {"type": "boolean"},
    "what": {"type": "string"}}, "required": ["i", "iconic", "ui_overlay"]}}}, "required": ["shots"]}

TAG_PROMPT = """This image is a grid of numbered frames, one per shot of an official game trailer (the number is in the
yellow box in each tile's corner). For EVERY number rate the shot for a viral hype edit:
- iconic: 1-10 (10 = instantly recognisable, breathtaking or high-action: skyline/aerial, main characters' close-ups,
  explosions, chases, beach/party crowds; 1 = generic interior, dull filler, logo/rating card).
- ui_overlay: true if the frame shows phone / social-media / livestream / news-TV / chat / app interface, usernames,
  "Follow" buttons, captions or any other UI or text on top of the picture.
- what: 3-8 words describing that tile.
Numbers: 0..{last}."""


def _grid(src: str, shots: list[Shot], tile_w: int = 256, cols: int = 8) -> bytes:
    th = tile_w * 9 // 16
    rows = (len(shots) + cols - 1) // cols
    grid = np.zeros((rows * th, cols * tile_w, 3), np.uint8)
    for k, x in enumerate(shots):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{(x.start + x.end) / 2:.2f}", "-i", src, "-frames:v", "1",
                              "-vf", f"scale={tile_w}:{th}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                             capture_output=True).stdout
        if len(raw) == tile_w * th * 3:
            tile = np.frombuffer(raw, np.uint8).reshape(th, tile_w, 3).copy()
            cv2.rectangle(tile, (0, 0), (34, 22), (0, 220, 255), -1)
            cv2.putText(tile, str(k), (3, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
            r, c = divmod(k, cols)
            grid[r * th:(r + 1) * th, c * tile_w:(c + 1) * tile_w] = tile
    return cv2.imencode(".jpg", grid, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes()


def tag_shots(src: str, shots: list[Shot], tags_dir: Path, gemini=None) -> None:
    """Attach iconic score + UI flag to each shot. One free Gemini call per footage file (a numbered grid of the
    shots' middle frames, so every answer maps to exactly one shot), stored in the repo (tags_dir/<file>.json)
    and never repeated. Without Gemini the defaults stay (iconic 5, no UI)."""
    tf = tags_dir / (Path(src).stem + ".json")
    tags = json.loads(tf.read_text()) if tf.exists() else None
    if tags is None and gemini is not None and gemini.available() and shots:
        from google.genai import types
        try:
            res = gemini.generate_json([types.Part.from_bytes(data=_grid(src, shots), mime_type="image/jpeg"),
                                        TAG_PROMPT.format(last=len(shots) - 1)], TAG_SCHEMA, temperature=0.1)
            tags = {f"{shots[r['i']].start:.2f}": {"iconic": float(r["iconic"]), "ui": bool(r["ui_overlay"]),
                                                   "what": r.get("what", "")}
                    for r in (res or {}).get("shots", []) if 0 <= r.get("i", -1) < len(shots)}
            tf.parent.mkdir(parents=True, exist_ok=True)
            tf.write_text(json.dumps(tags, indent=0, ensure_ascii=False))
        except Exception:
            tags = None
    for x in shots:
        t = (tags or {}).get(f"{x.start:.2f}")
        if t:
            x.iconic, x.ui = t["iconic"], t["ui"]
