"""Style library: learn editing formats from example clips and pick one per new clip.

`examples add` analyses an example short (local signal analysis + optional Gemini vision on a few
frames) and stores a *style preset*: layout, split ratio / facecam position, caption look, title
banner, length and pacing. When a profile's ``editing.layout_policy`` is ``style_examples``, the
adaptive editor asks this library for the preset that matches the candidate's category.
"""
from __future__ import annotations

import io
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ..config import Settings
from ..core.database import Database, dumps, loads, new_id, now_iso
from ..core.logger import get_logger
from ..core.media import extract_audio_wav, media_info, read_frames
from ..detection.audio_analyzer import analyze_wav
from ..detection.visual_analyzer import analyze_video, detect_faces

log = get_logger("styles")

SCHEMA = """
CREATE TABLE IF NOT EXISTS style_examples (
    id TEXT PRIMARY KEY, profile TEXT NOT NULL, label TEXT, category TEXT, source TEXT,
    metrics TEXT, vision TEXT, preset TEXT, notes TEXT, created_at TEXT
);
"""

LAYOUTS = ("focus", "fit_blur", "letterbox", "split_cam", "full_gameplay")


# ----------------------------------------------------------------------------- local analysis
def _frames(path: Path, n: int = 12, width: int = 360) -> list[np.ndarray]:
    dur = media_info(path)["duration"]
    out = []
    for i in range(n):
        t = dur * (0.05 + 0.9 * i / max(1, n - 1))
        fr = next(iter(read_frames(path, t, 0.05, 25, width)), None)
        if fr is not None:
            out.append(fr)
    return out


