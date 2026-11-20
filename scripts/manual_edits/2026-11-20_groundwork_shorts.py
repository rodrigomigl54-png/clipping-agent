"""2026-11-20 Groundwork / Leonida Files shorts, rebuilt from today's viral patterns with FRESH official footage
(Rockstar's "now available" spot + the Extended Look cut-downs from Rockstar's TikTok; none used on earlier days).

A  ambience  : one calm caption, 2 long takes (rooftop hand-hold -> skydive over Vice City), sound "limerence"
B  hype      : 3 s hook on Lucia's close-up, then a cut every 2 beats (GOOD LOOKING (HARDTEKK)), caption all the way
M1 meme      : caption on black + 4:5 footage (Lucia walks away from the burning car)
M2 meme      : caption on black + 4:5 footage (Jason & Lucia arrive at the rooftop party of dancing grandparents)

Rockstar's "RP" rating badge (bottom-left of the Extended Look clips) is cropped out wherever it is on screen.
Usage: python scripts/manual_edits/2026-11-20_groundwork_shorts.py [A B M1 M2]
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from clipper.editing.lyric_fx import caption_rgba  # noqa: E402

W, H, FPS = 1080, 1920, 30
EXT = ROOT / "assets/footage/gta6_extended"
REF = ROOT / "assets/hype_refs/1120"
OUT = ROOT / "outputs/_PRIVATE_TEST/GTA6/2026-11-20"
NO_BADGE = (0.16, 0.0, 0.84, 0.84)        # x, y, w, h fractions: drops the bottom-left RP badge (zoom 1.19x)


def clip(name, start, dur, out_wh=(W, H), crop=(0, 0, 1, 1), speed=1.0, zoom=(1.0, 1.0)):
    """Frames of `dur` s from assets/footage/gta6_extended/<name>.mp4, cropped (fractions) and scaled; speed<1 = slow-mo."""
    src = EXT / f"{name}.mp4"
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(src)], capture_output=True, text=True, check=True).stdout.strip().split(",")
    sw, sh = int(o[0]), int(o[1])
    ow, oh = out_wh
    cx, cy, cw, ch = crop
    # fit the output aspect inside the crop box
    bw, bh = cw * sw, ch * sh
    if bw / bh > ow / oh:
        bw = bh * ow / oh
    else:
        bh = bw * oh / ow
    x0 = cx * sw + (cw * sw - bw) / 2
    y0 = cy * sh + (ch * sh - bh) / 2
    scale = ow / bw * zoom[1]
    assert scale <= 2.05, f"{name}: upscale {scale:.2f}x would be blurry"
    bw, bh, x0, y0 = int(bw) // 2 * 2, int(bh) // 2 * 2, int(x0), int(y0)
    n = int(round(dur * FPS))
    vf = f"crop={bw}:{bh}:{x0}:{y0},scale={ow}:{oh}:flags=lanczos,setpts=PTS/{speed:.4f},fps={FPS}"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{dur * speed + 0.3:.3f}",
                          "-vf", vf, "-an", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    last = np.zeros((oh, ow, 3), np.uint8)
    for i in range(n):
        buf = p.stdout.read(ow * oh * 3)
        if len(buf) == ow * oh * 3:
            last = np.frombuffer(buf, np.uint8).reshape(oh, ow, 3)
        z = zoom[0] + (zoom[1] - zoom[0]) * i / max(1, n - 1)
        if z > 1.0:
            f = cv2.resize(last, None, fx=z, fy=z, interpolation=cv2.INTER_CUBIC)
            yy, xx = (f.shape[0] - oh) // 2, (f.shape[1] - ow) // 2
            yield np.ascontiguousarray(f[yy:yy + oh, xx:xx + ow])
        else:
            yield last
    p.stdout.close()
    p.wait()


def text_block(text, size, max_w):
    """Word-wrapped caption (white, colour emoji) as one BGRA image, lines centred."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if cur and caption_rgba(t, size).shape[1] > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = t
    lines.append(cur)
    imgs = [caption_rgba(line, size) for line in lines]
    gap = int(size * 0.18)
    bw = max(i.shape[1] for i in imgs)
    bh = sum(i.shape[0] for i in imgs) + gap * (len(imgs) - 1)
    out = np.zeros((bh, bw, 4), np.uint8)
    y = 0
    for i in imgs:
        x = (bw - i.shape[1]) // 2
        out[y:y + i.shape[0], x:x + i.shape[1]] = i
        y += i.shape[0] + gap
    return cv2.cvtColor(out, cv2.COLOR_RGBA2BGRA)


