"""Meme maker: one relatable line + one well-known reaction clip (the formula of the release-week memes in
docs/GTA6_PLAYBOOK.md).

1. `extract_clip`: from a reference meme, keep only the reaction footage. Captions and black bars are static,
   the footage moves, so the moving band (rows/columns with temporal variance) is the clip. Audio is kept.
2. Library: `config/meme_clips/<profile>.json` describes every clip (what happens, emotion, length) so the
   operator / AI can pair it with a new joke. Files live in `assets/meme_clips/` (gitignored).
3. `render_meme`: 1080x1920, black background, the caption in the top bar (white, bold, centred, never on the
   picture), the clip below it, the clip's own audio. Same file for TikTok and YouTube Shorts.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

W, H = 1080, 1920
MAX_UPSCALE = 2.0


def _probe(path: str) -> dict:
    d = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                                   "-of", "json", path], capture_output=True, text=True, check=True).stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    return {"w": v["width"], "h": v["height"], "duration": float(d["format"]["duration"]),
            "audio": any(s["codec_type"] == "audio" for s in d["streams"])}


def moving_box(path: str, thr: float = 12.0) -> tuple[int, int, int, int]:
    """(x, y, w, h) in source pixels of the region that moves (the reaction footage)."""
    info = _probe(path)
    aw, ah = 144, max(2, int(round(144 * info["h"] / info["w"] / 2)) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps=5,scale={aw}:{ah}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, ah, aw).astype(np.float32)
    std = fr.std(0)
    rows = np.where(std.mean(1) > thr)[0]
    cols = np.where(std.mean(0) > thr * 0.6)[0]
    if not len(rows):
        return 0, 0, info["w"], info["h"]
    y0, y1 = rows.min(), rows.max() + 1
    rstd = std.mean(1)
    while y0 > 0 and rstd[y0 - 1] > 1.0:                 # static parts of the footage still show compression noise;
        y0 -= 1                                          # captions on black / solid bars are perfectly still
    while y1 < ah and rstd[y1] > 1.0:
        y1 += 1
    x0, x1 = (cols.min(), cols.max() + 1) if len(cols) else (0, aw)
    sx, sy = info["w"] / aw, info["h"] / ah
    x, y = int(x0 * sx) // 2 * 2, int(y0 * sy) // 2 * 2
    w, h = int((x1 - x0) * sx) // 2 * 2, int((y1 - y0) * sy) // 2 * 2
    return x, y, max(2, w), max(2, h)


def extract_clip(src: str, out: Path, *, start: float = 0.0, end: float | None = None,
                 box: tuple[int, int, int, int] | None = None) -> dict:
    """Clean reaction clip (no caption, no bars) with its audio."""
    x, y, w, h = box or moving_box(src)
    info = _probe(src)
    end = min(end or info["duration"], info["duration"])
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-to", f"{end:.2f}", "-i", src,
           "-vf", f"crop={w}:{h}:{x}:{y}", "-c:v", "libx264", "-crf", "14", "-preset", "slow"]
    cmd += (["-c:a", "aac", "-b:a", "192k"] if info["audio"] else ["-an"]) + [str(out)]
    subprocess.run(cmd, check=True)
    return {"file": str(out), "box": [x, y, w, h], "duration": round(end - start, 2), "w": w, "h": h,
            "upscale": round(W / w, 2)}


def _caption(text: str, max_w: int, size: int = 62) -> np.ndarray:
    """RGBA caption: white bold text, wrapped and centred (TikTok meme style)."""
    from PIL import Image, ImageDraw
    from .hype_editor import _font
    while True:
        f = _font(size)
        d = ImageDraw.Draw(Image.new("L", (1, 1)))
        def wrap(width: float) -> list[str]:
            out, cur = [], ""
            for wd in text.split():
                t = (cur + " " + wd).strip()
                if d.textlength(t, font=f) <= width or not cur:
                    cur = t
                else:
                    out.append(cur)
                    cur = wd
            return out + [cur]
        lines = wrap(max_w)
        width = max_w
        while width > max_w * 0.5 and len(wrap(width - 20)) == len(lines):    # balance: no orphan last word
            width -= 20
        lines = wrap(width)
        if len(lines) <= 4 or size <= 40:
            break
        size -= 4
    lh = int(size * 1.18)
    img = Image.new("RGBA", (max_w + 40, lh * len(lines) + 30), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        dr.text(((img.width - dr.textlength(l, font=f)) / 2, 10 + i * lh), l, font=f, fill=(255, 255, 255, 255))
    return np.array(img)


def render_meme(clip: str, caption: str, out: Path, *, max_seconds: float = 30.0) -> dict:
    """Caption in the top bar + clip below it, clip audio; 1080x1920."""
    import cv2
    info = _probe(clip)
    scale = min(W / info["w"], 1150 / info["h"], MAX_UPSCALE)      # never enlarge more than 2x (no blurry memes)
    cw, ch = int(info["w"] * scale) // 2 * 2, int(info["h"] * scale) // 2 * 2
    cap = _caption(caption, int(W * 0.88))
    gap = 36
    block = cap.shape[0] + gap + ch
    top = max(140, (H - block) // 2 - 60)                 # slightly above centre, like the references
    cy, py = top, top + cap.shape[0] + gap
    canvas = np.zeros((H, W, 4), np.uint8)
    canvas[..., 3] = 255
    x0 = (W - cap.shape[1]) // 2
    a = cap[..., 3:4].astype(np.float32) / 255
    region = canvas[cy:cy + cap.shape[0], x0:x0 + cap.shape[1], :3].astype(np.float32)
    canvas[cy:cy + cap.shape[0], x0:x0 + cap.shape[1], :3] = (region * (1 - a) + cap[..., :3] * a).astype(np.uint8)
    out.parent.mkdir(parents=True, exist_ok=True)
    overlay = out.with_suffix(".bg.png")
    cv2.imwrite(str(overlay), cv2.cvtColor(canvas, cv2.COLOR_RGBA2BGRA))
    dur = min(info["duration"], max_seconds)
    fc = (f"[1:v]scale={cw}:{ch}:flags=lanczos,unsharp=5:5:0.6[c];[0:v][c]overlay={(W - cw) // 2}:{py},"
          f"format=yuv420p[v]")
    cmd = ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "30", "-i", str(overlay), "-i", clip,
           "-filter_complex", fc, "-map", "[v]"]
    cmd += (["-map", "1:a", "-c:a", "aac", "-b:a", "192k"] if info["audio"] else [])
    cmd += ["-t", f"{dur:.2f}", "-r", "30", "-c:v", "libx264", "-crf", "17", "-preset", "slow", "-movflags", "+faststart",
            str(out)]
    subprocess.run(cmd, check=True)
    overlay.unlink(missing_ok=True)
    return {"file": str(out), "duration": round(dur, 2), "upscale": round(scale, 2), "caption": caption,
            "layout": "caption top bar + clip"}


def load_library(root: Path, profile: str) -> list[dict]:
    p = root / "config" / "meme_clips" / f"{profile}.json"
    return json.loads(p.read_text()) if p.exists() else []


def save_library(root: Path, profile: str, clips: list[dict]) -> Path:
    p = root / "config" / "meme_clips" / f"{profile}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(clips, indent=1, ensure_ascii=False))
    return p


CAPTION_SCHEMA = {"type": "object", "properties": {"captions": {"type": "array", "items": {"type": "object", "properties": {
    "clip": {"type": "string"}, "caption": {"type": "string"}}, "required": ["clip", "caption"]}}}, "required": ["captions"]}

CAPTION_PROMPT = """You write captions for GTA 6 reaction memes (TikTok / YouTube Shorts). Format: one relatable line on
top + a well-known reaction clip below. Today: {today}; GTA 6 comes out on November 19, 2026 ({days_text}).
Trending GTA 6 topics today: {topics}.
Style of captions that went viral this week (do NOT copy them, write new jokes in the same voice):
{examples}
Rules: max 90 characters; first person ("Me when…", "POV:", "When…", "How I'll be…"); the clip must be the punchline
(caption = setup); about GTA 6 / Leonida / Vice City / Lucia & Jason / release night / preload / NPCs / police /
radio stations; no hashtags; no claims about game features that are not confirmed; nothing sexual or hateful;
every caption different from these already used: {used}.
Write ONE caption for each clip:
{clips}"""


def write_captions(clips: list[dict], gemini, *, days: int, topics: list[str], examples: list[str], today: str) -> dict:
    """One new caption per clip id (one free Gemini call for the whole batch)."""
    listing = "\n".join(f"- {c['id']}: {c['what']} (emotion: {', '.join(c.get('emotion', []))})" for c in clips)
    used = [u for c in clips for u in c.get("used_captions", [])]
    days_text = f"{days} days left" if days > 0 else ("out today" if days == 0 else f"out for {-days} days")
    res = gemini.generate_json(CAPTION_PROMPT.format(today=today, days_text=days_text, topics=", ".join(topics[:12]),
                                                     examples="\n".join(f"- {e}" for e in examples[:12]),
                                                     used="; ".join(used[-40:]), clips=listing),
                               CAPTION_SCHEMA, temperature=0.9)
    out = {}
    for r in (res or {}).get("captions", []):
        cap = (r.get("caption") or "").strip().strip('"')
        if r.get("clip") and cap and len(cap) <= 110 and cap not in used:
            out[r["clip"]] = cap
    return out
