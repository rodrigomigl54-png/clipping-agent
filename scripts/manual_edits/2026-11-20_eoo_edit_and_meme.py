"""2026-11-20 (round 2): the owner's two references, rebuilt with official Rockstar gameplay (Extended Look, 1080p copy).

EDIT  "GTA VI x EoO" style (@yadzuharu): 4:3 picture on black, NO text, every cut on the song's grid
      (half-beats in the intro, stutter bursts on the drum fills, one cut per beat with a punch-zoom on the drop).
MEME  caption on top + the real Extended Look line: "Are you a professional, Lucia?" ... "Huh? ... Of course."

Usage: python scripts/manual_edits/2026-11-20_eoo_edit_and_meme.py [EDIT MEME]
"""
import bisect
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import cv2  # noqa: E402
import numpy as np  # noqa: E402

W, H, FPS = 1080, 1920, 30
EL = ROOT / "assets/footage/gta6_official/extended_look_1080.mp4"
REF = ROOT / "assets/hype_refs/1120"
OUT = ROOT / "outputs/_PRIVATE_TEST/GTA6/2026-11-20"
CUTS = [float(x) for x in (ROOT / "data/shot_cache/extended_look_cuts.txt").read_text().split()]
PW, PH = 1080, 810                      # 4:3 picture
PY = (H - PH) // 2


def fit_start(t, dur):
    """Move t back so [t, t+dur] does not cross a shot boundary of the Extended Look."""
    i = bisect.bisect_right(CUTS, t)
    nxt = CUTS[i] if i < len(CUTS) else 1e9
    prev = CUTS[i - 1] if i else 0.0
    if t + dur > nxt - 0.04:
        t = max(prev + 0.04, nxt - 0.04 - dur)
    if 352 <= t <= 380:                    # title cards ("Rockstar Games presents", VI logo)
        t = 380.5
    return t


