"""Top-N ranked clip (owner's rule 2026-11-22: transformed clips with our scripted AI narrator, cut from the VOD).

Structure (vertical 1080x1920, < 60 s for Shorts):
  HOOK      1.5–2 s of the #1 moment (stream audio) + "WAIT FOR #1" -> the payoff is promised in second 0
  for #N..#1:
    CARD    narrator line (our own context / verdict, Kokoro am_fenrir) over the moment's first frame, darkened,
            slow zoom, huge rank number
    MOMENT  the moment from the VOD with the streamer's own audio, jump cuts (no dead air), word captions
  OUTRO     narrator question over the last frame (drives comments)
Headline on top the whole time, rank badge on the picture, progress bar at the bottom. No music baked in.

Spec: a python dict (see make_* scripts), e.g.
  dict(id="kai_banks_top3", src_dir=".../2026-11-23", src="kai_banks", out_dir="...",
       headline=["{KAI CENAT} ROBBED EVERY BANK", "IN GTA 6 — RANKED"], hook=(t, dur),
       items=[dict(rank=3, parts=[(a, b), ...], vo="Number three. ..."), ...],
       outro="Which one was the worst? Tell me below.", crop=None or 0.5, fix={})
"""
import importlib.util
import json
import re
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_s = importlib.util.spec_from_file_location("amp", ROOT / "scripts/manual_edits/2026-11-21_amp_clips.py")
amp = importlib.util.module_from_spec(_s)
_s.loader.exec_module(amp)
_s = importlib.util.spec_from_file_location("ex", ROOT / "scripts/manual_edits/2026-11-22_amp_examples.py")
ex = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ex)

W, H, FPS, SR = 1080, 1920, 30, 48000
YEL = (0, 214, 255)
KOKORO = ("/root/.cache/kokoro/kokoro.onnx", "/root/.cache/kokoro/voices.bin")
_tts = None


def tts(text, speed=1.1, voice="am_fenrir"):
    """-> stereo float32 at 48 kHz."""
    global _tts
    if _tts is None:
        from kokoro_onnx import Kokoro
        _tts = Kokoro(*KOKORO)
    a, sr = _tts.create(text, voice=voice, speed=speed, lang="en-us")
    n = int(len(a) * SR / sr)
    a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
    a = a / (np.max(np.abs(a)) + 1e-6) * 0.9
    pad = np.zeros(int(0.12 * SR), np.float32)
    a = np.concatenate([pad, a, pad])
    return np.stack([a, a], 1)


def vo_words(text, dur, lead=0.12):
    """approximate word timings for narrator captions (proportional to word length)."""
    ws = text.split()
    wts = np.array([len(re.sub(r"\W", "", w)) + 2 for w in ws], float)
    span = dur - 2 * lead
    t = lead + np.concatenate([[0], np.cumsum(wts)[:-1]]) / wts.sum() * span
    return [(float(ti), re.sub(r"[^\w'?!*.,#-]", "", w).upper()) for ti, w in zip(t, ws)]


def badge(text, size=150):
    return amp.fit("{" + text + "}", 600, size)


