""""Ranking" format (learned 2026-11-23 from 5 owner-sent TikTok examples, 1.6M–18.6M views each).

What those videos do (our own clips follow the format, never their footage):
  * top third = a ranking board: title "Ranking {Streamer} Funny Moments" (name in colour) + an empty list 1.–5.
  * bottom = the moment, playing over a blurred copy of itself, streamer's own audio, no narrator, no cards
  * when a moment plays, its short funny label + emoji is written into a slot; slots are filled OUT of order
    (e.g. 4, 5, 3, 2 and #1 last) so people stay to see what lands at #1; the current slot is coloured
  * 10–20 s per moment, one optional teaser under the title ("(last one 💀)")
Spec: dict(id, src_dir, src, out_dir, title=[line1, line2], sub, moments=[dict(slot, label, emoji, parts)], fix)
"""
import importlib.util
import re
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("amp", ROOT / "scripts/manual_edits/2026-11-21_amp_clips.py")
amp = importlib.util.module_from_spec(_s)
_s.loader.exec_module(amp)
_s = importlib.util.spec_from_file_location("sfx", ROOT / "scripts/tools/sfx.py")
sfx = importlib.util.module_from_spec(_s)
_s.loader.exec_module(sfx)
_s = importlib.util.spec_from_file_location("ex", ROOT / "scripts/manual_edits/2026-11-22_amp_examples.py")
ex = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ex)

W, H, FPS, SR = 1080, 1920, 30, 48000
POP = str(ROOT / "assets/fonts/Poppins-ExtraBold.ttf")
EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
WHITE, YEL, ORANGE = (255, 255, 255), (255, 214, 0), (255, 140, 30)
_emo = {}


def emoji_img(ch, size):
    key = (ch, size)
    if key not in _emo:
        f = ImageFont.truetype(EMOJI, 109)
        im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((0, 0), ch, font=f, embedded_color=True)
        bb = im.getbbox() or (0, 0, 1, 1)
        _emo[key] = im.crop(bb).resize((size, size), Image.LANCZOS)
    return _emo[key]


def text_img(parts, size, stroke=6, max_w=1000):
    """parts: [(text, rgb) | ('EMOJI:x', None)] -> BGRA ndarray, shrinks to fit max_w."""
    while True:
        f = ImageFont.truetype(POP, size)
        widths = [(size * 1.05 if t.startswith("EMOJI:") else f.getlength(t)) for t, _ in parts]
        w = int(sum(widths)) + 2 * stroke + 10
        if w <= max_w or size <= 30:
            break
        size -= 3
    h = int(size * 1.45) + 2 * stroke
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = stroke + 4
    for (t, col), tw in zip(parts, widths):
        if t.startswith("EMOJI:"):
            e = emoji_img(t[6:], int(size * 0.95))
            im.alpha_composite(e, (int(x), int(stroke + size * 0.22)))
        else:
            d.text((x, stroke), t, font=f, fill=col + (255,), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        x += tw
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGBA2BGRA)


def rich(text, size, base=WHITE, hi=YEL, max_w=1000):
    out = []
    for p in re.split(r"(\{[^}]*\})", text):
        if p:
            out.append((p[1:-1], hi) if p.startswith("{") else (p, base))
    return text_img(out, size, max_w=max_w)


def paste_left(fr, im, x, cy):
    h = im.shape[0]
    amp.paste(fr, im, x + im.shape[1] / 2, cy)


