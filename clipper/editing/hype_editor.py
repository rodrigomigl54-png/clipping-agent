"""Beat-synced hype edit engine (GTA 6 trailer / gameplay montages).

Recipe learned from the reference edits (docs/GTA6_PLAYBOOK.md, frame-accurate measurements in
config/style_examples/gta6_hype_measurements.json):

    opener (2.3-3 s, one cinematic shot while the music builds)
    -> first cut ON the drop
    -> every shot exactly 1 (or 2) beats long, each starting on its motion peak
    -> shot types alternate (day/night, warm/neon, calm/action) so every cut is a visible change
    -> flashes on the kicks, one short line of text / countdown, hard cut to black on the last beat.

The music itself is added by the owner when uploading (TikTok sound). So the edit is cut on the beat grid
of a measured reference edit whose sound is known: if the owner adds that sound from 0:00, every cut lands
on its beat. The output is silent (no trailer audio fighting the music) and comes with music instructions.

Quality: the picture is a 4:5 crop of the source scaled to 1080 px wide (1.25x from 1080p, sharp). Text sits
only in the black bands above/below the picture, never on the content. Text cards, logos, black frames and
soft shots are rejected before selection.
"""
from __future__ import annotations

import json
import math
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

import cv2
import numpy as np

OUT_W, OUT_H, FPS = 1080, 1920, 30
PIC_H = 1350                       # 4:5 picture, bands of 285 px above/below for text
AN_W, AN_H, AN_FPS = 320, 180, 15  # analysis resolution / rate
MIN_OPENER_SPEED = 0.6            # opener may be slowed to 0.6x (motion-interpolated)


# ------------------------------------------------------------------ templates (measured beat grids)
@dataclass
class BeatTemplate:
    id: str
    sound: str
    sound_author: str
    reference: str
    bpm: float
    cuts: list[float]              # cut times (s) of the reference edit = beat positions of the sound
    duration: float
    flashes: list[float] = field(default_factory=list)

    @property
    def drop(self) -> float:
        return self.cuts[0]


def load_templates(measurements: Path, meta: dict[str, dict] | None = None) -> dict[str, BeatTemplate]:
    """Build beat templates from the measured reference edits (only beat-locked ones: >=80% cuts on beat)."""
    raw = json.loads(measurements.read_text())
    out = {}
    for key, m in raw.items():
        if not isinstance(m, dict) or "cuts" not in m:
            continue
        if max(m.get("cuts_on_beat", 0), m.get("cuts_on_half_beat", 0)) < 0.8:
            continue
        info = (meta or {}).get(key, {})
        out[key] = BeatTemplate(id=key, sound=info.get("sound", "?"), sound_author=info.get("author", "?"),
                                reference=info.get("reference", key), bpm=m["bpm"], cuts=list(m["cuts"]),
                                duration=m["dur"], flashes=list(m.get("flashes", [])))
    return out


# ------------------------------------------------------------------ shot analysis
@dataclass
class Shot:
    src: str
    start: float
    end: float
    motion: float          # mean frame-to-frame change (0-1)
    peak: float            # time of strongest motion inside the shot
    bright: float          # mean luma 0-255
    sat: float             # mean saturation 0-255
    hue: float             # dominant hue 0-180
    sharp: float           # Laplacian variance at analysis size
    detail: float          # fraction of pixels with edges (text cards / logos / black are low)
    cx: float              # horizontal centre of interest 0-1 (for the 4:5 crop)
    faces: int = 0         # faces found in the mid frame (character shot vs scenery)
    bar: float = 0.0       # cinematic black bar height (fraction of frame height, top and bottom)
    iconic: float = 5.0    # 1-10: how iconic / wow the shot is (AI tag, cached per footage file)
    ui: bool = False       # phone / social-media / chat / HUD overlay inside the trailer shot
    usable: bool = True
    reason: str = ""

    @property
    def length(self) -> float:
        return self.end - self.start


def _frames(path: str, w: int = AN_W, h: int = AN_H, fps: int = AN_FPS):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo",
           "-pix_fmt", "bgr24", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = w * h * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    p.wait()