def frames(t, dur, cx=0.5, size=(PW, PH)):
    """`dur` seconds of the Extended Look from t, 4:3 crop around cx, as BGR frames."""
    n = int(round(dur * FPS))
    cw = 1440
    x = int(min(max(cx * 1920 - cw / 2, 0), 1920 - cw))
    vf = f"crop={cw}:1080:{x}:0,scale={size[0]}:{size[1]}:flags=lanczos,fps={FPS}"
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(EL), "-t", f"{dur + 0.2:.3f}", "-vf", vf,
                        "-an", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True, check=True).stdout
    fs = [np.frombuffer(p[i * size[0] * size[1] * 3:(i + 1) * size[0] * size[1] * 3], np.uint8).reshape(size[1], size[0], 3)
          for i in range(len(p) // (size[0] * size[1] * 3))]
    while len(fs) < n:
        fs.append(fs[-1] if fs else np.zeros((size[1], size[0], 3), np.uint8))
    return fs[:n]


def grade(f):
    m = float(f.mean())
    if m < 70:                                   # lift dark night shots so the drop doesn't go muddy
        g = 0.62 + 0.38 * m / 70
        f = (255 * (f / 255.0) ** g).astype(np.uint8)
    f = cv2.convertScaleAbs(f, alpha=1.08, beta=-6)
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.12, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def punch(f, k):
    """Zoom-in that settles: k=0 -> 1.10x, k=1 -> 1.0x."""
    z = 1.0 + 0.10 * (1 - min(1.0, k)) ** 2
    if z <= 1.001:
        return f
    h, w = f.shape[:2]
    g = cv2.resize(f, None, fx=z, fy=z, interpolation=cv2.INTER_LINEAR)
    y, x = (g.shape[0] - h) // 2, (g.shape[1] - w) // 2
    return g[y:y + h, x:x + w]


class Enc:
    def __init__(self, path):
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                                   "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "15",
                                   "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)
        self.n = 0

    def put(self, pic):
        f = np.zeros((H, W, 3), np.uint8)
        f[PY:PY + PH] = pic
        self.p.stdin.write(f.tobytes())
        self.n += 1

    def close(self):
        self.p.stdin.close()
        self.p.wait()


# ------------------------------------------------------------------------------------------------ EDIT
BEATS = [0.09, 0.7, 1.28, 1.86, 2.46, 3.02, 3.65, 4.25, 4.83, 5.39, 5.99, 6.57, 7.17, 7.76, 8.34, 8.94, 9.52, 10.1, 10.73,
         11.28, 11.87, 12.47, 13.07, 13.63, 14.23, 14.79, 15.39, 16.0, 16.6, 17.18, 17.79, 18.37, 18.92, 19.5, 20.09,
         20.69, 21.27, 21.85, 22.43, 23.03, 23.61, 24.2, 24.8, 25.38, 25.96, 26.56, 27.14, 27.72]
SONG_END = 29.2

# official Extended Look moments (seconds, crop centre) grouped by mood
CALM = [(380.5, .5), (396.5, .45), (404.5, .5), (412.5, .55), (464.5, .5), (468.5, .5), (516.5, .5), (528.5, .5),
        (992.5, .5), (1028.5, .5), (1044.5, .5), (1048.5, .5), (1108.5, .5), (1140.5, .5), (1132.5, .5), (1128.5, .5)]
MID = [(496.5, .45), (544.5, .5), (568.5, .5), (576.5, .6), (704.5, .5), (712.5, .5), (716.5, .55),
       (720.5, .5), (760.5, .5), (1032.5, .5), (1036.5, .5), (1040.5, .5), (1068.5, .5), (1080.5, .5), (1084.5, .5),
       (1088.5, .5), (1100.5, .5), (1116.5, .5), (1144.5, .5), (1156.5, .55), (1180.5, .5), (548.5, .5), (560.5, .5), (564.5, .5), (572.5, .5), (728.5, .5),
       (1012.5, .5), (1020.5, .5), (1072.5, .5), (1104.5, .5), (1160.5, .5), (1164.5, .5), (1184.5, .5), (1528.5, .5)]
HOT = [(552.5, .5), (696.5, .5), (848.5, .5), (862.5, .5), (1060.5, .5), (840.5, .5), (964.5, .5), (856.5, .5),
       (1064.5, .5), (1124.5, .5), (1548.5, .5), (1396.5, .5), (1520.5, .5), (1216.5, .5), (1544.5, .5), (1120.5, .5),
       (1212.5, .5), (1572.5, .5), (1388.5, .5), (1176.5, .5), (1220.5, .5), (1232.5, .5), (1224.5, .5), (1552.5, .5),
       (1248.5, .5), (1192.5, .5), (1240.5, .5), (1256.5, .5), (1268.5, .5), (1384.5, .5), (1392.5, .5), (1444.5, .5),
       (1464.5, .5)]
FINAL = (1568.2, .5)                     # sunset skyline


def timeline():
    """[(t0, t1, kind)] built from the song: kind in cut/stutter/drop."""
    half = [round((a + b) / 2, 2) for a, b in zip(BEATS, BEATS[1:])]
    grid = sorted(set(BEATS) | set(half))
    segs = []

    def cuts_between(a, b, every=1):
        pts = [t for t in grid if a <= t < b][::every]
        if not pts or pts[0] > a:
            pts = [a] + pts
        return [(x, y, "cut") for x, y in zip(pts, pts[1:] + [b])]

    segs += cuts_between(0.0, 2.46)                      # intro: every half-beat
    segs += cuts_between(2.46, 3.60, 2)                  # breathe
    segs += [(3.60, 3.82, "stutter")]
    segs += cuts_between(3.82, 4.81)
    segs += [(4.81, 5.66, "stutter")]
    segs += cuts_between(5.66, 12.40)
    segs += [(12.40, 13.30, "stutter")] + cuts_between(13.30, 13.85) + [(13.85, 14.22, "stutter")]
    segs += cuts_between(14.22, 15.27, 2) + [(15.27, 15.72, "stutter")]
    segs += cuts_between(15.72, 18.92)
    drop = [t for t in BEATS if 18.92 <= t < 28.3]
    segs += [(a, b, "drop") for a, b in zip(drop, drop[1:] + [28.3])]
    segs += [(28.3, SONG_END, "final")]
    return [(a, b, k) for a, b, k in segs if b - a > 0.02]


def edit():
    segs = timeline()
    pools = {"calm": list(CALM), "mid": list(MID), "hot": list(HOT)}

    def take(pool):
        p = pools[pool]
        if not p:
            pools[pool] = list({"calm": CALM, "mid": MID, "hot": HOT}[pool])
            p = pools[pool]
        return p.pop(0)

    silent = OUT / "PRIVATE-TEST_gta6_eoo_edit_silent.mp4"
    e = Enc(silent)
    for t0, t1, kind in segs:
        n = int(round(t1 * FPS)) - int(round(t0 * FPS))
        if n <= 0:
            continue
        pool = "calm" if t0 < 5.66 else ("mid" if t0 < 18.92 else "hot")
        if kind == "stutter":                          # flicker between 3 shots, 2 frames each
            shots = [take(pool) for _ in range(3)]
            fr = [frames(fit_start(s, n / FPS), n / FPS, cx) for s, cx in shots]
            for j in range(n):
                f = fr[(j // 2) % 3][j]
                if j % 4 == 0:
                    f = cv2.addWeighted(f, 0.75, np.full_like(f, 255), 0.25, 0)
                e.put(grade(f))
            continue
        if kind == "final":
            s, cx = FINAL
            fr = frames(s, n / FPS, cx)
            for j, f in enumerate(fr):
                a = max(0.0, 1 - max(0, j - (n - 18)) / 18)
                e.put((grade(f) * a).astype(np.uint8))
            continue
        s, cx = take(pool)
        fr = frames(fit_start(s, n / FPS), n / FPS, cx)
        for j, f in enumerate(fr):
            f = grade(f)
            if kind == "drop":
                f = punch(f, j / 7)
                if j < 2:
                    f = cv2.addWeighted(f, 0.6, np.full_like(f, 255), 0.4, 0)
            e.put(f)
    e.close()
    out = OUT / "PRIVATE-TEST_gta6_eoo_edit.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(REF / "edit_ref.wav"), "-map", "0:v",
                    "-map", "1:a", "-t", f"{e.n / FPS:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out)],
                   check=True)
    return out, len(segs)


# ------------------------------------------------------------------------------------------------ MEME
def meme():
    from clipper.editing.lyric_fx import caption_rgba
    start, dur = 897.6, 10.8                          # "...bullshit. A professional adapts. Are you a professional, Lucia?
    #                                                    Huh? Of course. Good. I need a professional."
    text = "When the boys ask if I'm good at GTA 6 after I died 30 times on the first mission"
    size, max_w = 66, 1000
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if cur and caption_rgba(t, size).shape[1] > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = t
    lines.append(cur)
    imgs = [cv2.cvtColor(caption_rgba(line, size), cv2.COLOR_RGBA2BGRA) for line in lines]
    pic_w, pic_h = 1080, 1080 * 1080 // 1440           # 4:3 -> 1080x810, under the caption
    top = 560
    silent = OUT / "PRIVATE-TEST_gta6_meme_professional_silent.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "15",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE)
    for f in frames(start, dur, 0.5, (pic_w, pic_h)):
        fr = np.zeros((H, W, 3), np.uint8)
        fr[top:top + pic_h] = grade(f)
        y = top - 40 - sum(i.shape[0] for i in imgs)
        for im in imgs:
            x = (W - im.shape[1]) // 2
            a = im[..., 3:4].astype(np.float32) / 255
            roi = fr[y:y + im.shape[0], x:x + im.shape[1]]
            fr[y:y + im.shape[0], x:x + im.shape[1]] = (roi * (1 - a) + im[..., :3] * a).astype(np.uint8)
            y += im.shape[0]
        enc.stdin.write(fr.tobytes())
    enc.stdin.close()
    enc.wait()
    out = OUT / "PRIVATE-TEST_gta6_meme_professional.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(EL),
                    "-map", "0:v", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-af", "loudnorm=I=-14:TP=-1.5", str(out)], check=True)
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {"EDIT": edit, "MEME": meme}
    for k in sys.argv[1:] or list(jobs):
        print(k, jobs[k]())