def render(spec):
    src = Path(spec["src_dir"]) / f"{spec['src']}.mp4"
    w, h = ex.probe(src)
    ex.SRC = Path(spec["src_dir"])
    ws, rms = ex.words_flat(spec["src"], spec.get("fix", {}))
    out_dir = Path(spec["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    head = [amp.fit(line, 1010, 84) for line in spec["headline"]]
    crop = spec.get("crop")
    if crop is not None:
        cw = int(h * 4 / 5)
        x0 = int(np.clip(crop * w - cw / 2, 0, w - cw))
        PW, PH = 1080, 1350
    else:
        cw, x0 = w, 0
        PW, PH = 1080, int(1080 * h / w)
    PY = 330 + (1350 - PH) // 2 if PH < 1350 else 330

    # ---------------- timeline: (kind, payload) ; kinds: clip (a, b, rank), card (frame_t, audio, text, rank)
    segs = []
    t, d = spec["hook"]
    segs.append(("hook", (t, t + d, 1)))
    for it in spec["items"]:
        a0 = it["parts"][0][0]
        segs.append(("card", (a0 + 0.2, tts(it["vo"]), it["vo"], it["rank"])))
        for a, b in it["parts"]:
            for x, y in ex.keep_intervals(ws, rms, a, b):
                segs.append(("clip", (x, y, it["rank"])))
    last = spec["items"][-1]["parts"][-1][1]
    segs.append(("card", (last - 0.3, tts(spec["outro"]), spec["outro"], None)))

    # durations + captions on the output timeline
    caps, audio, t_out, plan = [], [], 0.0, []
    for kind, p in segs:
        if kind in ("hook", "clip"):
            a, b, rank = p
            dur = b - a
            if kind == "clip":
                caps += [(t_out + (tw - a), txt) for tw, txt in ws if a <= tw < b]
            audio.append(amp.audio(src, [(a, b)]))
        else:
            ft, au, text, rank = p
            dur = len(au) / SR
            caps += [(t_out + tw, txt) for tw, txt in vo_words(text, dur)]
            audio.append(au)
        plan.append((kind, p, t_out, dur))
        t_out += dur
    total = t_out
    subs = amp.sub_chunks(caps)
    cache, bcache = {}, {}

    def base(f):
        main = cv2.resize(f[:, x0:x0 + cw], (PW, PH), interpolation=cv2.INTER_LANCZOS4)
        bg = cv2.GaussianBlur(cv2.resize(f, (192, 108)), (0, 0), 6)
        bg = cv2.resize(bg, (int(H * 192 / 108), H))
        xo = (bg.shape[1] - W) // 2
        fr = (bg[:, xo:xo + W].astype(np.float32) * 0.35).astype(np.uint8)
        return fr, main

    def overlay(fr, to, rank, card=False):
        y = 70 if PH >= 1200 else 150
        for im in head:
            amp.paste(fr, im, W / 2, y + im.shape[0] / 2)
            y += im.shape[0] - 10
        if rank is not None and not card:
            key = f"#{rank}"
            bcache.setdefault(key, badge(key, 110))
            amp.paste(fr, bcache[key], 110, PY + 90)
        for s0, s1, ch in subs:
            if s0 <= to < s1:
                cy = PY + PH - 170 if PH >= 1200 else PY + PH + 150
                amp.paste(fr, amp.sub_image(ch, to, cache), W / 2, cy)
                break
        cv2.rectangle(fr, (0, H - 14), (int(W * min(1, to / total)), H), YEL, -1)
        return fr

    tmp = out_dir / f"_{spec['id']}.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                            "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    for kind, p, t0, dur in plan:
        n = int(round(dur * FPS))
        if kind in ("hook", "clip"):
            a, b, rank = p
            frames = ex.grab(src, a, b, w, h)[:n] or [np.zeros((h, w, 3), np.uint8)]
            while len(frames) < n:
                frames.append(frames[-1])
            for j, f in enumerate(frames):
                fr, main = base(f)
                fr[PY:PY + PH] = main
                to = t0 + j / FPS
                fr = overlay(fr, to, None if kind == "hook" else rank)
                if kind == "hook":
                    key = "hook"
                    bcache.setdefault(key, amp.fit("WAIT FOR {#1}...", 900, 110))
                    amp.paste(fr, bcache[key], W / 2, PY + PH / 2)
                enc.stdin.write(fr.tobytes())
        else:
            ft, au, text, rank = p
            f = ex.grab(src, ft, ft + 0.1, w, h)[0]
            for j in range(n):
                z = 1.0 + 0.06 * j / max(1, n)
                g = cv2.resize(f, None, fx=z, fy=z)
                oy, ox = (g.shape[0] - h) // 2, (g.shape[1] - w) // 2
                g = g[oy:oy + h, ox:ox + w]
                fr, main = base(g)
                main = (main.astype(np.float32) * 0.45).astype(np.uint8)
                fr[PY:PY + PH] = main
                if rank is not None:
                    key = f"big#{rank}"
                    bcache.setdefault(key, badge(f"#{rank}", 300))
                    amp.paste(fr, bcache[key], W / 2, PY + PH / 2 - 40)
                fr = overlay(fr, t0 + j / FPS, rank, card=True)
                enc.stdin.write(fr.tobytes())
    enc.stdin.close()
    enc.wait()
    au = np.concatenate([x[:int(round(len(x) / SR * FPS)) * SR // FPS] for x in audio])
    wav = out_dir / f"_{spec['id']}.wav"
    wf = wave.open(str(wav), "wb")
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(SR)
    wf.writeframes((np.clip(au, -1, 1) * 32767).astype("<i2").tobytes())
    wf.close()
    out = out_dir / f"PRIVATE-TEST_{spec['id']}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5", "-shortest",
                    str(out)], check=True)
    tmp.unlink()
    wav.unlink()
    return out, round(total, 1)