def render(spec):
    src = Path(spec["src_dir"]) / f"{spec['src']}.mp4"
    w, h = ex.probe(src)
    ex.SRC = Path(spec["src_dir"])
    ws, rms = ex.words_flat(spec["src"], spec.get("fix", {}))
    out_dir = Path(spec["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    # timeline
    plan, caps, audio, t_out = [], [], [], 0.0
    for mi, m in enumerate(spec["moments"]):
        for a, b in m["parts"]:
            for x, y in ex.keep_intervals(ws, rms, a, b):
                plan.append((x, y, mi, t_out))
                caps += [(t_out + (tw - x), txt) for tw, txt in ws if x <= tw < y]
                audio.append(amp.audio(src, [(x, y)]))
                t_out += y - x
    total = t_out
    subs = amp.sub_chunks(caps)
    start_of = {}
    for x, y, mi, t0 in plan:
        start_of.setdefault(mi, t0)

    # static images
    title = [rich(spec["title"][0], 84), rich(spec["title"][1], 84, base=YEL, hi=ORANGE)]
    sub = text_img([(spec["sub"][0], WHITE), ("EMOJI:" + spec["sub"][1], None), (")", WHITE)], 40) if spec.get("sub") else None
    nums = {n: text_img([(f"{n}.", WHITE)], 66) for n in range(1, 6)}
    labels = {}
    for mi, m in enumerate(spec["moments"]):
        for state, col in (("cur", ORANGE), ("done", WHITE)):
            parts = [(m["label"] + " ", col)] + ([("EMOJI:" + m["emoji"], None)] if m.get("emoji") else [])
            labels[(mi, state)] = text_img(parts, 58, max_w=880)
    slot_of = {mi: m["slot"] for mi, m in enumerate(spec["moments"])}
    ROW0, STEP, X0 = 372, 76, 50
    clip_h = int(h * (1 - spec.get("crop_bottom", 0)))   # optional: cut burned-in captions at the bottom of the source
    cw = min(w, int(clip_h * 1.5))                      # 3:2 crop, <= 2x upscale on a 360p source
    cx0 = (w - cw) // 2
    PH = int(1080 * clip_h / cw)
    PY = 760
    cache = {}

    tmp = out_dir / f"_{spec['id']}.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                            "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    for x, y, mi, t0 in plan:
        frames = ex.grab(src, x, y, w, h)
        n = int(round((y - x) * FPS))
        frames = (frames + [frames[-1]] * n)[:n] if frames else []
        for j, f in enumerate(frames):
            to = t0 + j / FPS
            bg = cv2.GaussianBlur(cv2.resize(f, (192, 108)), (0, 0), 5)
            bg = cv2.resize(bg, (int(H * 192 / 108), H))
            xo = (bg.shape[1] - W) // 2
            fr = (bg[:, xo:xo + W].astype(np.float32) * 0.42).astype(np.uint8)
            fr[:720] = (fr[:720].astype(np.float32) * 0.55).astype(np.uint8)       # darker board area
            fr[PY:PY + PH] = cv2.resize(f[:clip_h, cx0:cx0 + cw], (1080, PH), interpolation=cv2.INTER_LANCZOS4)
            y0 = 70
            for im in title:
                amp.paste(fr, im, W / 2, y0 + im.shape[0] / 2)
                y0 += im.shape[0] - 18
            if sub is not None:
                amp.paste(fr, sub, W / 2, y0 + 22)
            for s in range(1, 6):
                cy = ROW0 + (s - 1) * STEP + 40
                paste_left(fr, nums[s], X0, cy)
                for mj in range(mi + 1):
                    if slot_of[mj] == s:
                        im = labels[(mj, "cur" if mj == mi else "done")]
                        if mj == mi and to - start_of[mi] < 0.25:                  # pop-in
                            k = 1.25 - (to - start_of[mi]) / 0.25 * 0.25
                            im = cv2.resize(im, None, fx=k, fy=k)
                        paste_left(fr, im, X0 + nums[s].shape[1] + 6, cy)
            for s0, s1, ch in subs:
                if s0 <= to < s1:
                    key = (tuple(w_ for _, w_ in ch), max([i for i, (tw, _) in enumerate(ch) if tw <= to + .02] or [0]))
                    if key not in cache:
                        cache[key] = text_img([(w_ + " ", YEL if i == key[1] else WHITE)
                                               for i, (_, w_) in enumerate(ch)], 70)
                    amp.paste(fr, cache[key], W / 2, PY + PH + 140)
                    break
            enc.stdin.write(fr.tobytes())
    enc.stdin.close()
    enc.wait()
    au = np.concatenate([a_[:int(round(len(a_) / SR * FPS)) * SR // FPS] for a_ in audio])
    # ---------------- sound effects (ours, synthesized): automatic + per-moment events at source times
    def src_to_out(ts):
        for x, y, mi, t0 in plan:
            if ts < y:
                return t0 + max(0.0, ts - x)
        return total

    events = []
    for mi, m in enumerate(spec["moments"]):
        st = start_of[mi]
        events.append((st, "pop", 0.45))
        if mi > 0:
            events.append((max(0, st - 0.2), "whoosh", 0.35))
        if m["slot"] == 1:
            events.append((max(0, st - 1.6), "riser", 0.4))
            events.append((st, "boom", 0.75))
        for ts, name, g in m.get("sfx", []):
            events.append((src_to_out(ts), name, g))
    if spec.get("sfx_on", False):          # owner 2026-11-23: no SFX
        au = au * 0.9
        for t_ev, name, g in events:
            e = sfx.get(name) * g
            i0 = int(t_ev * SR)
            i1 = min(len(au), i0 + len(e))
            if i1 > i0:
                au[i0:i1] += e[:i1 - i0]
        au = au / max(1.0, float(np.max(np.abs(au))))
    wav = out_dir / f"_{spec['id']}.wav"
    wf = wave.open(str(wav), "wb")
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(SR)
    wf.writeframes((np.clip(au, -1, 1) * 32767).astype("<i2").tobytes())
    wf.close()
    out = out_dir / f"PRIVATE-TEST_{spec['id']}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5,aresample=48000,alimiter=limit=0.85:level=false", "-shortest",
                    str(out)], check=True)
    tmp.unlink()
    wav.unlink()
    return out, round(total, 1)
