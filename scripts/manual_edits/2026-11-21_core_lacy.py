"""2026-11-21 CORE channel — Lacy's most viral GTA 6 moments, re-cut with our own headline and captions.

Owner's brief: take Lacy's clips that already went viral and give them better (clickbait / retention) titles.
Sources: the 8 most-viewed GTA 6 posts on Lacy's OFFICIAL verified TikTok @lacy (5.8M followers) from his GTA 6
marathon — the full marathon VODs (5–12 h each) are too big for the free import, so these are the only copies we
can reach. The Lacy campaigns allow Lacy's own TikTok as a source; we never re-upload as-is: their burned-in
caption is removed (inpainted), the square video is put in our vertical layout with our own headline on top and
word-by-word captions below. Audio is the post's own audio (some posts already carry a TikTok sound).

Files: assets/streams/2026-11-21/lacy_tt/<id>.mp4 (+ .words.json from faster-whisper)
Output: outputs/_PRIVATE_TEST/CORE/2026-11-21/PRIVATE-TEST_core_lacy_<id>.mp4
Usage: python scripts/manual_edits/2026-11-21_core_lacy.py [ids...]
"""
import importlib.util
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("amp", ROOT / "scripts/manual_edits/2026-11-21_amp_clips.py")
amp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(amp)

SRC = ROOT / "assets/streams/2026-11-21/lacy_tt"
OUT = ROOT / "outputs/_PRIVATE_TEST/CORE/2026-11-21"
W, H, FPS = 1080, 1920, 30
S, PY = 1080, 430                      # square picture size / top

# id: (tiktok id, views when found, headline lines, word fixes)
CLIPS = {
    "mandy":    ("7710078579719081229", "1.7M", ["{LACY} SNUCK INTO MANDY'S ROOM", "WAIT FOR WHAT'S ON HER DESK..."], {}),
    "lovegta":  ("7710120296258211085", "976K", ["{LACY}'S GIRLFRIEND CAN NEVER", "SEE THIS GTA 6 CLIP"], {"ahhh": "AHHH!"}),
    "lucia":    ("7710113766486052109", "519K", ["{LACY} IS THE LAST", "GENTLEMAN IN GTA 6"], {}),
    "lostmind": ("7710472541181070606", "461K", ["{LACY} FOUND THE MOST EVIL", "THING YOU CAN DO IN GTA 6"], {}),
    "evil":     ("7710043930028494093", "282K", ["MANDY SAID \"COME OVER\"...", "{LACY} BECAME A DIFFERENT MAN"], {}),
    "13years":  ("7710348625607560461", "127K", ["{LACY} WAITED 13 YEARS FOR GTA 6", "...AND GOT THIS"], {"chet": "CHAT"}),
    "lost":     ("7710436920605641997", "50K",  ["{LACY}'S PS5 DIED IN THE MIDDLE", "OF HIS GTA 6 MARATHON"], {}),
    "showers":  ("7710404957215706381", "47K",  ["{LACY} SET A GTA 6 WORLD RECORD", "NOBODY ASKED FOR"], {}),
}


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                          "-show_entries", "format=duration", "-of", "json", str(path)], capture_output=True,
                         text=True, check=True).stdout
    j = json.loads(out)
    return j["streams"][0]["width"], j["streams"][0]["height"], float(j["format"]["duration"])


def frames(path, w, h):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps={FPS}", "-f", "rawvideo",
                          "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    n = w * h * 3
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, 3)
    p.wait()


# posts whose caption changes / disappears: detect separately in each time window
CAPWIN = {"evil": [(0.0, 10.6), (10.9, 99.0)], "showers": [(0.0, 3.1), (4.6, 99.0)]}


