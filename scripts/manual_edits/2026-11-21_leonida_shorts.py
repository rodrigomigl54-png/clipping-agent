"""2026-11-21 Leonida Files Shorts — the owner's references rebuilt with OFFICIAL Rockstar footage only
(GTA VI: An Extended Look, parts never used before: the Raymond trap-house mission 3:00-5:30 and the penthouse 23:50-24:21).

EDIT1  @kareemkop style: square picture, deep red grade, glowing dialogue typed word by word over a slow intro,
       hard drop -> one cut per beat with punch zooms.            song for timing: SŌLIRA (Slowed) — MZØ
EDIT2  @ummi.fx style: landscape footage turned 90° to fill the vertical frame, blue/neon night, dialogue lines,
       cut per beat after the build.                                song for timing: MONTAGEM DIOSA (Slowed) — Nxmiya
MEME   @vicecitygators idea (Mandy + bathroom): caption on top, Jason knocking on a door and getting turned away.
FACTS  @bluethunder style: full vertical gameplay, narration, one big word at a time (voice: content/shorts/2026-11-21_facts).

Usage: python scripts/manual_edits/2026-11-21_leonida_shorts.py [EDIT1 EDIT2 MEME FACTS]
"""
import bisect
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

W, H, FPS = 1080, 1920, 30
EL = ROOT / "assets/footage/gta6_official/extended_look_1080.mp4"
REF = ROOT / "assets/hype_refs/1121b"
OUT = ROOT / "outputs/_PRIVATE_TEST/GTA6/2026-11-21"
FONTS = ROOT / "assets/fonts"
CUTS = [float(x) for x in (ROOT / "data/shot_cache/extended_look_cuts.txt").read_text().split()]
FACTS_VO = Path("/tmp/claude-0/facts_vo")


# ------------------------------------------------------------------------------------------------ helpers
def fit_start(t, dur):
    """Keep [t, t+dur] inside one shot of the Extended Look."""
    i = bisect.bisect_right(CUTS, t)
    nxt = CUTS[i] if i < len(CUTS) else 1e9
    prev = CUTS[i - 1] if i else 0.0
    if t + dur > nxt - 0.04:
        t = max(prev + 0.04, nxt - 0.04 - dur)
    return t