def paste(frame, img, cx, cy, alpha=1.0):
    h, w = img.shape[:2]
    x, y = int(cx - w / 2), int(cy - h / 2)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(frame.shape[1], x + w), min(frame.shape[0], y + h)
    part = img[y0 - y:y1 - y, x0 - x:x1 - x]
    a = part[..., 3:4].astype(np.float32) / 255 * alpha
    frame[y0:y1, x0:x1] = (frame[y0:y1, x0:x1] * (1 - a) + part[..., :3] * a).astype(np.uint8)


def grade(f, sat=1.08, warm=0.0):
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * sat, 0, 255)
    f = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    if warm:
        f = np.clip(f.astype(np.float32) + np.array([-warm, 0, warm]), 0, 255).astype(np.uint8)
    return f


class Enc:
    def __init__(self, path):
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                                   "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "15",
                                   "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)
        self.n = 0

    def put(self, f):
        self.p.stdin.write(np.ascontiguousarray(f).tobytes())
        self.n += 1

    def close(self):
        self.p.stdin.close()
        self.p.wait()


def mux_audio(silent, audio, out, dur, src_start=0.0):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-ss", f"{src_start:.3f}", "-i", str(audio),
                    "-map", "0:v", "-map", "1:a", "-t", f"{dur:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-af", f"afade=t=out:st={dur - 0.4:.2f}:d=0.4", str(out)], check=True)