def analyze_shots(path: str | Path, cut_thr: float = 0.45, min_len: float = 0.4) -> list[Shot]:
    path = str(path)
    feats, hists, prev = [], [], None
    for fr in _frames(path):
        hsv = cv2.cvtColor(fr, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        h = cv2.calcHist([hsv], [0, 1, 2], None, [12, 6, 6], [0, 180, 0, 256, 0, 256])
        cv2.normalize(h, h)
        hists.append(h)
        diff = cv2.absdiff(gray, prev) if prev is not None else np.zeros_like(gray)
        edges = cv2.Canny(gray, 60, 140)
        col = diff.astype(np.float32).mean(0) + edges.astype(np.float32).mean(0) * 0.3
        feats.append({
            "motion": float(diff.mean()) / 255.0,
            "bright": float(gray.mean()), "sat": float(hsv[..., 1].mean()),
            "hue": float(np.median(hsv[..., 0][hsv[..., 1] > 60])) if (hsv[..., 1] > 60).any() else -1.0,
            "sharp": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
            "detail": float((edges > 0).mean()), "col": col,
        })
        prev = gray
    if not feats:
        return []
    # cuts: histogram distance spike (also catches hard luminance changes)
    cuts = [0]
    for i in range(1, len(hists)):
        d = cv2.compareHist(hists[i - 1], hists[i], cv2.HISTCMP_BHATTACHARYYA)
        if d > cut_thr and i - cuts[-1] >= 3:
            cuts.append(i)
    cuts.append(len(feats))
    shots = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        t0, t1 = a / AN_FPS, b / AN_FPS
        if t1 - t0 < min_len:
            continue
        seg = feats[a + 1:b] or feats[a:b]       # skip the cut frame itself (its diff is the cut)
        mot = np.array([f["motion"] for f in seg])
        sm = np.convolve(mot, np.ones(3) / 3, mode="same") if len(mot) >= 3 else mot
        peak = t0 + (int(np.argmax(sm)) + 1) / AN_FPS
        col = np.convolve(np.sum([f["col"] for f in seg], axis=0), np.ones(31) / 31, mode="same")
        centroid = float((col * np.arange(len(col))).sum() / col.sum() / len(col)) if col.sum() > 0 else 0.5
        cx = 0.5 + 0.7 * (centroid - 0.5)          # centre prior: action is rarely at the very edge
        hues = [f["hue"] for f in seg if f["hue"] >= 0]
        s = Shot(src=path, start=t0, end=t1, motion=float(mot.mean()), peak=peak,
                 bright=float(np.mean([f["bright"] for f in seg])), sat=float(np.mean([f["sat"] for f in seg])),
                 hue=float(np.median(hues)) if hues else -1.0, sharp=float(np.median([f["sharp"] for f in seg])),
                 detail=float(np.median([f["detail"] for f in seg])), cx=cx)
        s.reason = reject_reason(s.bright, min(f["bright"] for f in seg), s.detail, s.motion, s.sharp)
        s.usable = not s.reason
        shots.append(s)
    _face_centres(path, shots)
    return shots


def reject_reason(bright: float, bright_min: float, detail: float, motion: float, sharp: float) -> str:
    """Why a shot cannot be used in a hype edit ('' = usable). Thresholds measured on official trailers."""
    if bright < 28 or bright_min < 12:
        return "black / fade"
    if detail < 0.035 or (motion < 0.012 and detail < 0.07):
        return "text card / flat frame"
    if sharp / max(detail, 1e-3) > 12500:
        return "logo / text overlay"       # sharpness comes from lettering, not from the picture
    if sharp < 60:
        return "soft / blurry"
    return ""


def letterbox_bar(img: np.ndarray, thr: float = 14.0) -> float:
    """Height of the black bars at top/bottom (fraction of height, the smaller of the two, rounded down)."""
    rows = img.reshape(img.shape[0], -1).astype(np.float32)
    mean, mx = rows.mean(1), rows.max(1)
    H = img.shape[0]

    def run(order) -> int:
        n = 0
        for i in order:
            if mean[i] < thr and mx[i] < 60:
                n += 1
            else:
                break
        return n
    top, bot = run(range(H)), run(range(H - 1, -1, -1))
    b = min(top, bot) / H
    return round(b, 3) if b >= 0.03 else 0.0


def _face_centres(path: str, shots: list[Shot]) -> None:
    """Centre the crop on the biggest face of character shots (mid frame, 640x360)."""
    from ..detection.visual_analyzer import detect_faces
    for s in shots:
        if not s.usable:
            continue
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{(s.start + s.end) / 2:.2f}", "-i", path,
                              "-frames:v", "1", "-vf", "scale=640:360", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(raw) != 640 * 360 * 3:
            continue
        img = np.frombuffer(raw, np.uint8).reshape(360, 640, 3)
        s.bar = letterbox_bar(img)
        faces = detect_faces(img, 0.08)
        if faces:
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            s.cx = (x + w / 2) / 640
            s.faces = len(faces)


# ------------------------------------------------------------------ selection
@dataclass
class Slot:
    t0: float
    t1: float
    kind: str                     # opener | beat | black
    shot: Shot | None = None
    src_start: float = 0.0
    flash: bool = False
    speed: float = 1.0            # <1 = slow motion (opener only, frame-interpolated)

    @property
    def dur(self) -> float:
        return self.t1 - self.t0


def _score(s: Shot) -> float:
    return (min(s.sharp, 900) / 900) * 1.2 + min(s.motion * 12, 1.0) * 1.4 + (s.sat / 255) * 0.6 + \
        min(s.detail * 6, 1.0) * 0.6


def _similar(a: Shot, b: Shot) -> bool:
    dh = min(abs(a.hue - b.hue), 180 - abs(a.hue - b.hue)) if a.hue >= 0 and b.hue >= 0 else 0
    return abs(a.bright - b.bright) < 18 and dh < 12


def plan_slots(tpl: BeatTemplate, shots: list[Shot]) -> list[Slot]:
    times = [0.0] + tpl.cuts + [tpl.duration]
    slots = []
    for i, (a, b) in enumerate(zip(times[:-1], times[1:])):
        kind = "opener" if i == 0 else ("black" if i == len(times) - 2 and b - a < 0.3 else "beat")
        slots.append(Slot(a, b, kind, flash=any(abs(f - a) < 0.05 for f in tpl.flashes)))
    pool = sorted([s for s in shots if s.usable], key=_score, reverse=True)
    used: set[tuple[str, float]] = set()
    prev: Shot | None = None
    for sl in slots:
        if sl.kind == "black":
            continue
        need = sl.dur + 0.1
        if sl.kind == "opener":     # cinematic: sharp, bright-ish, calm camera; may run in light slow motion
            cands = sorted([s for s in pool if s.length >= need * MIN_OPENER_SPEED],
                           key=lambda s: (min(s.sharp, 900) / 900) + min(s.detail * 6, 1) + s.bright / 255
                           - min(s.motion * 12, 1) * 0.3, reverse=True)
        else:
            cands = [s for s in pool if s.length >= need]
        choice = next((s for s in cands if (s.src, s.start) not in used and not (prev and _similar(s, prev))), None) \
            or next((s for s in cands if (s.src, s.start) not in used), None)
        if choice is None:
            raise ValueError(f"not enough usable shots for a {sl.dur:.2f}s slot")
        used.add((choice.src, choice.start))
        sl.shot = choice
        if sl.kind == "opener":
            sl.speed = min(1.0, (choice.length - 0.1) / sl.dur)
            sl.src_start = choice.start + max(0.0, (choice.length - 0.1 - sl.dur * sl.speed) / 2) * 0.3 + 0.05
        else:                       # start just before the motion peak: shot is already moving at the cut
            sl.src_start = min(max(choice.start + 0.05, choice.peak - 0.12), choice.end - sl.dur - 0.05)
        prev = choice
    return slots


# ------------------------------------------------------------------ rendering
def _font(size: int) -> "ImageFont.FreeTypeFont":
    from PIL import ImageFont
    for p in ("/usr/share/fonts/opentype/inter/InterDisplay-Black.otf", "/usr/share/fonts/opentype/inter/Inter-Black.otf",
              "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf", "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def text_layer(text: str, size: int, color=(255, 255, 255), max_w: int = OUT_W - 120) -> np.ndarray:
    """RGBA image of one centred line (shrinks to fit)."""
    from PIL import Image, ImageDraw
    while True:
        f = _font(size)
        x0, y0, x1, y1 = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=f)
        if x1 - x0 <= max_w or size <= 28:
            break
        size = int(size * 0.92)
    img = Image.new("RGBA", (x1 - x0 + 20, y1 - y0 + 20), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((10 - x0, 10 - y0), text, font=f, fill=(*color, 255))
    return np.array(img)


def _blend(frame: np.ndarray, layer: np.ndarray, cy: int, scale: float = 1.0, alpha: float = 1.0) -> None:
    if scale != 1.0:
        layer = cv2.resize(layer, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    h, w = layer.shape[:2]
    x, y = (OUT_W - w) // 2, cy - h // 2
    y0, y1, x0, x1 = max(0, y), min(OUT_H, y + h), max(0, x), min(OUT_W, x + w)
    if y1 <= y0 or x1 <= x0:
        return
    part = layer[y0 - y:y1 - y, x0 - x:x1 - x]
    a = part[..., 3:4].astype(np.float32) / 255 * alpha
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (roi * (1 - a) + part[..., :3][..., ::-1].astype(np.float32) * a).astype(np.uint8)


def _grade(img: np.ndarray) -> np.ndarray:
    """Hype look: a bit more contrast and saturation, plus a light unsharp mask after upscaling."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.12, 0, 255)
    img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    img = cv2.convertScaleAbs(img, alpha=1.08, beta=-8)
    blur = cv2.GaussianBlur(img, (0, 0), 1.2)
    return cv2.addWeighted(img, 1.35, blur, -0.35, 0)


def _segment(src: str, start: float, dur: float, crop_x: int, crop_w: int, src_h: int, speed: float = 1.0):
    vf = f"crop={crop_w}:{src_h}:{crop_x}:0,"
    vf += f"setpts=PTS/{speed:.4f},minterpolate=fps={FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir" \
        if speed < 0.999 else f"fps={FPS}"
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{(dur + 0.1) * speed:.3f}", "-i", src,
           "-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = crop_w * src_h * 3
    return [np.frombuffer(raw[i:i + n], np.uint8).reshape(src_h, crop_w, 3) for i in range(0, len(raw) - n + 1, n)]


@dataclass
class HypeText:
    opener: str                    # viewer-voice line during the opener
    main: str                      # big line after the drop (countdown)
    final: str                     # last beats
    final_beats: int = 3
    watermark: str = ""


def render_hype(slots: list[Slot], text: HypeText, out: Path, *, src_size: tuple[int, int]) -> dict:
    sw, sh = src_size
    crop_w = int(round(sh * OUT_W / PIC_H / 2) * 2)          # 4:5 crop at full source height
    scale = PIC_H / sh
    pic_y = (OUT_H - PIC_H) // 2
    band_top_cy, band_bot_cy = pic_y // 2, pic_y + PIC_H + (OUT_H - pic_y - PIC_H) // 2
    l_open, l_main, l_final = text_layer(text.opener, 64), text_layer(text.main, 150), text_layer(text.final, 110)
    l_wm = text_layer(text.watermark, 34, (200, 200, 200)) if text.watermark else None
    total = slots[-1].t1
    final_from = slots[max(0, len(slots) - 1 - text.final_beats)].t0
    out.parent.mkdir(parents=True, exist_ok=True)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{OUT_W}x{OUT_H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "16",
                            "-pix_fmt", "yuv420p", "-profile:v", "high", "-movflags", "+faststart", str(out)],
                           stdin=subprocess.PIPE)
    n_frames = int(round(total * FPS))
    seg_cache: dict[int, list[np.ndarray]] = {}
    log = []
    for fi in range(n_frames):
        t = fi / FPS
        si = next(i for i, s in enumerate(slots) if s.t0 <= t < s.t1 or i == len(slots) - 1)
        sl = slots[si]
        frame = np.zeros((OUT_H, OUT_W, 3), np.uint8)
        if sl.kind != "black" and sl.shot is not None:
            if si not in seg_cache:
                seg_cache.clear()
                cx = int(np.clip(sl.shot.cx * sw - crop_w / 2, 0, sw - crop_w))
                seg_cache[si] = _segment(sl.shot.src, sl.src_start, sl.dur, cx, crop_w, sh, sl.speed)
                log.append({"t": round(sl.t0, 2), "dur": round(sl.dur, 2), "kind": sl.kind,
                            "src": Path(sl.shot.src).name, "src_t": round(sl.src_start, 2), "crop_x": cx,
                            "flash": sl.flash, "speed": round(sl.speed, 2)})
            frs = seg_cache[si]
            k = min(len(frs) - 1, int((t - sl.t0) * FPS))
            src = frs[k]
            # punch-in on every cut after the drop: 1.07 -> 1.0 over 6 frames
            z = 1.0 + 0.07 * max(0.0, 1 - (t - sl.t0) * FPS / 6) if sl.kind == "beat" else 1.0 + 0.04 * (t / sl.t1)
            pic = cv2.resize(src, (int(OUT_W * z), int(PIC_H * z)), interpolation=cv2.INTER_LANCZOS4)
            oy, ox = (pic.shape[0] - PIC_H) // 2, (pic.shape[1] - OUT_W) // 2
            frame[pic_y:pic_y + PIC_H] = _grade(pic[oy:oy + PIC_H, ox:ox + OUT_W])
            if sl.flash:
                a = max(0.0, 0.85 - (t - sl.t0) * FPS * 0.28)
                if a > 0:
                    frame[pic_y:pic_y + PIC_H] = (frame[pic_y:pic_y + PIC_H] * (1 - a) + 255 * a).astype(np.uint8)
        # text: bands only (never over the picture)
        if sl.kind == "opener":
            _blend(frame, l_open, band_top_cy, alpha=min(1.0, t / 0.25))
        elif t >= final_from and sl.kind != "black":
            _blend(frame, l_final, band_top_cy, scale=1.0 + 0.12 * max(0.0, 1 - (t - final_from) * FPS / 5))
        elif sl.kind != "black":
            drop = slots[1].t0
            _blend(frame, l_main, band_top_cy, scale=1.0 + 0.18 * max(0.0, 1 - (t - drop) * FPS / 5))
        if l_wm is not None and sl.kind != "black":
            _blend(frame, l_wm, band_bot_cy, alpha=0.8)
        enc.stdin.write(frame.tobytes())
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg encode failed")
    return {"file": str(out), "duration": round(n_frames / FPS, 2), "shots": log,
            "upscale": round(scale * 1.07, 2), "layout": "4:5 picture + black bands (text in bands)",
            "crop": f"{crop_w}x{sh} of {sw}x{sh}"}


# ------------------------------------------------------------------ public entry point
def days_until(release: str, today: date | None = None) -> int:
    return (date.fromisoformat(release) - (today or date.today())).days


def countdown_text(release: str, today: date | None = None, game: str = "GTA 6") -> HypeText:
    d = days_until(release, today)
    if d > 1:
        return HypeText(opener=f"{game} comes out in {d} days.", main=f"{d} DAYS", final="ARE YOU READY?")
    if d == 1:
        return HypeText(opener=f"{game} comes out TOMORROW.", main="1 DAY", final="ARE YOU READY?")
    if d == 0:
        return HypeText(opener=f"{game} is OUT.", main="IT'S HERE", final="SEE YOU IN LEONIDA")
    return HypeText(opener=f"{game} has been out for {-d} days.", main=f"DAY {-d}", final="STILL NOT OVER IT")


def music_instructions(tpl: BeatTemplate) -> dict:
    beat = 60 / tpl.bpm
    return {
        "sound": tpl.sound, "artist": tpl.sound_author, "reference_post": tpl.reference,
        "how": [f"On TikTok open the reference post and tap the sound '{tpl.sound}' -> Use this sound "
                f"(or pick it in the editor's sound search).",
                "Start the sound at 0:00 (do not trim the start): the edit was cut on this sound's beat grid.",
                "Set the original-video volume to 0 (the file is silent anyway), sound volume 100.",
                f"Check: the first hard cut + white flash at {tpl.drop:.2f}s must hit the drop."],
        "bpm": round(tpl.bpm, 1), "beat_s": round(beat, 3), "drop_at_s": round(tpl.drop, 2),
        "part_used": f"0:00-0:{int(math.ceil(tpl.duration)):02d} of the sound (build-up 0-{tpl.drop:.2f}s, drop at "
                     f"{tpl.drop:.2f}s, then one cut per beat)",
        "cut_times_s": [round(c, 2) for c in tpl.cuts],
        "other_sound_rule": f"Any other sound works if its drop is placed at {tpl.drop:.2f}s and it runs at "
                            f"~{tpl.bpm:.0f} BPM (or {tpl.bpm * 2:.0f} BPM counted in half-time).",
    }


def make_hype_edit(sources: list[str], tpl: BeatTemplate, text: HypeText, out: Path) -> dict:
    shots: list[Shot] = []
    for s in sources:
        shots += analyze_shots(s)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                       "stream=width,height", "-of", "json", sources[0]],
                                      capture_output=True, text=True, check=True).stdout)["streams"][0]
    for s in sources[1:]:
        p = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                       "stream=width,height", "-of", "json", s], capture_output=True, text=True,
                                      check=True).stdout)["streams"][0]
        if (p["width"], p["height"]) != (probe["width"], probe["height"]):
            raise ValueError("all sources must have the same resolution")
    slots = plan_slots(tpl, shots)
    res = render_hype(slots, text, out, src_size=(probe["width"], probe["height"]))
    res["source_height"] = probe["height"]
    res["shots_found"] = len(shots)
    res["shots_usable"] = sum(s.usable for s in shots)
    res["rejected"] = {r: sum(1 for s in shots if s.reason == r) for r in {s.reason for s in shots if s.reason}}
    res["template"] = tpl.id
    res["text"] = asdict(text)
    res["music"] = music_instructions(tpl)
    return res