def frames(t, dur, cx=0.5, cw=1920, size=(1920, 1080)):
    """`dur` s of the Extended Look from t: crop cw x 1080 around cx, scale to size. BGR frames."""
    n = int(round(dur * FPS))
    x = int(min(max(cx * 1920 - cw / 2, 0), 1920 - cw))
    vf = f"crop={cw}:1080:{x}:0,scale={size[0]}:{size[1]}:flags=lanczos,fps={FPS}"
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(EL), "-t", f"{dur + 0.2:.3f}", "-vf", vf,
                        "-an", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True, check=True).stdout
    fl = size[0] * size[1] * 3
    fs = [np.frombuffer(p[i * fl:(i + 1) * fl], np.uint8).reshape(size[1], size[0], 3) for i in range(len(p) // fl)]
    while len(fs) < n:
        fs.append(fs[-1] if fs else np.zeros((size[1], size[0], 3), np.uint8))
    return fs[:n]


def lift(f, target=70):
    m = float(f.mean())
    if m < target:
        g = 0.6 + 0.4 * m / target
        f = (255 * (f / 255.0) ** g).astype(np.uint8)
    return f


def red_grade(f):
    """deep red look (kareemkop style): half tinted, contrasty, red-glowing edges"""
    f = lift(f, 85).astype(np.float32) / 255
    lum = f.mean(axis=2, keepdims=True)
    red = np.concatenate([lum * 0.25, lum * 0.30, np.clip(lum * 1.45, 0, 1)], axis=2)    # BGR
    o = np.clip((0.5 * f + 0.5 * red - 0.5) * 1.35 + 0.5, 0, 1) ** 1.05
    h, w = o.shape[:2]
    if (h, w) not in _VIG:
        yy, xx = np.mgrid[0:h, 0:w]
        d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
        _VIG[(h, w)] = np.clip((d - 0.75) / 0.6, 0, 1)[..., None].astype(np.float32)
    v = _VIG[(h, w)]
    o = o * (1 - 0.5 * v) + np.array([0.05, 0.05, 0.55], np.float32) * 0.5 * v
    return (np.clip(o, 0, 1) * 255).astype(np.uint8)


_VIG = {}


def blue_grade(f):
    f = lift(f, 95).astype(np.float32)
    f[..., 0] *= 1.12
    f[..., 2] *= 0.98
    f = np.clip((f - 128) * 1.15 + 126, 0, 255)
    hsv = cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.2, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def punch(f, k, amt=0.10):
    z = 1.0 + amt * (1 - min(1.0, k)) ** 2
    if z <= 1.001:
        return f
    h, w = f.shape[:2]
    g = cv2.resize(f, None, fx=z, fy=z, interpolation=cv2.INTER_LINEAR)
    y, x = (g.shape[0] - h) // 2, (g.shape[1] - w) // 2
    return g[y:y + h, x:x + w]


def push(f, k, amt=0.06):
    """slow push-in over a shot, k in 0..1"""
    z = 1.0 + amt * k
    h, w = f.shape[:2]
    g = cv2.resize(f, None, fx=z, fy=z, interpolation=cv2.INTER_LINEAR)
    y, x = (g.shape[0] - h) // 2, (g.shape[1] - w) // 2
    return g[y:y + h, x:x + w]


def flash(f, a):
    return cv2.addWeighted(f, 1 - a, np.full_like(f, 255), a, 0)


def text_rgba(text, font, size, fill=(255, 255, 255), spacing=0, stroke=0, glow=0, glow_col=None):
    fnt = ImageFont.truetype(str(FONTS / font), size)
    chars = list(text)
    ws = [fnt.getbbox(c)[2] - fnt.getbbox(c)[0] if c != " " else size * 0.28 for c in chars]
    tw = int(sum(ws) + spacing * (len(chars) - 1)) + 2 * stroke + 2 * glow + 8
    th = int(size * 1.35) + 2 * stroke + 2 * glow
    im = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = stroke + glow + 4
    for c, w in zip(chars, ws):
        d.text((x, glow + stroke), c, font=fnt, fill=fill + (255,), stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        x += w + spacing
    if glow:
        g = im.filter(ImageFilter.GaussianBlur(glow / 2))
        col = Image.new("RGBA", im.size, (glow_col or fill) + (0,))
        col.putalpha(g.getchannel("A").point(lambda v: min(255, int(v * 1.6))))
        base = Image.new("RGBA", im.size, (0, 0, 0, 0))
        base = Image.alpha_composite(base, col)
        im = Image.alpha_composite(base, im)
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGBA2BGRA)


def paste(fr, im, cx, cy, alpha=1.0):
    h, w = im.shape[:2]
    x, y = int(cx - w / 2), int(cy - h / 2)
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, fr.shape[1]), min(y + h, fr.shape[0])
    if x1 <= x0 or y1 <= y0:
        return fr
    sub = im[y0 - y:y1 - y, x0 - x:x1 - x]
    a = sub[..., 3:4].astype(np.float32) / 255 * alpha
    roi = fr[y0:y1, x0:x1].astype(np.float32)
    fr[y0:y1, x0:x1] = (roi * (1 - a) + sub[..., :3] * a).astype(np.uint8)
    return fr


class Enc:
    def __init__(self, path, size=(W, H)):
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s",
                                   f"{size[0]}x{size[1]}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
                                   "-crf", "15", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)],
                                  stdin=subprocess.PIPE)
        self.n = 0

    def put(self, f):
        self.p.stdin.write(np.ascontiguousarray(f).tobytes())
        self.n += 1

    def close(self):
        self.p.stdin.close()
        self.p.wait()


def el_audio(src, dur, sr=48000):
    """mono float32 game audio of the Extended Look"""
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{src:.3f}", "-t", f"{dur:.3f}", "-i", str(EL), "-vn", "-ac", "1",
                        "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(p, np.float32).copy()
    f = min(len(a), int(0.03 * sr))
    if f:
        a[:f] *= np.linspace(0, 1, f)
        a[-f:] *= np.linspace(1, 0, f)
    return a