def detect_seam(frames: list[np.ndarray]) -> tuple[float | None, float]:
    """Find a horizontal split line present at the same height in most frames.
    Returns (y_fraction or None, strength)."""
    if not frames:
        return None, 0.0
    profiles = []
    for fr in frames:
        g = cv2.cvtColor(fr, cv2.COLOR_RGB2GRAY).astype(np.float32)
        rows = g.mean(axis=1)
        grad = np.abs(np.diff(rows))                       # brightness jump between consecutive rows
        edge = np.abs(np.diff(g, axis=0)).mean(axis=1)     # per-row mean vertical edge strength
        p = grad * 0.5 + edge
        profiles.append(p / (np.median(p) + 1e-6))
    h = min(len(p) for p in profiles)
    stack = np.stack([p[:h] for p in profiles])
    score = np.median(stack, axis=0)                       # consistent across frames
    # a real split separates two different pictures: weight rows by how different the bands
    # just above and below them are (colour statistics, averaged over frames)
    band = max(4, h // 20)
    diff = np.zeros(h)
    for fr in frames:
        f = fr.astype(np.float32)
        for y in range(band, h - band, 2):
            a = f[y - band:y].reshape(-1, 3); b = f[y + 1:y + 1 + band].reshape(-1, 3)
            d = np.abs(a.mean(0) - b.mean(0)).sum() + np.abs(a.std(0) - b.std(0)).sum()
            diff[y] += d; diff[min(h - 1, y + 1)] += d
    diff /= max(1, len(frames))
    score = score * (0.3 + diff / (np.median(diff[band:h - band]) + 1e-6))
    lo, hi = int(h * 0.2), int(h * 0.8)
    y = lo + int(np.argmax(score[lo:hi]))
    strength = float(score[y])
    return (round((y + 1) / (h + 1), 3), strength) if strength >= 12.0 else (None, strength)


def blur_bands(frames: list[np.ndarray]) -> float:
    """Ratio of edge detail in top/bottom quarters vs the middle half (low = blurred fill)."""
    rs = []
    for fr in frames:
        g = cv2.cvtColor(fr, cv2.COLOR_RGB2GRAY)
        h = g.shape[0]
        lap = lambda a: float(cv2.Laplacian(a, cv2.CV_64F).var())
        mid = lap(g[h // 4: 3 * h // 4]) + 1e-6
        rs.append((lap(g[: h // 4]) + lap(g[3 * h // 4:])) / 2 / mid)
    return float(np.median(rs)) if rs else 1.0


def face_positions(frames: list[np.ndarray]) -> list[tuple[float, float, float]]:
    out = []
    for fr in frames:
        H, W = fr.shape[:2]
        for x, y, w, h in detect_faces(fr, 0.04):
            out.append(((x + w / 2) / W, (y + h / 2) / H, h / H))
    return out


def analyze_local(path: Path, work: Path) -> dict[str, Any]:
    info = media_info(path)
    frames = _frames(path)
    seam, seam_strength = detect_seam(frames)
    blur = blur_bands(frames)
    faces = face_positions(frames)
    vis = analyze_video(path, info["duration"], fps=2.0, width=240)
    cuts = int((vis.scene > 0.45).sum()) if vis.scene.size else 0
    loud = None
    if info.get("has_audio"):
        wav = extract_audio_wav(path, work / "example.wav")
        a = analyze_wav(wav)
        loud = round(float(np.percentile(a.db, 90)), 1)
        wav.unlink(missing_ok=True)
    vertical = info.get("height", 0) > info.get("width", 0)
    face_y = float(np.median([f[1] for f in faces])) if faces else None
    if not vertical:
        layout = "fit_blur"
    elif blur < 0.25:
        layout = "fit_blur"          # 16:9 picture on a blurred fill (its edges look like seams)
    elif seam is not None:
        layout = "split_cam"
    elif faces and len(faces) >= len(frames) * 0.6:
        layout = "focus"
    else:
        layout = "full_gameplay"
    cam = None
    if layout == "split_cam":
        cam = "top" if (face_y is None or face_y < seam) else "bottom"
    return {
        "duration": round(info["duration"], 1), "width": info.get("width"), "height": info.get("height"),
        "vertical": vertical, "seam_y": seam, "seam_strength": round(seam_strength, 2),
        "blur_band_ratio": round(blur, 3), "faces_per_frame": round(len(faces) / max(1, len(frames)), 2),
        "face_y": round(face_y, 3) if face_y is not None else None, "cuts_per_min": round(cuts * 60 / max(1, info["duration"]), 1),
        "loudness_p90_db": loud, "layout_guess": layout, "cam_position": cam,
    }


# ----------------------------------------------------------------------------- Gemini vision
VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "layout": {"type": "string", "enum": ["full_frame", "split_top_bottom", "blurred_bands", "black_bars", "picture_in_picture", "other"]},
        "facecam_position": {"type": "string", "enum": ["top", "bottom", "overlay", "none"]},
        "split_ratio": {"type": "number"},
        "captions_present": {"type": "boolean"},
        "caption_position": {"type": "number"},
        "caption_uppercase": {"type": "boolean"},
        "caption_words_per_line": {"type": "integer"},
        "caption_primary_color": {"type": "string"},
        "caption_highlight_color": {"type": "string"},
        "title_banner_present": {"type": "boolean"},
        "title_position": {"type": "number"},
        "title_box_color": {"type": "string"},
        "title_text_color": {"type": "string"},
        "title_text": {"type": "string"},
        "effects": {"type": "array", "items": {"type": "string"}},
        "category": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["layout", "captions_present", "title_banner_present"],
}


def analyze_vision(path: Path, gemini, categories: list[str]) -> dict[str, Any] | None:
    if gemini is None or not gemini.available():
        return None
    from google.genai import types
    from PIL import Image
    parts = []
    for fr in _frames(path, n=4, width=540):
        buf = io.BytesIO()
        Image.fromarray(fr).save(buf, "JPEG", quality=85)
        parts.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"))
    prompt = (
        "These are 4 frames (in order) from ONE vertical short-form clip that the user likes. Describe its "
        "EDITING FORMAT precisely so it can be reproduced: layout (full_frame, split_top_bottom with a streamer "
        "camera and gameplay, blurred_bands = original 16:9 on a blurred background, black_bars = original 16:9 on solid black bars, picture_in_picture), where "
        "the streamer camera is, split_ratio (fraction of height of the TOP panel), captions (vertical position as "
        "fraction of height of their centre, uppercase or not, words per line, colours as #RRGGBB incl. highlight "
        "colour of emphasised words), an on-screen title banner (present, vertical position fraction of its top, "
        "box and text colours as #RRGGBB, its text), visible effects (zoom, emojis, progress bar, etc.) and the "
        f"content category, one of: {', '.join(categories)}. Only describe what is visible.")
    try:
        return gemini.generate_json([*parts, prompt], VISION_SCHEMA, temperature=0.1)
    except Exception as e:
        log.warning("vision analysis failed: %s", e)
        return {"error": str(e)[:300]}


# ----------------------------------------------------------------------------- presets
def _hex(v: Any, default: str) -> str:
    s = str(v or "").strip()
    return s.upper() if len(s) == 7 and s.startswith("#") else default


def _frac(v: Any, default: float, lo: float = 0.05, hi: float = 0.95) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f > 1.0:            # model answered in percent
        f /= 100.0
    return round(min(hi, max(lo, f)), 3)


def derive_preset(metrics: dict, vision: dict | None) -> dict[str, Any]:
    v = vision if isinstance(vision, dict) and "error" not in vision else {}
    layout = metrics.get("layout_guess", "focus")
    vl = v.get("layout")
    if vl == "split_top_bottom":
        layout = "split_cam"
    elif vl == "blurred_bands":
        layout = "fit_blur"
    elif vl == "black_bars":
        layout = "letterbox"
    elif vl == "full_frame" and layout in ("split_cam", "fit_blur"):
        layout = "focus" if metrics.get("faces_per_frame", 0) >= 0.6 else "full_gameplay"
    split = _frac(v.get("split_ratio"), metrics.get("seam_y") or 0.5, 0.25, 0.75)
    cam = v.get("facecam_position") if v.get("facecam_position") in ("top", "bottom") else (metrics.get("cam_position") or "top")
    preset: dict[str, Any] = {"layout": layout, "split_ratio": split, "cam_position": cam,
                              "target_duration": metrics.get("duration"), "cuts_per_min": metrics.get("cuts_per_min")}
    if v.get("captions_present", True):
        preset["caption"] = {
            "position": _frac(v.get("caption_position"), split if layout == "split_cam" else 0.62, 0.3, 0.8),
            "uppercase": bool(v.get("caption_uppercase", True)),
            "max_words": int(min(5, max(1, v.get("caption_words_per_line") or 3))),
            "primary_color": _hex(v.get("caption_primary_color"), "#FFFFFF"),
            "highlight_color": _hex(v.get("caption_highlight_color"), "#FFD400"),
        }
    else:
        preset["caption"] = {"enabled": False}
    if v:
        preset["title_overlay"] = {
            "enabled": bool(v.get("title_banner_present")),
            "position": _frac(v.get("title_position"), 0.10, 0.06, 0.4),
            "box_color": _hex(v.get("title_box_color"), "#FFFFFF"),
            "text_color": _hex(v.get("title_text_color"), "#000000"),
        }
    preset["effects"] = list(v.get("effects") or [])[:8]
    return preset


@dataclass
class StyleChoice:
    preset: dict[str, Any]
    example_ids: list[str]
    reason: str


class StyleLibrary:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings
        self.db.conn.executescript(SCHEMA)

    def add(self, path: str | Path, profile: str, *, label: str | None = None, category: str | None = None,
            source: str | None = None, gemini=None, notes: str | None = None) -> dict[str, Any]:
        prof = self.settings.profile(profile)
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(p)
        work = self.settings.work_dir / "examples"
        work.mkdir(parents=True, exist_ok=True)
        metrics = analyze_local(p, work)
        vision = analyze_vision(p, gemini, prof.content_categories)
        cat = category or ((vision or {}).get("category") if (vision or {}).get("category") in prof.content_categories else None)
        preset = derive_preset(metrics, vision)
        eid = new_id("ex")
        self.db.insert("style_examples", {"id": eid, "profile": profile, "label": label or p.stem, "category": cat,
                                          "source": source or str(p.resolve()), "metrics": dumps(metrics),
                                          "vision": dumps(vision), "preset": dumps(preset), "notes": notes,
                                          "created_at": now_iso()})
        return {"id": eid, "category": cat, "metrics": metrics, "vision": vision, "preset": preset}

    def add_from_description(self, description: str, profile: str, *, source: str, gemini,
                             label: str | None = None, category: str | None = None) -> dict[str, Any]:
        """Save an example from a written scene-by-scene analysis (e.g. when only a link is available).
        Gemini turns the text into the same structured description the frame analysis produces."""
        prof = self.settings.profile(profile)
        schema = {**VISION_SCHEMA, "properties": {**VISION_SCHEMA["properties"],
                                                  "duration_seconds": {"type": "number"},
                                                  "cuts_per_minute": {"type": "number"},
                                                  "content_summary": {"type": "string"}}}
        prompt = ("Convert this analysis of a vertical short-form video into the structured editing format. "
                  "A 16:9 picture centred on solid black bars is layout black_bars (NOT split_top_bottom, which "
                  "means two different pictures stacked). "
                  "Use only what the analysis states; leave unknown fields out. Colours as #RRGGBB, positions as "
                  f"fractions of the frame height. category must be one of: {', '.join(prof.content_categories)}.\n\n"
                  + description[:12000])
        vision = gemini.generate_json(prompt, schema, temperature=0.1)
        metrics = {"duration": vision.get("duration_seconds"), "cuts_per_min": vision.get("cuts_per_minute"),
                   "layout_guess": {"split_top_bottom": "split_cam", "blurred_bands": "fit_blur", "black_bars": "letterbox"}.get(
                       vision.get("layout"), "focus"), "faces_per_frame": 0, "seam_y": None,
                   "from": "written analysis"}
        cat = category or (vision.get("category") if vision.get("category") in prof.content_categories else None)
        preset = derive_preset(metrics, vision)
        eid = new_id("ex")
        self.db.insert("style_examples", {"id": eid, "profile": profile, "label": label or source, "category": cat,
                                          "source": source, "metrics": dumps(metrics), "vision": dumps(vision),
                                          "preset": dumps(preset), "notes": description[:20000],
                                          "created_at": now_iso()})
        return {"id": eid, "category": cat, "metrics": metrics, "vision": vision, "preset": preset}

    def list(self, profile: str | None = None) -> list[dict]:
        sql = "SELECT * FROM style_examples" + (" WHERE profile=?" if profile else "") + " ORDER BY created_at"
        rows = self.db.query(sql, (profile,) if profile else ())
        for r in rows:
            for k in ("metrics", "vision", "preset"):
                r[k] = loads(r[k])
        return rows

    def remove(self, eid: str) -> None:
        self.db.execute("DELETE FROM style_examples WHERE id=?", (eid,))

    def set_category(self, eid: str, category: str) -> None:
        self.db.update("style_examples", "id", eid, {"category": category})

    def choose(self, profile: str, category: str | None) -> StyleChoice | None:
        rows = self.list(profile)
        if not rows:
            return None
        pool = [r for r in rows if category and r["category"] == category]
        why = f"examples for category '{category}'"
        if not pool:
            pool, why = rows, "all examples (no example for this category yet)"
        # majority layout among the pool, then the most recent example with that layout
        layout = Counter(r["preset"]["layout"] for r in pool).most_common(1)[0][0]
        pick = [r for r in pool if r["preset"]["layout"] == layout][-1]
        return StyleChoice(pick["preset"], [r["id"] for r in pool], f"{why}: layout '{layout}' from example {pick['id']}")

    def summary(self, profile: str) -> dict[str, Any]:
        rows = self.list(profile)
        by_cat: dict[str, Counter] = {}
        for r in rows:
            by_cat.setdefault(r["category"] or "(none)", Counter())[r["preset"]["layout"]] += 1
        return {"examples": len(rows), "by_category": {k: dict(v) for k, v in by_cat.items()}}


def json_dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