def caption_mask(path, w, h, t0, t1):
    """The post's caption is the only thing that stays still and bright in the window -> find it."""
    samp = []
    for k in range(48):
        t = t0 + (k + 0.5) * (t1 - t0) / 48
        b = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                            "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
        if len(b) == w * h * 3:
            samp.append(np.frombuffer(b, np.uint8).reshape(h, w, 3))
    st = np.stack(samp).astype(np.float32)
    mn = st.min(axis=0)                                    # darkest value each pixel ever had
    std = st.std(axis=0).mean(axis=2)
    bright = (mn.min(axis=2) > 175) & (std < 14)           # white letters, never moving
    hsv = cv2.cvtColor(np.median(st, axis=0).astype(np.uint8), cv2.COLOR_BGR2HSV)
    colour = (hsv[..., 1] > 90) & (hsv[..., 2] > 90) & (std < 10)   # emojis
    blocks = cv2.morphologyEx(bright.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((25, 61), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(blocks)
    best = max(range(1, n), key=lambda i: (stats[i, 2] > 200) * stats[i, 4], default=None)
    if best is None:
        return None, None
    x, y, bw, bh = stats[best, :4]
    x0, y0, x1, y1 = max(0, x - 140), max(0, y - 30), min(w, x + bw + 140), min(h, y + bh + 30)
    # second caption line just below/above belongs to the same caption
    for i in range(1, n):
        if i != best and stats[i, 2] > 150 and abs(stats[i, 1] - (y + bh)) < 70 or \
                i != best and stats[i, 2] > 150 and abs(stats[i, 1] + stats[i, 3] - y) < 70:
            xx, yy, ww, hh = stats[i, :4]
            x0, y0, x1, y1 = min(x0, xx - 140), min(y0, yy - 30), max(x1, xx + ww + 140), max(y1, yy + hh + 30)
    x0, y0 = max(0, x0), max(0, y0)
    m = np.zeros((h, w), np.uint8)
    sub = (bright | colour)[y0:y1, x0:x1].astype(np.uint8)
    m[y0:y1, x0:x1] = cv2.dilate(sub, np.ones((17, 17), np.uint8))
    return m * 255, (x0, y0, x1, y1)


def words(cid, fix):
    d = json.loads((SRC / f"{cid}.words.json").read_text())
    ws = []
    for s in d["segs"]:
        for w, t in s["w"]:
            k = re.sub(r"[^\w'*]", "", w).lower()
            w2 = fix.get(k, amp.BAD.get(k))
            txt = (w2 if w2 else re.sub(r"[^\w'?!*.,-]", "", w)).upper()
            if txt:
                ws.append((t, txt))
    return amp.sub_chunks(ws)


def render(cid):
    tid, views, headline, fix = CLIPS[cid]
    path = SRC / f"{cid}.mp4"
    w, h, dur = probe(path)
    wins = [(a, min(b, dur)) for a, b in CAPWIN.get(cid, [(0.0, dur)])]
    masks = [(a, b) + caption_mask(path, w, h, a, b) for a, b in wins]
    OUT.mkdir(parents=True, exist_ok=True)
    head = [amp.fit(line, 1010, 84) for line in headline]
    subs = words(cid, fix)
    cache = {}
    tmp = OUT / f"_{cid}.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                            "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    nfr = 0
    for j, f in enumerate(frames(path, w, h)):
        t = j / FPS
        for a, b, mask, box in masks:
            if a <= t < b and mask is not None:
                x0, y0, x1, y1 = box
                f = f.copy()
                f[y0:y1, x0:x1] = cv2.inpaint(f[y0:y1, x0:x1], mask[y0:y1, x0:x1], 7, cv2.INPAINT_TELEA)
        sq = cv2.resize(f, (S, int(S * h / w)), interpolation=cv2.INTER_AREA if w > S else cv2.INTER_LANCZOS4)
        bg = cv2.GaussianBlur(cv2.resize(f, (108, int(108 * h / w))), (0, 0), 5)
        bg = cv2.resize(bg, (int(H * w / h), H))
        xo = (bg.shape[1] - W) // 2
        fr = (bg[:, xo:xo + W].astype(np.float32) * 0.36).astype(np.uint8)
        ph = sq.shape[0]
        top = PY if ph <= 1080 else max(0, (H - ph) // 2)
        cv2.rectangle(fr, (0, top - 6), (W, top + ph + 6), (20, 20, 20), -1)
        fr[top:top + ph] = sq[:H - top]
        y = 200
        for im in head:
            amp.paste(fr, im, W / 2, y + im.shape[0] / 2)
            y += im.shape[0] - 10
        for s0, s1, ch in subs:
            if s0 <= t < s1:
                amp.paste(fr, amp.sub_image(ch, t, cache), W / 2, top + ph + 150)
                break
        enc.stdin.write(fr.tobytes())
        nfr += 1
    enc.stdin.close()
    enc.wait()
    a = amp.audio(path, [(0.0, dur)])
    wav = OUT / f"_{cid}.wav"
    wf = wave.open(str(wav), "wb")
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(48000)
    wf.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
    wf.close()
    out = OUT / f"PRIVATE-TEST_core_lacy_{cid}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5", "-shortest",
                    str(out)], check=True)
    tmp.unlink()
    wav.unlink()
    return out, round(nfr / FPS, 1), [m[3] for m in masks]


if __name__ == "__main__":
    for cid in sys.argv[1:] or list(CLIPS):
        print(cid, render(cid), flush=True)