def write_wav(path, x, sr=48000):
    import wave
    x = np.clip(x, -1, 1)
    st = np.stack([x, x], 1) if x.ndim == 1 else x
    w = wave.open(str(path), "wb")
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes((st * 32767).astype("<i2").tobytes())
    w.close()


def song(name, dur, sr=48000):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(REF / f"{name}.wav"), "-t", f"{dur:.3f}", "-ac", "1", "-ar",
                        str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(p, np.float32).copy()
    return np.pad(a, (0, max(0, int(dur * sr) - len(a))))[:int(dur * sr)]


def finish(silent, dialog, music_name, dur, tag, sr=48000):
    """silent.mp4 (video only) -> *_silent.mp4 with dialogue only (YouTube; add the song in the app)
    and *.mp4 with song + dialogue (preview / TikTok)."""
    d = dialog / max(1e-6, np.abs(dialog).max()) * 0.85
    m = song(music_name, dur, sr) * 0.75
    env = np.convolve((np.abs(d) > 0.02).astype(np.float32), np.ones(int(0.25 * sr)) / int(0.25 * sr), "same")
    duck = 1 - 0.65 * np.clip(env * 4, 0, 1)
    tmp = OUT / f"_{tag}"
    write_wav(f"{tmp}_dlg.wav", d, sr)
    write_wav(f"{tmp}_mix.wav", m * duck + d, sr)
    out_s, out = OUT / f"PRIVATE-TEST_gta6_{tag}_silent.mp4", OUT / f"PRIVATE-TEST_gta6_{tag}.mp4"
    for wav, o in [(f"{tmp}_dlg.wav", out_s), (f"{tmp}_mix.wav", out)]:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", wav, "-map", "0:v", "-map", "1:a",
                        "-t", f"{dur:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(o)], check=True)
        Path(wav).unlink()
    silent.unlink()
    return out, out_s


