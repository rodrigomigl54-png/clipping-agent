"""THE BEGINNING v2: exact layout of @gavrik_boy's edit: a 2:1 picture strip in the middle of a black 9:16 frame,
caption in the middle of the picture, crossfades on the same timing as the reference:
  0.00 original J&L convertible frame        "ChatGPT make them wear white"         (caption 0.0-1.5)
  1.50 crossfade -> white clothes             "No bro, like all of it white"         (2.0-4.0)
  4.00 crossfade -> white statues             "No bro, I mean take everything back"  (4.5-7.5)
  7.25 slow crossfade -> Los Santos sunset    "Noo bro, like all back to the beginning" (7.75-9.6)
 10.00-12.00 GTA V logo grows (ease-out), holds to 14.13
 14.13 GTA V montage on the reference cuts.
Images: /tmp/claude-0/gen (made by steps.py: rembg masks + recolour, all local).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from clipper.editing import longform as LF  # noqa: E402
from clipper.editing.lyric_fx import mux  # noqa: E402
from clipper.editing.longform import text_rgba, over  # noqa: E402

GEN = Path("/tmp/claude-0/gen")
OUT = ROOT / "outputs/_PRIVATE_TEST/GTA6/2026-11-18"
W, H, FPS = 1080, 1920, 30
SW, SH = 1080, 540
SY = (H - SH) // 2


def strip_of(img):
    h, w = img.shape[:2]
    ch = int(w / 2)
    if ch > h:
        cw = h * 2
        x = (w - cw) // 2
        img = img[:, x:x + cw]
    else:
        y = (h - ch) // 2
        img = img[y:y + ch]
    return cv2.resize(img, (SW, SH), interpolation=cv2.INTER_AREA)


def load(name):
    im = cv2.imread(str(GEN / name))
    rows = np.where(im.mean((1, 2)) > 8)[0]
    return strip_of(im[rows.min():rows.max() + 1])


def ls_frame():
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", "70.80", "-i", str(ROOT / "assets/footage/gta5/trailer.mp4"),
                        "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, check=True).stdout
    im = cv2.imdecode(np.frombuffer(p, np.uint8), cv2.IMREAD_COLOR)
    return strip_of(im[72:648])


def caption(text):
    return text_rgba(text, "inter", 42, (255, 255, 255), stroke=3, shadow=True)


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def main():
    base, s1, s2, ls = load("base.png"), load("white_clothes.png"), load("white_all.png"), ls_frame()
    logo = cv2.imread(str(ROOT / "assets/official/gta6/logo_gta5.png"), cv2.IMREAD_UNCHANGED)
    keys = [(0.0, base), (1.5, s1), (4.0, s2), (7.25, ls)]
    fades = {1.5: 0.25, 4.0: 0.25, 7.25: 0.5}
    caps = [(0.0, 1.5, "ChatGPT make them wear white"), (2.0, 4.0, "No bro, like all of it white"),
            (4.5, 7.5, "No bro, I mean take everything back"), (7.75, 9.6, "Noo bro, like all back to the beginning")]
    cuts = [14.13, 15.37, 16.4, 17.5, 18.6, 19.73, 21.0, 22.1, 23.2, 24.3, 26.1, 26.6, 27.7, 28.57]
    montage = ["v:tr:6.33", "v:tr:38.07", "v:tr:39.4", "v:gp:70.67", "v:tr:67.07", "v:tr:68.2", "v:tr:69.47",
               "v:of:7.73", "v:of:11.2", "v:tr:45.8", "v:gp:251.13", "v:gp:58.27", "v:gp:24.07"]
    silent = OUT / "PRIVATE-TEST_gta6_beginning_silent.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p",
                            "-movflags", "+faststart", str(silent)], stdin=subprocess.PIPE)

    def put(strip):
        f = np.zeros((H, W, 3), np.uint8)
        f[SY:SY + SH] = strip
        enc.stdin.write(f.tobytes())

    # intro 0 - 14.13
    for i in range(int(round(14.13 * FPS))):
        t = i / FPS
        k = max(j for j, (t0, _) in enumerate(keys) if t >= t0)
        img = keys[k][1].astype(np.float32)
        nxt = k + 1 if k + 1 < len(keys) else None
        if nxt is not None:
            t1 = keys[nxt][0]
            fd = fades[t1]
            if t >= t1 - fd / 2 and False:
                pass
        # crossfade window starts at the key time
        t0 = keys[k][0]
        if k > 0 and t < t0 + fades[t0]:
            a = (t - t0) / fades[t0]
            img = keys[k - 1][1].astype(np.float32) * (1 - a) + img * a
        z = 1.0 + 0.03 * (t / 14.13)                       # very slow push-in, like the reference
        st = cv2.resize(img.astype(np.uint8), None, fx=z, fy=z, interpolation=cv2.INTER_CUBIC)
        y0, x0 = (st.shape[0] - SH) // 2, (st.shape[1] - SW) // 2
        st = np.ascontiguousarray(st[y0:y0 + SH, x0:x0 + SW])
        if t >= 10.0:
            g = ease((t - 10.0) / 2.0)
            wpx = int(SW * (0.22 + 0.48 * g))
            lg = cv2.resize(logo, (wpx, int(logo.shape[0] * wpx / logo.shape[1])), interpolation=cv2.INTER_AREA)
            over(st, lg, SW / 2, SH / 2, min(1.0, (t - 10.0) / 0.2))
        for c0, c1, txt in caps:
            if c0 <= t < c1:
                over(st, caption(txt), SW / 2, SH * 0.5, 1.0)
        put(st)
    # montage
    for (a, b), ref in zip(zip(cuts, cuts[1:]), montage):
        n = int(round(b * FPS)) - int(round(a * FPS))
        info = LF.shot_info(ref)
        for j, fr in enumerate(LF.read_frames(info, n / FPS, SW, SH)):
            if j >= n:
                break
            if j < 4:                                    # short dissolve from the previous shot
                fr = fr
            put(np.ascontiguousarray(fr))
    enc.stdin.close()
    enc.wait()
    out = OUT / "PRIVATE-TEST_gta6_beginning.mp4"
    mux(silent, str(ROOT / "assets/hype_refs/gavrik_beginning.mp4"), out)
    print(out)


if __name__ == "__main__":
    main()
