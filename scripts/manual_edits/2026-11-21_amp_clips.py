"""2026-11-21 AMP clips (Kai Cenat first, Agent00) — vertical 1080x1920, our own cut and our own text.

Layout ("AMP v2", different from the 11-18 clips): the whole stream frame (facecam included, so the streamer is
on screen the entire clip) in the middle over a blurred, darkened copy of itself; a two-line headline on top with
the streamer's name in yellow; word-by-word subtitles under the picture (current word yellow); quick zoom-ins on
the key moment. Stream audio only (no music baked in — the post kit says which song to add in the app).

Sources (assets/streams/2026-11-21/, imported with the free vidIQ import, private test):
  kai_play2.mp4        Kai Cenat Gaming "Kai Cenat Picks Up Lucia From Prison | GTA 6 Playthrough #2" (80n7Nk1XL7s)
  kai_6stars.mp4       Kai Cenat Gaming "I Tried Escaping 6 Stars In GTA 6..." (Kupe41kll08)
  agent_6stars.mp4     Agent 00 "How Long Can I Survive With 6 Stars on GTA 6" (xnpE_061zG8)
  agent_military.mp4   Agent 00 "I Stole EVERY Military Vehicle in GTA 6.." (4PI8D0fDQ7c)
  kai_mandy_a_src.mp4  Kai's Mandy scene, from a small clip channel upload (-H0WiiGjz_s) — the only copy reachable
  agent_mandy_src.mp4  Agent's Mandy scene, from a small clip channel upload (lh3_WE5eOlY)
Usage: python scripts/manual_edits/2026-11-21_amp_clips.py [clip ids...]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "assets/streams/2026-11-21"
OUT = ROOT / "outputs/_PRIVATE_TEST/AMP/2026-11-21"
ANTON = str(ROOT / "assets/fonts/Anton-Regular.ttf")
W, H, FPS = 1080, 1920, 30
PW, PH, PY = 1080, 608, 676                       # main picture
YELLOW, WHITE = (255, 214, 0), (255, 255, 255)
BAD = {"fuck": "f*ck", "fucking": "f*cking", "motherfucker": "m*therf*cker", "shit": "sh*t", "bitch": "b*tch",
       "nigga": "n*gga", "niggas": "n*ggas", "pussy": "p*ssy", "ass": "a**", "sex": "s*x", "ballsack": "b*llsack"}

# id: src, parts [(start, end)], headline (name in {braces} = yellow), zooms [(t_src, cx, cy, zoom, dur)],
#     blur [(t0_src, t1_src, x0, y0, x1, y1)] (Mandy's body), fix: transcript corrections
CLIPS = {}


def clip(cid, src, parts, headline, zooms=(), blur=(), fix=None):
    CLIPS[cid] = dict(src=src, parts=parts, headline=headline, zooms=list(zooms), blur=list(blur), fix=fix or {})


# ------------------------------------------------------------------ AGENT00
clip("agent_warning", "agent_military", [(222.0, 271.6)],
     ["GTA 6 TOLD {AGENT 00} TO CALM DOWN", "SO HE TOOK A TANK INSTEAD"],
     zooms=[(229.0, 0.12, 0.27, 1.9, 4.2), (253.6, 0.84, 0.78, 1.7, 1.6)])
CLIPS["agent_warning"]["fix"] = {"lusia": "LUCIA"}
clip("agent_tight", "agent_6stars", [(63.5, 79.0), (88.6, 101.0)],
     ["{AGENT 00} GOT STUCK INSIDE", "A TANK IN GTA 6"],
     zooms=[(90.5, 0.84, 0.78, 1.6, 2.2)])
clip("agent_magician", "agent_military", [(606.0, 629.4)],
     ["{AGENT 00} LOST 6 STARS IN SECONDS", "AND CALLED HIMSELF A MAGICIAN"],
     zooms=[(617.6, 0.84, 0.78, 1.7, 2.6)])
clip("agent_cargo", "agent_military", [(855.5, 873.6), (883.5, 905.0)],
     ["{AGENT 00} TRIED TO STEAL A CARGO PLANE", "THE STAIRS HAD OTHER PLANS"],
     zooms=[(889.0, 0.84, 0.78, 1.6, 2.0)])
clip("agent_mandy", "agent_mandy_src", [(2.4, 28.2)],
     ["{AGENT 00} MET MANDY IN GTA 6", "AND DID IT ALL \"FOR THE PLOT\""],
     blur=[(18.8, 28.3, 0.17, 0.12, 0.56, 1.0)])


def wrap(lines):
    return lines


# ------------------------------------------------------------------ rendering helpers
def font(size):
    return ImageFont.truetype(ANTON, size)


def rich_line(text, size, stroke=7):
    """'{NAME} REST' -> RGBA image, {..} parts yellow."""
    parts = re.split(r"(\{[^}]*\})", text)
    f = font(size)
    segs = [(p[1:-1], YELLOW) if p.startswith("{") else (p, WHITE) for p in parts if p]
    widths = [f.getlength(s) for s, _ in segs]
    w = int(sum(widths)) + 2 * stroke + 6
    h = int(size * 1.3) + 2 * stroke
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = stroke + 3
    for (s, col), sw in zip(segs, widths):
        d.text((x, stroke), s, font=f, fill=col + (255,), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        x += sw
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGBA2BGRA)


def fit(text, max_w, size):
    while size > 40:
        im = rich_line(text, size)
        if im.shape[1] <= max_w:
            return im
        size -= 4
    return rich_line(text, size)


def paste(fr, im, cx, cy):
    h, w = im.shape[:2]
    x, y = int(cx - w / 2), int(cy - h / 2)
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, fr.shape[1]), min(y + h, fr.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    sub = im[y0 - y:y1 - y, x0 - x:x1 - x]
    a = sub[..., 3:4].astype(np.float32) / 255
    fr[y0:y1, x0:x1] = (fr[y0:y1, x0:x1] * (1 - a) + sub[..., :3] * a).astype(np.uint8)


def read_frames(path, start, dur):
    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip().split(",")
    sw, sh = int(p[0]), int(p[1])
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(path), "-t", f"{dur:.3f}",
                          "-vf", f"fps={FPS}", "-an", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         capture_output=True, check=True).stdout
    n = len(raw) // (sw * sh * 3)
    return [np.frombuffer(raw[i * sw * sh * 3:(i + 1) * sw * sh * 3], np.uint8).reshape(sh, sw, 3) for i in range(n)]


def audio(path, parts, sr=48000):
    out = []
    for a, b in parts:
        p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(path), "-vn",
                            "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
        x = np.frombuffer(p, np.float32).reshape(-1, 2).copy()
        f = min(len(x), int(0.04 * sr))
        x[:f] *= np.linspace(0, 1, f)[:, None]
        x[-f:] *= np.linspace(1, 0, f)[:, None]
        out.append(x)
    return np.concatenate(out)


def words_for(src, parts, fix):
    d = json.loads((SRC / f"{src}.words.json").read_text())
    ws, off = [], 0.0
    for a, b in parts:
        for s in d["segs"]:
            for w, t in s["w"]:
                if a <= t < b:
                    k = re.sub(r"[^\w'*]", "", w).lower()
                    w2 = fix.get(k, BAD.get(k, None))
                    txt = (w2 if w2 else re.sub(r"[^\w'?!*.,-]", "", w)).upper()
                    if txt:
                        ws.append((off + t - a, txt))
        off += b - a
    return ws


def sub_chunks(ws):
    """group words into on-screen chunks of up to 3 words (break on long gaps)."""
    chunks, cur = [], []
    for i, (t, w) in enumerate(ws):
        if cur and (len(cur) == 3 or t - cur[-1][0] > 0.7):
            chunks.append(cur)
            cur = []
        cur.append((t, w))
    if cur:
        chunks.append(cur)
    out = []
    for i, c in enumerate(chunks):
        end = chunks[i + 1][0][0] if i + 1 < len(chunks) else c[-1][0] + 1.2
        out.append((c[0][0], min(end, c[-1][0] + 1.3), c))
    return out


def sub_image(chunk, t, cache):
    active = max(i for i, (tw, _) in enumerate(chunk) if tw <= t + 0.02) if any(tw <= t + 0.02 for tw, _ in chunk) else 0
    key = (tuple(w for _, w in chunk), active)
    if key not in cache:
        txt = " ".join(("{%s}" % w) if i == active else w for i, (_, w) in enumerate(chunk))
        cache[key] = fit(txt, 1000, 92)
    return cache[key]


def zoom_frame(f, z, cx, cy):
    h, w = f.shape[:2]
    cw, ch = w / z, h / z
    x0 = min(max(cx * w - cw / 2, 0), w - cw)
    y0 = min(max(cy * h - ch / 2, 0), h - ch)
    return f[int(y0):int(y0 + ch), int(x0):int(x0 + cw)]


def render(cid):
    c = CLIPS[cid]
    path = SRC / f"{c['src']}.mp4"
    OUT.mkdir(parents=True, exist_ok=True)
    head = [fit(line, 1010, 84) for line in c["headline"]]
    words = sub_chunks(words_for(c["src"], c["parts"], c["fix"]))
    cache = {}
    tmp = OUT / f"_{cid}.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
                            "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    t_out = 0.0
    for a, b in c["parts"]:
        frames = read_frames(path, a, b - a)
        for j, f in enumerate(frames):
            ts = a + j / FPS                      # source time
            to = t_out + j / FPS                  # output time
            sh, sw = f.shape[:2]
            for t0, t1, x0, y0, x1, y1 in c["blur"]:
                if t0 <= ts <= t1:
                    X0, Y0, X1, Y1 = int(x0 * sw), int(y0 * sh), int(x1 * sw), int(y1 * sh)
                    roi = f[Y0:Y1, X0:X1]
                    small = cv2.resize(roi, (max(1, (X1 - X0) // 28), max(1, (Y1 - Y0) // 28)))
                    f = f.copy()
                    f[Y0:Y1, X0:X1] = cv2.GaussianBlur(cv2.resize(small, (X1 - X0, Y1 - Y0),
                                                                  interpolation=cv2.INTER_NEAREST), (0, 0), 6)
            pic = f
            for zt, zx, zy, zz, zd in c["zooms"]:
                if zt <= ts <= zt + zd:
                    k = (ts - zt) / zd
                    ease = min(1.0, k / 0.12) if k < 0.85 else max(0.0, (1 - k) / 0.15)
                    pic = zoom_frame(f, 1 + (zz - 1) * ease, zx, zy)
            main = cv2.resize(pic, (PW, PH), interpolation=cv2.INTER_LANCZOS4)
            bg = cv2.resize(f, (192, 108))
            bg = cv2.GaussianBlur(bg, (0, 0), 6)
            bh = H
            bwid = int(bh * 192 / 108)
            bg = cv2.resize(bg, (bwid, bh))
            x = (bwid - W) // 2
            fr = (bg[:, x:x + W].astype(np.float32) * 0.38).astype(np.uint8)
            cv2.rectangle(fr, (0, PY - 6), (W, PY + PH + 6), (20, 20, 20), -1)
            fr[PY:PY + PH] = main
            y = 300 if len(head) > 1 else 400
            for im in head:
                paste(fr, im, W / 2, y + im.shape[0] / 2)
                y += im.shape[0] - 10
            for s0, s1, ch in words:
                if s0 <= to < s1:
                    paste(fr, sub_image(ch, to, cache), W / 2, PY + PH + 170)
                    break
            enc.stdin.write(fr.tobytes())
        t_out += len(frames) / FPS
    enc.stdin.close()
    enc.wait()
    a = audio(path, c["parts"])
    wav = OUT / f"_{cid}.wav"
    import wave
    w = wave.open(str(wav), "wb")
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(48000)
    w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
    w.close()
    name = "agent00" if cid.startswith("agent") else "kaicenat"
    out = OUT / f"PRIVATE-TEST_amp_{cid}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5", "-shortest",
                    str(out)], check=True)
    tmp.unlink()
    wav.unlink()
    return out, round(t_out, 1), name


if __name__ == "__main__":
    for cid in sys.argv[1:] or list(CLIPS):
        print(cid, render(cid), flush=True)