def clip_audio(name, out):
    """Original audio of an official clip (PyAV: some TikTok files carry an odd channel layout ffmpeg rejects)."""
    import av
    import wave
    c = av.open(str(EXT / f"{name}.mp4"))
    if not c.streams.audio:
        return None
    s = c.streams.audio[0]
    a = np.concatenate([fr.to_ndarray() for fr in c.decode(s)], axis=1)
    if a.dtype != np.float32:
        a = a.astype(np.float32) / 32768
    pcm = (np.clip(a.T, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(s.rate)
        w.writeframes(pcm.tobytes())
    return out


# --------------------------------------------------------------------------------------------- A: ambience
def edit_a():
    dur, xf = 11.03, 0.5
    cap = text_block("after 13 years we finally get to live here 🥹🌴", 80, 960)
    a = list(clip("ext_44", 12.6, 5.6 + xf, zoom=(1.0, 1.06)))
    b = list(clip("ext_12s", 2.9, dur - 5.6, crop=NO_BADGE, zoom=(1.0, 1.05)))
    silent = OUT / "PRIVATE-TEST_gta6_live_here_silent.mp4"
    e = Enc(silent)
    na = int(round(5.6 * FPS))
    nx = int(round(xf * FPS))
    for i in range(int(round(dur * FPS))):
        if i < na:
            f = a[i]
        elif i < na + nx:
            k = (i - na) / nx
            f = cv2.addWeighted(a[i], 1 - k, b[i - na], k, 0)
        else:
            f = b[min(i - na, len(b) - 1)]
        f = grade(f, 1.06, 4)
        paste(f, cap, W / 2, H * 0.30, min(1.0, i / 8))
        e.put(f)
    e.close()
    out = OUT / "PRIVATE-TEST_gta6_live_here.mp4"
    mux_audio(silent, REF / "mori_limerence.wav", out, dur)
    return out


# --------------------------------------------------------------------------------------------- B: hype
B_SHOTS = [  # (start of segment in the song, clip, source start, crop, speed)
    (0.00, "now_available", 13.90, None, 0.5),   # hook: Lucia close-up, slow-mo
    (3.02, "ext_12s", 3.30, NO_BADGE, 1.0),      # skydive
    (3.99, "ext_19b", 12.60, None, 1.0),         # bench press
    (4.97, "now_available", 35.45, None, 0.85),  # Lucia at sunset
    (5.94, "ext_32", 2.00, NO_BADGE, 1.0),       # walks off from the burning car
    (6.90, "ext_44", 15.00, None, 1.0),          # rooftop hand-hold
    (7.87, "now_available", 45.32, None, 0.72),  # Lucia shooting (camera pans onto her at 45.3)
    (8.85, "ext_19a", 4.00, NO_BADGE, 1.0),      # dirt bike
    (9.80, "ext_44", 3.20, NO_BADGE, 1.0),       # elevator, pink dress
    (10.77, "now_available", 39.40, None, 1.0),  # Jason & Lucia
    (11.73, "ext_12s", 6.50, NO_BADGE, 1.0),     # parachute over Vice City
    (12.70, "now_available", 24.00, None, 1.0),  # silhouette at the window
]


def edit_b():
    dur = 13.63
    cap = text_block("Lucia from GTA 6 is HIM 😮‍💨🔥", 88, 960)
    silent = OUT / "PRIVATE-TEST_gta6_lucia_him_silent.mp4"
    e = Enc(silent)
    bounds = [s[0] for s in B_SHOTS] + [dur]
    for (t0, name, ss, crop, sp), t1 in zip(B_SHOTS, bounds[1:]):
        n = int(round(t1 * FPS)) - int(round(t0 * FPS))
        frames = clip(name, ss, n / FPS, crop=crop or (0, 0, 1, 1), speed=sp, zoom=(1.0, 1.07 if t0 else 1.04))
        for j, f in enumerate(frames):
            if j >= n:
                break
            f = grade(f, 1.12)
            if t0 == 3.02 and j < 4:                       # white flash on the drop
                f = cv2.addWeighted(f, 1 - (4 - j) / 5, np.full_like(f, 255), (4 - j) / 5, 0)
            paste(f, cap, W / 2, H * 0.20)
            e.put(f)
    e.close()
    out = OUT / "PRIVATE-TEST_gta6_lucia_him.mp4"
    mux_audio(silent, REF / "hav_arthur.wav", out, dur)
    return out


# --------------------------------------------------------------------------------------------- memes
def meme(name, start, dur, text, slug, crop=(0, 0.05, 1, 0.78)):
    box_h = 1350                                      # 4:5 picture
    top = 470
    cap = text_block(text, 70, 1000)
    silent = OUT / f"PRIVATE-TEST_gta6_meme_{slug}_silent.mp4"
    e = Enc(silent)
    for f in clip(name, start, dur, out_wh=(W, box_h), crop=crop):
        frame = np.zeros((H, W, 3), np.uint8)
        frame[top:top + box_h] = grade(f, 1.05)
        paste(frame, cap, W / 2, top / 2 + 10)
        e.put(frame)
    e.close()
    wav = clip_audio(name, OUT / f"_{slug}.wav")
    out = OUT / f"PRIVATE-TEST_gta6_meme_{slug}.mp4"
    if wav:
        mux_audio(silent, wav, out, dur, src_start=start)
        wav.unlink()
    return out


def meme1():
    return meme("ext_32", 1.0, 7.5, "Me leaving the group chat after they spoiled the GTA 6 ending 💀", "groupchat",
                crop=(0.1, 0.04, 0.9, 0.64))          # keeps the RP badge (bottom-left) out of the picture


def meme2():
    return meme("ext_44", 19.0, 13.0,
                "Jason & Lucia pulling up to a Leonida rooftop party full of Florida grandparents 😭", "rooftop")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {"A": edit_a, "B": edit_b, "M1": meme1, "M2": meme2}
    for k in sys.argv[1:] or list(jobs):
        print(k, jobs[k]())