# ------------------------------------------------------------------------------------------------ EDIT 1 (red / Raymond)
def edit1():
    sr, DUR = 48000, 21.0
    SQ, SY = 1080, 420                                  # square picture position
    dialog = np.zeros(int(DUR * sr), np.float32)

    def put_audio(src, length, at):
        a = el_audio(src, length, sr)
        i = int(at * sr)
        dialog[i:i + len(a)] += a[:len(dialog) - i]

    put_audio(193.95, 197.60 - 193.95, 0.0)             # "Let me tell y'all something... at this point, I really don't give a—"
    put_audio(185.55, 187.75 - 185.55, 8.68)            # "Problem is, he only worried about himself."
    # dialogue captions: (start, end, line, [(word, appear_t)])
    caps = [
        (0.10, 2.20, [("LET", 0.15), ("ME", 0.65), ("TELL", 0.75), ("Y'ALL", 0.93), ("SOMETHING...", 1.17)]),
        (2.20, 3.81, [("AT", 2.25), ("THIS", 2.45), ("POINT,", 2.61), ("I", 2.83), ("REALLY", 2.95), ("DON'T", 3.15),
                      ("GIVE", 3.45), ("A—", 3.53)]),
        (8.75, 11.2, [("PROBLEM", 8.75), ("IS,", 9.15), ("HE", 9.35), ("ONLY", 9.5), ("WORRIED", 9.75), ("ABOUT", 10.05),
                      ("HIMSELF.", 10.3)]),
    ]
    intro = [(0.0, 3.81, 193.95, 0.64, "hold"), (3.81, 5.39, 229.0, 0.5, "push"), (5.39, 7.08, 223.0, 0.5, "push"),
             (7.08, 8.68, 219.3, 0.45, "push"), (8.68, 10.73, 185.55, 0.62, "hold"), (10.73, 11.96, 238.6, 0.5, "push")]
    stutter = (11.96, 12.98, [244.5, 248.0, 253.5])
    grid = [12.98, 13.40, 13.61, 14.0, 14.42, 14.81, 15.23, 15.63, 16.04, 16.46, 16.86, 17.28, 17.69, 18.09, 18.51,
            18.9, 19.3, 19.71, DUR]
    drop = [242.6, 246.6, 256.5, 253.8, 265.5, 262.5, 268.5, 271.0, 277.5, 280.8, 284.0, 288.5, 291.0, 300.6, 304.5,
            310.0, 315.0, 320.2]
    silent = OUT / "_e1.mp4"
    e = Enc(silent)
    sqf = lambda t, d, cx: frames(t, d, cx, 1080, (SQ, SQ))  # noqa: E731

    def emit(pic, t):
        fr = np.zeros((H, W, 3), np.uint8)
        fr[SY:SY + SQ] = pic
        for c0, c1, words in caps:
            if c0 <= t < c1:
                lines, cur = [], ""
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
                y = SY + SQ - 170 - 40 * (len(lines) - 1)
                for line in lines:
                    im = text_rgba(line, "Oswald[wght].ttf", 56, (255, 255, 255), spacing=5, glow=14,
                                   glow_col=(255, 60, 60))
                    paste(fr, im, W / 2, y)
                    y += 80
        e.put(fr)

    t = 0.0
    for a, b, src, cx, mode in intro:
        n = int(round(b * FPS)) - int(round(a * FPS))
        fs = sqf(src if mode == "hold" else fit_start(src, n / FPS), n / FPS, cx)
        for j, f in enumerate(fs):
            f = red_grade(f)
            f = push(f, j / max(1, n - 1), 0.05 if mode == "push" else 0.03)
            if a > 0 and j < 2:
                f = flash(f, 0.55 - 0.25 * j)
            emit(f, a + j / FPS)
    a, b, srcs = stutter
    n = int(round(b * FPS)) - int(round(a * FPS))
    fr3 = [sqf(fit_start(s, n / FPS), n / FPS, 0.5) for s in srcs]
    for j in range(n):
        f = red_grade(fr3[(j // 2) % 3][j])
        emit(flash(f, 0.3) if j % 4 == 0 else f, a + j / FPS)
    for k, src in enumerate(drop):
        a, b = grid[k], grid[k + 1]
        n = int(round(b * FPS)) - int(round(a * FPS))
        fs = sqf(fit_start(src, n / FPS), n / FPS, 0.5)
        for j, f in enumerate(fs):
            f = punch(red_grade(f), j / 6, 0.12)
            if j < 2 and k % 2 == 0:
                f = flash(f, 0.45 - 0.2 * j)
            if k == len(drop) - 1:
                f = (f * max(0.0, min(1.0, (n - j) / 24))).astype(np.uint8)
            emit(f, a + j / FPS)
    e.close()
    return finish(silent, dialog, "song_solira", e.n / FPS, "raymond_red_edit")


# ------------------------------------------------------------------------------------------------ EDIT 2 (blue / Lucia, rotated)
def edit2():
    sr, DUR = 48000, 20.6
    dialog = np.zeros(int(DUR * sr), np.float32)
    for src, end, at in [(1433.0, 1436.15, 0.40), (1436.40, 1438.10, 3.40)]:
        a = el_audio(src, end - src, sr)
        i = int(at * sr)
        dialog[i:i + len(a)] += a
    caps = [(0.45, 3.2, "HEY, HEY, HEY... GIVE ME THE PHONE."), (3.4, 4.4, "WHO AM I GONNA CALL?"),
            (4.4, 5.62, "I'M NOT STUPID.")]
    intro = [(0.0, 3.16, 1432.9, "push"), (3.16, 5.62, 1441.0, "push"), (5.62, 6.85, 1438.6, "punch"),
             (6.85, 8.08, 1441.9, "punch")]
    grid = [8.08, 8.68, 9.31, 9.94, 10.54, 11.15, 11.77, 12.40, 13.03, 13.63, 14.26, 14.86, 15.49, 16.09, 16.72, 17.35,
            17.97, 18.58, DUR]
    drop = [1443.2, 1450.7, 1434.2, 1455.2, 1441.9, 800.0, 1458.0, 1010.5, 1452.6, 905.2, 1435.3, 1020.0, 1456.8,
            1438.9, 1451.4, 1012.0, 1459.2, 1460.3]            # never 1446.4-1450.2 (body in the elevator)
    silent = OUT / "_e2.mp4"
    e = Enc(silent)

    def emit(f, t):
        for c0, c1, line in caps:
            if c0 <= t < c1:
                n_chars = int((t - c0) / 0.035) + 1          # typewriter
                im = text_rgba(line[:n_chars], "BebasNeue-Regular.ttf", 64, (255, 255, 255), spacing=4, stroke=2,
                               glow=10, glow_col=(90, 160, 255))
                paste(f, im, 960, 900)
        e.put(cv2.rotate(f, cv2.ROTATE_90_CLOCKWISE))

    for a, b, src, mode in intro:
        n = int(round(b * FPS)) - int(round(a * FPS))
        for j, f in enumerate(frames(src, n / FPS)):
            f = blue_grade(f)
            f = push(f, j / max(1, n - 1), 0.06) if mode == "push" else punch(f, j / 6, 0.10)
            if a > 0 and j < 2:
                f = flash(f, 0.4 - 0.2 * j)
            emit(f, a + j / FPS)
    for k, src in enumerate(drop):
        a, b = grid[k], grid[k + 1]
        n = int(round(b * FPS)) - int(round(a * FPS))
        for j, f in enumerate(frames(fit_start(src, n / FPS), n / FPS)):
            f = punch(blue_grade(f), j / 6, 0.12)
            if j < 2 and k % 2 == 0:
                f = flash(f, 0.4 - 0.2 * j)
            if k == len(drop) - 1:
                f = (f * max(0.0, min(1.0, (n - j) / 30))).astype(np.uint8)
            emit(f, a + j / FPS)
    e.close()
    return finish(silent, dialog, "song_diosa", e.n / FPS, "lucia_blue_edit")


# ------------------------------------------------------------------------------------------------ MEME (Mandy)
def meme():
    from clipper.editing.lyric_fx import caption_rgba
    parts = [(131.30, 135.40), (139.55, 144.60)]          # walk to the door + knock | "What you want?" ... "Nah. Never heard of it."
    text = "Me knocking on Mandy's bathroom door for the 5th time:"
    size, max_w = 70, 1000
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
    pw, ph, top = 1080, 810, 560
    silent = OUT / "_meme.mp4"
    e = Enc(silent)
    audio = []
    for a, b in parts:
        audio.append(el_audio(a, b - a))
        for f in frames(a, b - a, 0.55, 1440, (pw, ph)):
            fr = np.zeros((H, W, 3), np.uint8)
            fr[top:top + ph] = lift(f, 75)
            y = top - 40 - sum(i.shape[0] for i in imgs)
            for im in imgs:
                paste(fr, im, W / 2, y + im.shape[0] / 2)
                y += im.shape[0]
            e.put(fr)
    e.close()
    a = np.concatenate(audio)
    a = a / max(1e-6, np.abs(a).max()) * 0.9
    wav = OUT / "_meme.wav"
    write_wav(wav, a)
    out = OUT / "PRIVATE-TEST_gta6_meme_mandy_door.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5", "-shortest", str(out)],
                   check=True)
    silent.unlink()
    wav.unlink()
    return out


# ------------------------------------------------------------------------------------------------ FACTS
FACT_SHOTS = {                     # Extended Look seconds (9:16 crops of official gameplay), cx
    "hook": [(1130.0, 0.5), (740.0, 0.5)],
    "cash": [(690.5, 0.5), (700.0, 0.45), (706.0, 0.5), (540.5, 0.45)],
    "rifle": [(850.0, 0.4), (858.0, 0.45), (1080.5, 0.5)],
    "know": [(920.5, 0.5), (928.0, 0.5), (936.0, 0.5), (944.0, 0.5)],
    "stars": [(840.5, 0.55), (960.5, 0.5), (966.0, 0.5)],
    "guns": [(270.5, 0.5), (281.0, 0.45), (290.0, 0.5)],
    "radio": [(1020.5, 0.5), (1010.5, 0.5)],
    "animals": [(465.2, 0.32), (468.3, 0.42), (466.4, 0.62)],
    "outro": [(1210.0, 0.5), (750.0, 0.5)],
}
YELLOW = {"insane", "rob", "gone", "atm", "rifle", "notice", "cops", "camera", "six", "dogs", "helicopters", "arsenal",
          "trunk", "headphones", "radio", "170", "seventy", "first?"}


def facts():
    from clipper.editing.longform import draw_caption  # noqa: F401  (same caption family as the long-form)
    order = ["hook", "cash", "rifle", "know", "stars", "guns", "radio", "animals", "outro"]
    sr = 48000
    vo, words, t = [], [], 0.0
    for sid in order:
        meta = json.loads((FACTS_VO / f"{sid}.json").read_text())
        p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(FACTS_VO / f"{sid}.wav"), "-af", "atempo=1.12",
                            "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
        a = np.frombuffer(p, np.float32)
        gap = 0.12
        vo.append(a)
        vo.append(np.zeros(int(gap * sr), np.float32))
        for w in meta["words"]:
            words.append((t + w["s"] / 1.12, t + w["e"] / 1.12, w["w"]))
        seg_len = len(a) / sr + gap
        meta["_t"] = (t, t + seg_len)
        FACT_SHOTS[sid + "_t"] = meta["_t"]
        t += seg_len
    voice = np.concatenate(vo)
    dur = len(voice) / sr + 0.4
    silent = OUT / "_facts.mp4"
    e = Enc(silent)
    title = [text_rgba("THE MOST", "Anton-Regular.ttf", 120, (255, 214, 0), stroke=7),
             text_rgba("INSANE THINGS", "Anton-Regular.ttf", 120, (255, 60, 60), stroke=7),
             text_rgba("IN GTA 6", "Anton-Regular.ttf", 120, (255, 255, 255), stroke=7)]
    cache = {}
    for sid in order:
        a, b = FACT_SHOTS[sid + "_t"]
        if sid == order[-1]:
            b = dur
        shots = FACT_SHOTS[sid]
        n_total = int(round(b * FPS)) - int(round(a * FPS))
        per = n_total // len(shots)
        for k, (src, cx) in enumerate(shots):
            n = per if k < len(shots) - 1 else n_total - per * (len(shots) - 1)
            fs = frames(fit_start(src, n / FPS), n / FPS, cx, 608, (W, H))
            for j, f in enumerate(fs):
                tt = a + (k * per + j) / FPS
                f = cv2.convertScaleAbs(lift(f, 75), alpha=1.06, beta=-4)
                f = punch(f, j / 5, 0.06) if j < 6 else f
                if sid == "hook" and tt < 2.6:
                    y = 720
                    for im in title:
                        paste(f, im, W / 2, y)
                        y += 150
                else:
                    cur = [w for w in words if w[0] - 0.02 <= tt < w[1] + 0.12]
                    if cur:
                        word = {"LEONITA": "LEONIDA"}.get(cur[-1][2].upper().strip(",."), cur[-1][2].upper().strip(",."))
                        key = word.lower() in YELLOW or cur[-1][2].lower() in YELLOW
                        ck = (word, key)
                        if ck not in cache:
                            cache[ck] = text_rgba(word, "Anton-Regular.ttf", 118, (255, 214, 0) if key else (255, 255, 255),
                                                  stroke=8)
                        im = cache[ck]
                        pop = min(1.0, (tt - cur[-1][0]) / 0.08)
                        if pop < 1:
                            sc = 0.85 + 0.15 * pop
                            im = cv2.resize(im, None, fx=sc, fy=sc)
                        paste(f, im, W / 2, 760)
                e.put(f)
    e.close()
    voice = np.pad(voice, (0, int(dur * sr) - len(voice)))
    voice = voice / max(1e-6, np.abs(voice).max()) * 0.9
    wav = OUT / "_facts.wav"
    write_wav(wav, voice)
    out = OUT / "PRIVATE-TEST_gta6_facts_insane_things.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(wav), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-af", "loudnorm=I=-14:TP=-1.5", "-shortest", str(out)],
                   check=True)
    silent.unlink()
    wav.unlink()
    return out, round(dur, 1)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {"EDIT1": edit1, "EDIT2": edit2, "MEME": meme, "FACTS": facts}
    for k in sys.argv[1:] or list(jobs):
        print(k, jobs[k](), flush=True)
