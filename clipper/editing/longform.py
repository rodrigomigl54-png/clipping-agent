"""Long-form (16:9) narrated videos: script.json + narration WAVs (+ word timings) + a shot plan -> 1920x1080 MP4.

* `align(script_text, whisper_words)` gives every script token a time (spelling from the script, timing from
  Whisper), so captions are spelled right even when Whisper mishears a name.
* `sentences(section)` splits a section on . ? ! and returns script sentences with times.
* `build_timeline` places each section's narration on one track (small pre/post gaps) and turns the plan's
  beats ({sentence index -> visual}) into absolute time ranges.
* `render` draws every frame: full shots (GTA V / GTA VI tag), split-screen pairs, number cards, info
  graphics over a blurred shot, captions (3-word chunks, numbers highlighted), source chip, section chip.
  Shots are read with ffmpeg (letterbox removed, never upscaled more than 2x), with a slow 4% push-in.

Plans live next to the script (content/longform/<id>/plan.py) and only reference footage + sentence indices.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

W, H, FPS = 1920, 1080, 30
ROOT = Path(__file__).resolve().parents[2]
RED = (40, 30, 225)          # BGR
PINK = (150, 70, 255)
GREY = (190, 190, 190)
YELLOW = (40, 210, 255)
PRE, POST = 0.35, 0.45       # silence before / after each section's narration


# ------------------------------------------------------------------ text timing
def _norm(t: str) -> str:
    t = t.lower().replace("vi", "6") if t.lower() in ("vi", "vi's") else t.lower()
    return re.sub(r"[^a-z0-9]", "", t)


NUM = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
       "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
       "fifteen": "15", "twenty": "20", "thirty": "30"}


def align(text: str, words: list[dict]) -> list[dict]:
    toks = text.split()
    a = [NUM.get(_norm(t), _norm(t)) for t in toks]
    b = [NUM.get(_norm(w["w"]), _norm(w["w"])) for w in words]
    times: list[tuple[float, float] | None] = [None] * len(toks)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            w = words[blk.b + k]
            times[blk.a + k] = (w["s"], w["e"])
    known = [i for i, x in enumerate(times) if x]
    for i in range(len(toks)):                 # interpolate the few tokens Whisper split or merged differently
        if times[i] is None:
            prev = max([k for k in known if k < i], default=None)
            nxt = min([k for k in known if k > i], default=None)
            s = times[prev][1] if prev is not None else 0.0
            e = times[nxt][0] if nxt is not None else s + 0.3
            span = [k for k in range(prev + 1 if prev is not None else 0, nxt if nxt is not None else len(toks))]
            j = span.index(i)
            step = (e - s) / max(1, len(span))
            times[i] = (s + j * step, s + (j + 1) * step)
    return [{"w": t, "s": round(x[0], 3), "e": round(x[1], 3)} for t, x in zip(toks, times)]


def sentences(tokens: list[dict]) -> list[dict]:
    out, cur = [], []
    for t in tokens:
        cur.append(t)
        if t["w"][-1:] in ".?!" or t["w"].endswith((".”", "?”", "!”")):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [{"t0": c[0]["s"], "t1": c[-1]["e"], "tokens": c, "text": " ".join(x["w"] for x in c)} for c in out]


# ------------------------------------------------------------------ footage
SRC = {"v:gp": "assets/footage/gta5/gameplay.mp4", "v:tr": "assets/footage/gta5/trailer.mp4",
       "v:of": "assets/footage/gta5/official.mp4", "v:ng": "assets/footage/gta5/nextgen.mp4",
       "6:t1": "assets/footage/gta6/trailer1.mp4", "6:t2": "assets/footage/gta6/trailer2.mp4",
       "6:fe": "assets/footage/gta6/features.mp4", "6:pl": "assets/footage/gta6/preload.mp4",
       "6:la": "assets/footage/gta6_launch/launch.mp4"}


LETTERBOX = {"v:of": 0.1, "v:ng": 0.1, "v:tr": 0.1}     # measured: 72/720 px bars top and bottom


@lru_cache(maxsize=None)
def _shots(src: str) -> list[dict]:
    p = ROOT / "data/shot_cache" / f"{Path(src).parent.name}__{Path(src).name}.shots.json"
    return json.loads(p.read_text()) if p.exists() else []


@lru_cache(maxsize=None)
def _probe(src: str) -> tuple[int, int, float]:
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                        "-of", "json", str(ROOT / src)], capture_output=True, text=True, check=True).stdout
    d = json.loads(o)
    return d["streams"][0]["width"], d["streams"][0]["height"], float(d["format"]["duration"])


def shot_info(ref: str) -> dict:
    """'6:la:46.33' -> {src, start, end, bar, cx, game}."""
    key, t = ref.rsplit(":", 1)
    src, t = SRC[key], float(t)
    sh = min(_shots(src), key=lambda s: abs(s["start"] - t), default=None)
    if sh and abs(sh["start"] - t) < 0.2:
        bar = sh.get("bar", 0.0)
        if key in LETTERBOX and bar < 0.05:          # cinematic bars the shot analysis missed
            bar = LETTERBOX[key]
        return {"src": src, "start": sh["start"], "end": sh["end"], "bar": bar, "cx": sh.get("cx", 0.5),
                "game": "V" if key.startswith("v") else "VI"}
    return {"src": src, "start": t, "end": t + 4.0, "bar": 0.0, "cx": 0.5, "game": "V" if key.startswith("v") else "VI"}


def read_frames(info: dict, dur: float, w: int, h: int, offset: float = 0.0):
    """Generator of BGR frames (w x h) for `dur` seconds of a shot; slows down (max 2x) when the shot is short."""
    sw, sh_, _ = _probe(info["src"])
    bar = info["bar"] if info["bar"] and info["bar"] < 0.2 else 0.0
    avail = max(0.3, info["end"] - info["start"] - 0.1 - offset)
    speed = max(0.5, min(1.0, avail / dur))
    vis_h = int(sh_ * (1 - 2 * bar)) // 2 * 2
    scale = max(w / sw, h / vis_h)
    if scale > 2.05:                             # never blow a source up past ~2x: keep the bars instead
        bar, vis_h = 0.0, sh_
        scale = max(w / sw, h / vis_h)
    cw, ch = int(round(w / scale)) // 2 * 2, int(round(h / scale)) // 2 * 2
    cw, ch = min(cw, sw), min(ch, vis_h)
    x = int(min(max(info["cx"] * sw - cw / 2, 0), sw - cw))
    y = int((sh_ - vis_h) / 2 + (vis_h - ch) / 2)
    vf = f"crop={cw}:{ch}:{x}:{y},scale={w}:{h}:flags=lanczos,setpts=PTS/{speed:.4f},fps={FPS}"
    read_len = min(dur * speed + 0.3, avail)                  # never run into the next shot (title cards etc.)
    n = int(round(dur * FPS))
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{info['start'] + 0.05 + offset:.3f}", "-i", str(ROOT / info["src"]),
                          "-t", f"{read_len:.3f}", "-vf", vf, "-an", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         stdout=subprocess.PIPE)
    last = np.zeros((h, w, 3), np.uint8)
    for _ in range(n):
        buf = p.stdout.read(w * h * 3)
        if len(buf) == w * h * 3:
            last = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        yield last
    p.stdout.close()
    p.wait()


# ------------------------------------------------------------------ drawing helpers
FONT = {"anton": str(ROOT / "assets/fonts/Anton-Regular.ttf"),
        "inter": "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
        "interx": "/usr/share/fonts/opentype/inter/InterDisplay-Black.otf"}


@lru_cache(maxsize=2048)
def text_rgba(text: str, font: str, size: int, color: tuple = (255, 255, 255), stroke: int = 0,
              shadow: bool = True) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont
    fp = FONT[font] if Path(FONT[font]).exists() else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    f = ImageFont.truetype(fp, size)
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    l, t, r, b = d.textbbox((0, 0), text, font=f, stroke_width=stroke)
    pad = int(size * 0.3)
    img = Image.new("RGBA", (r - l + 2 * pad, b - t + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((pad - l, pad - t), text, font=f, fill=(color[2], color[1], color[0], 255),
                             stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    a = np.array(img)
    out = cv2.cvtColor(a, cv2.COLOR_RGBA2BGRA)
    if shadow:
        sh = cv2.GaussianBlur(out[..., 3].astype(np.float32), (0, 0), size * 0.08)
        out[..., 3] = np.clip(np.maximum(out[..., 3].astype(np.float32), sh * 0.75), 0, 255).astype(np.uint8)
    return out


def over(frame: np.ndarray, img: np.ndarray, x: float, y: float, alpha: float = 1.0, anchor: str = "c") -> None:
    h, w = img.shape[:2]
    if anchor == "c":
        x, y = x - w / 2, y - h / 2
    elif anchor == "l":
        y = y - h / 2
    x, y = int(x), int(y)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    if x1 <= x0 or y1 <= y0 or alpha <= 0:
        return
    part = img[y0 - y:y1 - y, x0 - x:x1 - x]
    a = part[..., 3:4].astype(np.float32) / 255 * alpha
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (roi * (1 - a) + part[..., :3].astype(np.float32) * a).astype(np.uint8)


def box(frame, x0, y0, x1, y1, color, alpha=0.8, radius=14):
    x0, y0, x1, y1 = map(int, (x0, y0, x1, y1))
    ov = frame[max(0, y0):y1, max(0, x0):x1]
    if ov.size == 0:
        return
    mask = np.zeros(ov.shape[:2], np.uint8)
    cv2.rectangle(mask, (radius, 0), (mask.shape[1] - radius, mask.shape[0]), 255, -1)
    cv2.rectangle(mask, (0, radius), (mask.shape[1], mask.shape[0] - radius), 255, -1)
    for cx_, cy_ in ((radius, radius), (mask.shape[1] - radius, radius), (radius, mask.shape[0] - radius),
                     (mask.shape[1] - radius, mask.shape[0] - radius)):
        cv2.circle(mask, (cx_, cy_), radius, 255, -1)
    a = (mask.astype(np.float32) / 255 * alpha)[..., None]
    ov[:] = (ov.astype(np.float32) * (1 - a) + np.array(color, np.float32) * a).astype(np.uint8)


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def pop(t: float, t0: float, dur: float = 0.25) -> float:
    """0 before t0, eases to 1 over `dur`."""
    return ease((t - t0) / dur) if t >= t0 else 0.0


# ------------------------------------------------------------------ timeline
@dataclass
class Beat:
    t0: float
    t1: float
    spec: dict
    section: str
    label: str = ""


@dataclass
class Timeline:
    beats: list[Beat] = field(default_factory=list)
    words: list[dict] = field(default_factory=list)          # absolute script-aligned tokens
    sections: list[dict] = field(default_factory=list)       # id, label, t0, t1, card_t1
    audio: list[tuple[str, float]] = field(default_factory=list)
    duration: float = 0.0


def build_timeline(script: dict, vo_dir: Path, plan: dict, tail: float = 10.0) -> Timeline:
    tl = Timeline()
    t = 0.0
    for sec in script["sections"]:
        sid = sec["id"]
        meta = json.loads((vo_dir / f"{sid}.wav.json").read_text())
        toks = align(sec["text"], meta["words"])
        sents = sentences(toks)
        start = t + PRE
        tl.audio.append((str(vo_dir / f"{sid}.wav"), start))
        for x in toks:
            tl.words.append({**x, "s": x["s"] + start, "e": x["e"] + start, "section": sid})
        end = start + meta["dur"] + POST
        if sid == script["sections"][-1]["id"]:
            end += tail
        beats = plan[sid]
        keys = sorted(beats)
        bounds = []
        for i, k in enumerate(keys):
            b0 = t if i == 0 else start + (sents[k]["t0"] if k < len(sents) else meta["dur"]) - 0.12
            bounds.append(b0)
        bounds.append(end)
        for i, k in enumerate(keys):
            tl.beats.append(Beat(bounds[i], bounds[i + 1], beats[k], sid, sec.get("label", "")))
        card_t1 = None
        for b in tl.beats:
            if b.section == sid and b.spec.get("card"):
                card_t1 = b.t1
        tl.sections.append({"id": sid, "label": sec.get("label", ""), "t0": t, "t1": end, "card_t1": card_t1,
                            "sents": [{**s, "t0": s["t0"] + start, "t1": s["t1"] + start} for s in sents]})
        t = end
    tl.duration = t
    return tl


def word_time(tl: Timeline, section: str, token: str, nth: int = 1) -> float:
    k = 0
    for w in tl.words:
        if w["section"] == section and _norm(w["w"]).startswith(_norm(token)):
            k += 1
            if k == nth:
                return w["s"]
    raise KeyError(f"{token!r} not in section {section}")


# ------------------------------------------------------------------ captions
HIGHLIGHT = re.compile(r"^(\d[\d,]*|gta|vi|v|six|thirteen|fifteen|two|three|one|leonida|vice|rockstar|police|cops|focus)$", re.I)


def caption_chunks(tl: Timeline, size: int = 3) -> list[dict]:
    out = []
    for sec in tl.sections:
        for s in sec["sents"]:
            toks = s["tokens"]
            for i in range(0, len(toks), size):
                part = toks[i:i + size]
                t0 = part[0]["s"] + [x for x in tl.audio if Path(x[0]).stem == sec["id"]][0][1]
                t1 = part[-1]["e"] + [x for x in tl.audio if Path(x[0]).stem == sec["id"]][0][1]
                out.append({"t0": t0, "t1": t1 + 0.08, "words": [p["w"] for p in part], "section": sec["id"]})
    for a, b in zip(out, out[1:]):                       # no flicker between consecutive chunks
        if 0 < b["t0"] - a["t1"] < 0.25:
            a["t1"] = b["t0"]
    return out


def draw_caption(frame: np.ndarray, ch: dict, t: float) -> None:
    words = [w.strip() for w in ch["words"]]
    imgs = []
    for w in words:
        clean = w.strip(".,!?:;\"“”")
        col = YELLOW if HIGHLIGHT.match(clean.replace(",", "")) else (255, 255, 255)
        imgs.append(text_rgba(w.upper(), "interx", 58, col, stroke=5))
    gap = 16
    total = sum(i.shape[1] for i in imgs) + gap * (len(imgs) - 1)
    x = (W - total) / 2
    k = pop(t, ch["t0"], 0.12)
    y = H - 150 + (1 - k) * 14
    for im in imgs:
        over(frame, im, x, y, k, anchor="l")
        x += im.shape[1] + gap


# ------------------------------------------------------------------ graphics
def blur_bg(frame: np.ndarray, dark: float = 0.45) -> np.ndarray:
    small = cv2.resize(frame, (W // 8, H // 8), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), 3)
    return (cv2.resize(small, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32) * dark).astype(np.uint8)


def chip(frame, text, x, y, color=(30, 30, 30), fg=(255, 255, 255), size=30, alpha=1.0, anchor="l"):
    im = text_rgba(text, "inter", size, fg, shadow=False)
    w, h = im.shape[1], im.shape[0]
    if anchor == "c":
        x = x - w / 2
    box(frame, x, y - h / 2, x + w, y + h / 2, color, 0.85 * alpha, radius=10)
    over(frame, im, x, y, alpha, anchor="l")


def g_title(frame, t, b, tl):
    k = pop(t, b.t0, 0.35)
    lines = b.spec["lines"]
    sizes = [150 if len(lines) == 1 else 120] + [86] * (len(lines) - 1)
    total = sum(s * 1.2 for s in sizes)
    y = H / 2 - total / 2 + sizes[0] * 0.6
    for i, (ln, s) in enumerate(zip(lines, sizes)):
        col = RED if i == len(lines) - 1 and len(lines) > 1 else (255, 255, 255)
        im = text_rgba(ln, "anton", s, col)
        kk = pop(t, b.t0 + 0.15 * i, 0.35)
        sc = 1.12 - 0.12 * kk
        im2 = cv2.resize(im, None, fx=sc, fy=sc) if abs(sc - 1) > 0.005 else im
        over(frame, im2, W / 2, y + (1 - kk) * 30, kk * k)
        y += s * 1.2


def g_stamp(frame, t, b, tl):
    k = pop(t, b.t0, 0.3)
    im = text_rgba(b.spec["text"], "anton", 110, (255, 255, 255))
    pad = 40
    x0, y0 = W / 2 - im.shape[1] / 2 - pad, H / 2 - im.shape[0] / 2 - 30
    box(frame, x0, y0, x0 + im.shape[1] + 2 * pad, y0 + im.shape[0] + 30, RED, 0.9 * k, radius=18)
    sc = 1.25 - 0.25 * k
    im2 = cv2.resize(im, None, fx=sc, fy=sc)
    over(frame, im2, W / 2, H / 2 - 15, k)
    if b.spec.get("sub"):
        over(frame, text_rgba(b.spec["sub"], "inter", 40, (235, 235, 235)), W / 2, H / 2 + im.shape[0] / 2 + 40,
             pop(t, b.t0 + 0.3, 0.3))


COLORS = {"pink": PINK, "red": RED, "grey": (90, 90, 90)}


def g_items(frame, t, b, tl):
    sp = b.spec
    if sp.get("title"):
        over(frame, text_rgba(sp["title"], "anton", 70, (255, 255, 255)), W / 2, 180, pop(t, b.t0, 0.3))
    items, cols = sp["items"], sp.get("cols", 3)
    rows, row, n = [], [], 0
    for it in items:
        span = cols if it.get("wide") else 1
        if n + span > cols:
            rows.append(row)
            row, n = [], 0
        row.append(it)
        n += span
    rows.append(row)
    cw, chh, gap = 520 if cols <= 2 else (440 if cols == 3 else 400), 120, 28
    y = H / 2 - (len(rows) * (chh + gap) - gap) / 2 + chh / 2 + 30
    for r in rows:
        widths = [(cw * cols + gap * (cols - 1)) if it.get("wide") else cw for it in r]
        x = W / 2 - (sum(widths) + gap * (len(r) - 1)) / 2
        for it, wdt in zip(r, widths):
            t_on = word_time(tl, b.section, it["on"], it.get("nth", 1)) - 0.05
            k = pop(t, t_on, 0.22)
            off = it.get("off") and t >= word_time(tl, b.section, it["off"]) - 0.05
            col = COLORS.get(it.get("color"), (35, 35, 40))
            if k > 0:
                yy = y + (1 - k) * 25
                box(frame, x, yy - chh / 2, x + wdt, yy + chh / 2, (60, 60, 60) if off else col, 0.88 * k, radius=16)
                cv2.rectangle(frame, (int(x), int(yy - chh / 2)), (int(x + 8), int(yy + chh / 2)), PINK if not off else (90, 90, 90), -1)
                im = text_rgba(it["text"], "anton", 54, (150, 150, 150) if off else (255, 255, 255))
                if im.shape[1] > wdt - 40:
                    im = cv2.resize(im, None, fx=(wdt - 40) / im.shape[1], fy=(wdt - 40) / im.shape[1])
                over(frame, im, x + wdt / 2, yy, k)
                if off:
                    cv2.line(frame, (int(x + 20), int(yy)), (int(x + wdt - 20), int(yy)), RED, 8)
                    if it.get("offnote"):
                        over(frame, text_rgba(it["offnote"], "inter", 30, (255, 255, 255)), x + wdt / 2, yy + chh / 2 + 28, 1)
                if it.get("note_on") and t >= word_time(tl, b.section, it["note_on"]) - 0.05:
                    chip(frame, it["note"], x + wdt / 2, yy + chh / 2 + 30, color=(60, 160, 60), size=30, anchor="c")
            x += wdt + gap
        y += chh + gap


def g_counter(frame, t, b, tl):
    sp = b.spec
    over(frame, text_rgba(sp["title"], "anton", 76, (255, 255, 255)), W / 2, 200, pop(t, b.t0, 0.3))
    vmax = max(x["value"] for x in sp["bars"])
    for i, bar in enumerate(sp["bars"]):
        t_on = word_time(tl, b.section, bar["on"]) - 0.1
        k = ease((t - t_on) / 1.4) if t >= t_on else 0
        if k <= 0:
            continue
        y = 430 + i * 230
        full = 1300 * bar["value"] / vmax
        col = COLORS[bar["color"]] if bar["color"] != "grey" else (150, 150, 150)
        box(frame, 300, y - 55, 300 + max(24, full * k), y + 55, col, 0.95, radius=14)
        lab = text_rgba(bar["label"], "anton", 58, (255, 255, 255))
        over(frame, lab, 280 - lab.shape[1], y, 1, anchor="l")
        val = text_rgba(f"{int(bar['value'] * k):,}", "anton", 74, (255, 255, 255))
        over(frame, val, 320 + max(24, full * k), y, 1, anchor="l")


def g_stars(frame, t, b, tl):
    over(frame, text_rgba(b.spec["title"], "anton", 76, (255, 255, 255)), W / 2, 330, pop(t, b.t0, 0.3))
    t_on = word_time(tl, b.section, b.spec["on"]) - 0.4
    for i in range(6):
        k = pop(t, t_on + 0.18 * i, 0.2)
        cx, cy, r = W / 2 + (i - 2.5) * 190, 560, 78
        pts = []
        for j in range(10):
            ang = -np.pi / 2 + j * np.pi / 5
            rr = r if j % 2 == 0 else r * 0.45
            pts.append([cx + rr * np.cos(ang), cy + rr * np.sin(ang)])
        pts = np.array(pts, np.int32)
        cv2.polylines(frame, [pts], True, (200, 200, 200), 4, cv2.LINE_AA)
        if k > 0:
            ov = frame.copy()
            cv2.fillPoly(ov, [pts], (255, 255, 255), cv2.LINE_AA)
            cv2.addWeighted(ov, k, frame, 1 - k, 0, frame)


GRAPHICS = {"title": g_title, "stamp": g_stamp, "items": g_items, "counter": g_counter, "stars": g_stars, "end": g_title}


# ------------------------------------------------------------------ frame sources per beat
@lru_cache(maxsize=None)
def _ui_tags(src: str) -> dict:
    p = ROOT / "config/footage_tags" / Path(src).parent.name / (Path(src).stem + ".json")
    return json.loads(p.read_text()) if p.exists() else {}


def expand(ref: str, dur: float, allow_ui: bool = False) -> list[tuple[dict, float]]:
    """A slot longer than its shot continues with the following shots of the same video (Rockstar's own edit
    order), skipping title cards, logos and UI shots; the last piece may slow down up to 2x."""
    first = shot_info(ref)
    shots = _shots(first["src"])
    idx = min(range(len(shots)), key=lambda i: abs(shots[i]["start"] - first["start"])) if shots else None
    out, remaining, i = [], dur, idx
    info = first
    while remaining > 0.04:
        avail = max(0.3, info["end"] - info["start"] - 0.15)
        if remaining <= avail * 2 and (remaining <= avail + 0.4 or idx is None):
            out.append((info, remaining))
            break
        take = min(avail, remaining)
        out.append((info, take))
        remaining -= take
        nxt = None
        while i is not None and i + 1 < len(shots):
            i += 1
            c = shots[i]
            tag = _ui_tags(first["src"]).get(f"{c['start']:.2f}", {})
            if c.get("usable", True) and (allow_ui or not tag.get("ui")) and c["end"] - c["start"] > 0.45:
                nxt = c
                break
        if nxt is None:                       # end of the video: stretch what we have
            info, last = out.pop()
            out.append((info, last + remaining))
            break
        info = {"src": first["src"], "start": nxt["start"], "end": nxt["end"], "bar": nxt.get("bar", 0.0),
                "cx": nxt.get("cx", 0.5), "game": first["game"]}
    return out

def _game_tag(frame, game: str, x: float, y: float = 70):
    if game == "V":
        chip(frame, "GTA V · 2013", x, y, color=(20, 20, 20), size=40)
    else:
        chip(frame, "GTA VI · 2026", x, y, color=PINK, size=40)


def beat_frames(b: Beat):
    """Yields (frame, overlay_fn) for every frame of the beat."""
    sp, dur = b.spec, b.t1 - b.t0
    n = int(round(dur * FPS))
    if "split" in sp:
        pairs = sp["split"]
        per = dur / len(pairs)
        for l, r in pairs:
            li, ri = shot_info(l), shot_info(r)

            def side(ref):
                for inf, d in expand(ref, per):
                    yield from read_frames(inf, d, W // 2 - 4, H)
            gl, gr = side(l), side(r)
            for fl, fr in zip(gl, gr):
                f = np.zeros((H, W, 3), np.uint8)
                f[:, :W // 2 - 4] = fl
                f[:, W // 2 + 4:] = fr
                f[:, W // 2 - 4:W // 2 + 4] = (255, 255, 255)
                yield f, ("split", li["game"], ri["game"])
        return
    refs = sp.get("shots") or [sp.get("bg")]
    per = dur / len(refs)
    def pieces(ref):
        for inf, d in expand(ref, per, allow_ui=True if sp.get("ui") else False):
            yield from read_frames(inf, d, W, H)
    for ref in refs:
        info = shot_info(ref)
        frames = pieces(ref)
        for i, f in enumerate(frames):
            z = 1.0 + 0.04 * (i / max(1, per * FPS))          # slow push-in
            if z > 1.001:
                f = cv2.resize(f, None, fx=z, fy=z, interpolation=cv2.INTER_LINEAR)
                y0, x0 = (f.shape[0] - H) // 2, (f.shape[1] - W) // 2
                f = f[y0:y0 + H, x0:x0 + W]
            if "g" in sp or sp.get("card"):
                f = blur_bg(f, 0.42 if "g" in sp else 0.35)
            yield np.ascontiguousarray(f), ("full", info["game"])


# ------------------------------------------------------------------ render
def render(tl: Timeline, out: Path, section_labels: dict) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    silent = out.with_name(out.stem + "_video.mp4")
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                            str(silent)], stdin=subprocess.PIPE)
    caps = caption_chunks(tl)
    ci = 0
    fi = 0
    total = int(round(tl.duration * FPS))
    for b in tl.beats:
        sec = next(s for s in tl.sections if s["id"] == b.section)
        n_target = int(round(b.t1 * FPS)) - fi
        produced = 0
        for f, kind in beat_frames(b):
            if produced >= n_target:
                break
            t = fi / FPS
            f = f.copy()
            sp = b.spec
            if sp.get("card"):
                num = str(int(b.section))
                k = pop(t, b.t0, 0.3)
                im = text_rgba(f"#{num}", "anton", 330, RED)
                sc = 1.3 - 0.3 * k
                over(f, cv2.resize(im, None, fx=sc, fy=sc), W / 2, H / 2 - 70, k)
                lab = text_rgba(section_labels.get(b.section, ""), "anton", 96, (255, 255, 255))
                over(f, lab, W / 2, H / 2 + 150 + (1 - pop(t, b.t0 + 0.2, 0.3)) * 20, pop(t, b.t0 + 0.2, 0.3))
            elif "g" in sp:
                GRAPHICS[sp["g"]](f, t, b, tl)
            else:
                if kind[0] == "split":
                    _game_tag(f, kind[1], 40)
                    _game_tag(f, kind[2], W // 2 + 40)
                else:
                    _game_tag(f, kind[1], 40)
                if sp.get("kw"):
                    k = pop(t, b.t0 + 0.15, 0.25)
                    im = text_rgba(sp["kw"], "anton", 80, (255, 255, 255))
                    ky = H - 290                       # lower third, above the captions: never over faces
                    box(f, W / 2 - im.shape[1] / 2 - 10, ky - im.shape[0] / 2 + 10, W / 2 + im.shape[1] / 2 + 10,
                        ky + im.shape[0] / 2 - 10, RED, 0.9 * k, radius=12)
                    over(f, im, W / 2, ky + (1 - k) * 20, k)
            # section chip (top right) once the number card is over
            if b.section not in ("hook", "outro") and not sp.get("card") and sec["card_t1"] and t > sec["card_t1"]:
                txt = f"#{int(b.section)}  {section_labels.get(b.section, '')}"
                im = text_rgba(txt, "inter", 28, (255, 255, 255), shadow=False)
                box(f, W - 40 - im.shape[1], 60 - im.shape[0] / 2, W - 40, 60 + im.shape[0] / 2, (25, 25, 25), 0.85, 10)
                over(f, im, W - 40 - im.shape[1], 60, 1, anchor="l")
            if sp.get("src"):
                k = pop(t, b.t0 + 0.4, 0.3)
                chip(f, sp["src"], 40, H - 60, color=(20, 20, 20), fg=(220, 220, 220), size=24, alpha=k)
            while ci < len(caps) and caps[ci]["t1"] < t:
                ci += 1
            if ci < len(caps) and caps[ci]["t0"] <= t and not sp.get("card") and sp.get("g") not in ("title", "end"):
                draw_caption(f, caps[ci], t)
            enc.stdin.write(f.tobytes())
            fi += 1
            produced += 1
        while produced < n_target:                       # safety: pad with the last frame
            enc.stdin.write(f.tobytes())
            fi += 1
            produced += 1
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("encode failed")
    # audio: narration placed on the timeline + a soft whoosh on each number card
    inputs, filters = [], []
    for i, (wav, st) in enumerate(tl.audio):
        inputs += ["-i", wav]
        filters.append(f"[{i}:a]aresample=48000,adelay={int(st * 1000)}|{int(st * 1000)}[a{i}]")
    k = len(tl.audio)
    whoosh_t = [s["t0"] + PRE - 0.05 for s in tl.sections if s["card_t1"]]
    for j, wt in enumerate(whoosh_t):
        inputs += ["-f", "lavfi", "-t", "0.6", "-i", "anoisesrc=color=pink:amplitude=0.25:sample_rate=48000"]
        filters.append(f"[{k + j}:a]highpass=f=400,lowpass=f=3500,afade=t=in:d=0.25,afade=t=out:st=0.3:d=0.3,volume=0.35,"
                       f"adelay={int(wt * 1000)}|{int(wt * 1000)}[w{j}]")
    mix = "".join(f"[a{i}]" for i in range(k)) + "".join(f"[w{j}]" for j in range(len(whoosh_t)))
    filters.append(f"{mix}amix=inputs={k + len(whoosh_t)}:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[out]")
    narr = out.with_name(out.stem + "_audio.m4a")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]",
                    "-t", f"{tl.duration:.3f}", "-c:a", "aac", "-b:a", "192k", str(narr)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(narr), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart", str(out)], check=True)
    silent.unlink(missing_ok=True)
    return {"file": str(out), "duration": round(tl.duration, 2), "audio": str(narr)}


def chapters(tl: Timeline, labels: dict) -> list[str]:
    out = []
    for s in tl.sections:
        m, sec = divmod(int(s["t0"]), 60)
        name = "Intro" if s["id"] == "hook" else ("The biggest difference" if s["id"] == "outro" else f"#{int(s['id'])} {labels[s['id']].title()}")
        out.append(f"{m}:{sec:02d} {name}")
    return out


def srt(tl: Timeline) -> str:
    def ts(x):
        h, r = divmod(x, 3600)
        m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"
    lines, k = [], 1
    for sec in tl.sections:
        st = [x for x in tl.audio if Path(x[0]).stem == sec["id"]][0][1]
        for s in sec["sents"]:
            lines += [str(k), f"{ts(s['t0'])} --> {ts(s['t1'])}", s["text"], ""]
            k += 1
    return "\n".join(lines)


def check_plan(tl: Timeline) -> list[str]:
    """Shots that would need more than 2x slow motion to fill their slot."""
    bad = []
    for b in tl.beats:
        sp, dur = b.spec, b.t1 - b.t0
        groups = [[p] for p in (sp.get("shots") or [sp.get("bg")])] if "split" not in sp else [list(p) for p in sp["split"]]
        per = dur / len(groups)
        for g in groups:
            for ref in g:
                parts = expand(ref, per)
                for inf, d in parts:
                    if d > (inf["end"] - inf["start"] - 0.15) * 2 + 0.05:
                        bad.append(f"{b.section} @{b.t0:.1f}: {ref} stretched {d:.1f}s over {inf['end'] - inf['start']:.1f}s")
    return bad
