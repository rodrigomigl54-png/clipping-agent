"""2026-11-21 (redo, owner's notes): recreate the owner's references for real.

NIKO1  @kareemkop "Niko Bellic" edit: square, red, Niko's real lines typed on screen word by word
       ("Just shut up, okay? I've been doing this since you were in your daddy's n*tsack" ...), drop -> cut per beat.
NIKO2  @ummi.fx "Niko Bellic" edit: footage turned 90°, Niko's lines typed, cut per beat after the build.
MEME2  @vicecitygators meme recreated: the same man trying to get through the door, cut out and put in front of
       Mandy's real bathroom door (GTA 6 'Pipework' house), same caption.

Footage (third-party gameplay uploads, imported with vidIQ — private test, owner decides):
  assets/footage/gta6_gameplay/niko_cutscenes.mp4   "GTA 6 - All Niko Bellic Cutscenes (4K)" youtube.com/watch?v=y7H4rhErWNI
  assets/footage/gta6_gameplay/mandy_bathroom.mp4   youtube.com/watch?v=OJXnO1ZN2qI (frame at 129.5 s, photo mode)
Usage: python scripts/manual_edits/2026-11-21b_niko_and_meme.py [NIKO1 NIKO2 MEME2]
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("ls", ROOT / "scripts/manual_edits/2026-11-21_leonida_shorts.py")
L = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(L)

W, H, FPS = 1080, 1920, 30
NIKO = ROOT / "assets/footage/gta6_gameplay/niko_cutscenes.mp4"
MANDY = ROOT / "assets/footage/gta6_gameplay/mandy_bathroom.mp4"
REF = ROOT / "assets/hype_refs/1121b"
OUT = ROOT / "outputs/_PRIVATE_TEST/GTA6/2026-11-21"
L.OUT = OUT
CLEAN_H = 940                        # rows 940+ hold the uploader's subtitles and logo


def nframes(t, dur, cx=0.5, w=CLEAN_H, h=CLEAN_H, size=(1080, 1080)):
    """frames of the Niko video, crop w x h from the top (no subtitles/logo) around cx"""
    n = int(round(dur * FPS))
    x = int(min(max(cx * 1920 - w / 2, 0), 1920 - w))
    vf = f"crop={w}:{h}:{x}:0,scale={size[0]}:{size[1]}:flags=lanczos,fps={FPS}"
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(NIKO), "-t", f"{dur + 0.2:.3f}", "-vf", vf,
                        "-an", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True, check=True).stdout
    fl = size[0] * size[1] * 3
    fs = [np.frombuffer(p[i * fl:(i + 1) * fl], np.uint8).reshape(size[1], size[0], 3) for i in range(len(p) // fl)]
    while len(fs) < n:
        fs.append(fs[-1] if fs else np.zeros((size[1], size[0], 3), np.uint8))
    return fs[:n]


def naudio(src, dur, sr=48000):
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{src:.3f}", "-t", f"{dur:.3f}", "-i", str(NIKO), "-vn", "-ac", "1",
                        "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(p, np.float32).copy()
    f = min(len(a), int(0.03 * sr))
    if f:
        a[:f] *= np.linspace(0, 1, f)
        a[-f:] *= np.linspace(1, 0, f)
    return a


def look(f, red=0.45):
    """the cutscene is already red-lit: lift, contrast, then part of the red grade"""
    g = L.red_grade(f)
    f = cv2.convertScaleAbs(L.lift(f, 80), alpha=1.12, beta=-8)
    return cv2.addWeighted(f, 1 - red, g, red, 0)


def captions_at(t, caps):
    """caps: [(start, end, colour, [(WORD, appear_t), ...])] -> list of (line text, colour)"""
    out = []
    for c0, c1, col, words in caps:
        if c0 <= t < c1:
            cur, lines = "", []
            for w, at in words:
                if t < at:
                    break
                if cur and len(cur) + len(w) > 24:
                    lines.append(cur)
                    cur = w
                else:
                    cur = (cur + " " + w).strip()
            if cur:
                lines.append(cur)
            out += [(ln, col) for ln in lines]
    return out


WHITE, YELLOW = (255, 255, 255), (255, 214, 60)


# ------------------------------------------------------------------------------------------------ NIKO 1 (kareemkop)
def niko1():
    sr, DUR, SY = 48000, 21.0, 420
    dialog = np.zeros(int(DUR * sr), np.float32)
    for src, end, at in [(161.90, 167.98, 0.0), (147.30, 151.30, 8.10), (236.75, 238.70, 19.03)]:
        a = naudio(src, end - src)
        i = int(at * sr)
        dialog[i:i + len(a)] += a[:len(dialog) - i]
    caps = [
        (0.05, 1.25, WHITE, [("OKAY,", 0.06), ("LET'S", 0.78), ("JUST", 0.96), ("TAKE", 1.0), ("IT...", 1.05)]),
        (1.25, 3.25, WHITE, [("JUST", 1.25), ("SHUT", 1.32), ("UP,", 1.6), ("OKAY?", 1.96)]),
        (3.28, 6.40, YELLOW, [("I'VE", 3.30), ("BEEN", 3.70), ("DOING", 3.82), ("THIS", 4.04), ("SINCE", 4.24),
                              ("YOU", 4.46), ("WERE", 4.66), ("IN", 4.76), ("YOUR", 4.90), ("DADDY'S", 5.02),
                              ("N*TSACK.", 5.56)]),
        (8.15, 12.0, WHITE, [("I", 8.2), ("HAVEN'T", 8.72), ("KILLED", 9.24), ("ANYBODY", 9.46), ("SINCE", 10.28),
                             ("2012.", 10.75)]),
        (19.05, DUR, YELLOW, [("SEE", 19.1), ("YOU", 19.78), ("AROUND,", 19.88), ("TOUGH", 20.5), ("GUY.", 20.62)]),
    ]
    intro = [(0.0, 6.40, 161.90, 0.55, "sync"), (6.40, 8.0, 169.6, 0.5, "push"), (8.0, 12.0, 147.20, 0.5, "sync")]
    stutter = (12.0, 12.98, [208.5, 212.5, 233.0])
    grid = [12.98, 13.40, 13.61, 14.0, 14.42, 14.81, 15.23, 15.63, 16.04, 16.46, 16.86, 17.28, 17.69, 18.09, 18.51, 18.9]
    drop = [80.5, 104.2, 120.2, 163.3, 172.5, 176.5, 196.5, 200.5, 209.0, 213.5, 228.5, 380.5, 384.0, 388.5, 401.0]
    final = (18.9, DUR, 237.0)
    silent = OUT / "_n1.mp4"
    e = L.Enc(silent)
    cache = {}

    def emit(pic, t):
        fr = np.zeros((H, W, 3), np.uint8)
        fr[SY:SY + 1080] = pic
        lines = captions_at(t, caps)
        y = SY + 1080 - 170 - 40 * (len(lines) - 1)
        for ln, col in lines:
            if (ln, col) not in cache:
                cache[(ln, col)] = L.text_rgba(ln, "Oswald[wght].ttf", 56, col, spacing=5, glow=14,
                                               glow_col=(255, 60, 60) if col == WHITE else (255, 170, 0))
            L.paste(fr, cache[(ln, col)], W / 2, y)
            y += 80
        e.put(fr)

    opener = nframes(163.3, 0.6, 0.55)
    for a, b, src, cx, mode in intro:
        n = int(round(b * FPS)) - int(round(a * FPS))
        for j, f in enumerate(nframes(src, n / FPS, cx)):
            if a == 0.0 and j < len(opener):
                f = opener[j]
            f = L.push(look(f), j / max(1, n - 1), 0.05 if mode == "push" else 0.025)
            if a > 0 and j < 2:
                f = L.flash(f, 0.5 - 0.25 * j)
            emit(f, a + j / FPS)
    a, b, srcs = stutter
    n = int(round(b * FPS)) - int(round(a * FPS))
    fr3 = [nframes(s, n / FPS) for s in srcs]
    for j in range(n):
        f = look(fr3[(j // 2) % 3][j])
        emit(L.flash(f, 0.15) if j % 4 == 0 else f, a + j / FPS)
    for k, src in enumerate(drop):
        a, b = grid[k], grid[k + 1]
        n = int(round(b * FPS)) - int(round(a * FPS))
        for j, f in enumerate(nframes(src, n / FPS)):
            f = L.punch(look(f, 0.55), j / 6, 0.12)
            if j < 2 and k % 2 == 0:
                f = L.flash(f, 0.45 - 0.2 * j)
            emit(f, a + j / FPS)
    a, b, src = final
    n = int(round(b * FPS)) - int(round(a * FPS))
    for j, f in enumerate(nframes(src, n / FPS)):
        f = L.push(look(f), j / n, 0.04)
        if j < 2:
            f = L.flash(f, 0.5 - 0.25 * j)
        f = (f * max(0.0, min(1.0, (n - j) / 15))).astype(np.uint8)
        emit(f, a + j / FPS)
    e.close()
    return L.finish(silent, dialog, "song_solira", e.n / FPS, "niko_red_edit")


# ------------------------------------------------------------------------------------------------ NIKO 2 (ummi.fx, rotated)
def niko2():
    sr, DUR = 48000, 20.6
    dialog = np.zeros(int(DUR * sr), np.float32)
    for src, end, at in [(86.30, 88.10, 3.45), (105.50, 108.15, 5.70), (109.75, 111.35, 8.20), (400.40, 402.60, 18.80)]:
        a = naudio(src, end - src)
        i = int(at * sr)
        dialog[i:i + len(a)] += a[:len(dialog) - i]
    caps = [(3.5, 5.6, "IT'S BEEN A LONG TIME."), (5.8, 8.1, "ONLY ONE REASON I WOULD COME HERE."),
            (8.25, 10.0, "YOU REALLY F*CKED UP."), (18.85, DUR, "WELL... I GUESS IT'S TIME TO GO HOME.")]
    intro = [(0.0, 3.16, 74.2, "push"), (3.16, 5.62, 80.8, "push"), (5.62, 8.08, 105.4, "sync")]
    grid = [8.08, 8.68, 9.31, 9.94, 10.54, 11.15, 11.77, 12.40, 13.03, 13.63, 14.26, 14.86, 15.49, 16.09, 16.72, 17.35,
            17.97, 18.58]
    drop = [109.6, 124.3, 146.8, 163.3, 167.5, 209.5, 212.0, 214.5, 104.5, 237.6, 380.5, 384.5, 388.0, 392.5, 396.0,
            120.5, 172.5]
    final = (18.58, DUR, 400.15)
    silent = OUT / "_n2.mp4"
    e = L.Enc(silent)
    size = (1920, 1080)

    def grab(src, n):
        return nframes(src, n / FPS, 0.5, int(CLEAN_H * 16 / 9), CLEAN_H, size)

    def emit(f, t):
        for c0, c1, line in caps:
            if c0 <= t < c1:
                k = int((t - c0) / 0.035) + 1
                im = L.text_rgba(line[:k], "BebasNeue-Regular.ttf", 68, WHITE, spacing=4, stroke=2, glow=10,
                                 glow_col=(255, 70, 70))
                L.paste(f, im, 960, 905)
        e.put(cv2.rotate(f, cv2.ROTATE_90_CLOCKWISE))

    for a, b, src, mode in intro:
        n = int(round(b * FPS)) - int(round(a * FPS))
        for j, f in enumerate(grab(src, n)):
            f = L.push(look(f, 0.3), j / max(1, n - 1), 0.06 if mode == "push" else 0.03)
            if a > 0 and j < 2:
                f = L.flash(f, 0.4 - 0.2 * j)
            emit(f, a + j / FPS)
    for k, src in enumerate(drop):
        a, b = grid[k], grid[k + 1]
        n = int(round(b * FPS)) - int(round(a * FPS))
        for j, f in enumerate(grab(src, n)):
            f = L.punch(look(f, 0.35), j / 6, 0.12)
            if j < 2 and k % 2 == 0:
                f = L.flash(f, 0.4 - 0.2 * j)
            emit(f, a + j / FPS)
    a, b, src = final
    n = int(round(b * FPS)) - int(round(a * FPS))
    for j, f in enumerate(grab(src, n)):
        f = L.push(look(f, 0.25), j / n, 0.04)
        f = (f * max(0.0, min(1.0, (n - j) / 15))).astype(np.uint8)
        emit(f, a + j / FPS)
    e.close()
    return L.finish(silent, dialog, "song_diosa", e.n / FPS, "niko_sideways_edit")


# ------------------------------------------------------------------------------------------------ MEME 2 (recreated)
def door_background():
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", "129.5", "-i", str(MANDY), "-frames:v", "1", "-f", "rawvideo",
                        "-pix_fmt", "bgr24", "-"], capture_output=True, check=True).stdout
    f = np.frombuffer(p, np.uint8).reshape(1080, 1920, 3).copy()
    m = np.zeros(f.shape[:2], np.uint8)                       # photo-mode focus brackets -> inpaint
    for x0, y0 in [(828, 465), (1058, 465), (828, 580), (1058, 580)]:
        m[y0 - 4:y0 + 34, x0 - 4:x0 + 34] = 255
    f = cv2.inpaint(f, m, 5, cv2.INPAINT_TELEA)
    x = 715 - 304
    crop = f[:, x:x + 608]
    return cv2.resize(crop, (W, H), interpolation=cv2.INTER_LANCZOS4)


def meme2():
    from PIL import Image
    from rembg import new_session, remove
    from clipper.editing.lyric_fx import caption_rgba
    sess = new_session("u2net_human_seg")
    bg = door_background()
    bg_mean = bg.reshape(-1, 3).mean(0)
    cap = cv2.VideoCapture(str(REF / "meme.mp4"))
    shift = 330                                              # feet to the bottom edge (the reference hid them behind a bed)
    lines = ["POV :", "Me trying to get inside the", "bathroom with Mandy"]
    imgs = [cv2.cvtColor(caption_rgba(t, 64), cv2.COLOR_RGBA2BGRA) for t in lines]
    silent = OUT / "_m2.mp4"
    e = L.Enc(silent)
    prev = None
    while True:
        ok, f = cap.read()
        if not ok:
            break
        m = np.array(remove(Image.fromarray(f[..., ::-1]), session=sess, only_mask=True)).astype(np.uint8)
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        poster = (hsv[..., 1] > 100) & (hsv[..., 0] > 135) & (hsv[..., 0] < 172) & (hsv[..., 2] > 90)  # bright pink/purple poster
        m[poster] = 0
        r = hsv[330:520, 0:230]                                       # the small framed poster on the left wall
        m[330:520, 0:230][(r[..., 0] > 95) & (r[..., 1] > 50) & (r[..., 2] > 35)] = 0
        n, lab, st, _ = cv2.connectedComponentsWithStats((m > 127).astype(np.uint8))
        if n > 1:
            keep = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
            m = np.where(lab == keep, m, 0).astype(np.uint8)
        m = np.where(m > 90, 255, 0).astype(np.uint8)          # solid matte (the bald head came out half see-through)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        m = cv2.GaussianBlur(m, (5, 5), 0)
        if prev is not None:                                 # temporal smoothing of the matte
            m = cv2.addWeighted(m, 0.7, prev, 0.3, 0)
        prev = m
        big = cv2.resize(f, (W, H), interpolation=cv2.INTER_LANCZOS4).astype(np.float32)
        a = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32)[..., None] / 255
        big = big * (0.85 + 0.15 * bg_mean / max(1.0, big.reshape(-1, 3).mean()))   # light match to the hallway
        man = np.zeros_like(big)
        am = np.zeros_like(a)
        man[shift:] = big[:H - shift]
        am[shift:] = a[:H - shift]
        fr = (bg.astype(np.float32) * (1 - am) + man * am).clip(0, 255).astype(np.uint8)
        y = 430
        for im in imgs:
            L.paste(fr, im, W / 2, y)
            y += im.shape[0] - 6
        e.put(fr)
    e.close()
    out = OUT / "PRIVATE-TEST_gta6_meme_mandy_bathroom_v2.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(REF / "meme.mp4"), "-map", "0:v",
                    "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True)
    silent.unlink()
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {"NIKO1": niko1, "NIKO2": niko2, "MEME2": meme2}
    for k in sys.argv[1:] or list(jobs):
        print(k, jobs[k](), flush=True)
