"""Groundwork test: one level ("Your Life as Every Level of a Dropshipper" — Level 1: The Dream) in the channel style.

Channel style (learned from "Your Life as a Gambling Addict" and "Every Rank in the Secret Service"):
  * no intro — the video opens on "Level one, the ..."; each level = black title card ~2 s, white bold condensed
    "LEVEL ONE:\nTHE DREAM", then narration over still illustrations
  * illustrations: one recurring character (big round plain white head, dot eyes, flat mouth, grey hoodie) in
    detailed, muted, cinematic painted interiors; a new image every ~3–5 s, hard cuts, very slow push-in
  * narration: second person, present tense, concrete numbers and small details, ~170 wpm, 60–200 s per level
Images: shotlist.json has a ready prompt for every shot. Until images are generated, PLACEHOLDER frames from our
own old video (Gambling Addict) are used, labelled in the corner.
Usage: python content/groundwork/dropshipper_test/make_level.py
"""
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REF = ROOT / "assets/groundwork/refs/gambling.mp4"
IMG_DIR = HERE / "images"                      # put generated shot_XX.png here to replace placeholders
OUT = ROOT / "outputs/_PRIVATE_TEST/GROUNDWORK/level1_dropshipper_test.mp4"
W, H, FPS = 1920, 1080, 30
FONT = str(ROOT / "assets/fonts/Oswald[wght].ttf")

STYLE = ("digital painting, cinematic, muted colors, soft realistic lighting, detailed realistic environment, "
         "a simple cartoon character with a large round plain white head, two small black dot eyes, a small flat "
         "line mouth, no hair, no nose, wearing a grey hoodie; ")
# (start s, end s, scene prompt, placeholder time in REF)
SHOTS = [
    (0.0, 1.93, "TITLE", None),
    (1.93, 4.5, "the character lying in bed at night scrolling a phone, face lit by the screen, dark bedroom", 72),
    (4.5, 8.5, "close-up of a phone screen showing a video of a young man leaning on a rented Lamborghini", 136),
    (8.5, 13.45, "close-up of the character's face, eyes wide, blue phone glow, late at night", 112),
    (13.45, 16.1, "the character sitting up in bed watching the phone again, alarm clock shows 11:58 PM", 168),
    (16.1, 20.8, "a notebook on a desk with handwritten words 'dropshipping', 'winning product', 'scale'", 240),
    (20.8, 24.0, "a phone on a desk showing a screenshot of an online store sales dashboard with big green numbers", 232),
    (24.0, 27.13, "the character's face, determined, small confident smile", 208),
    (27.13, 31.5, "the character at a desk at night signing up on a laptop, store builder website on screen", 192),
    (31.5, 36.52, "a wall calendar with a date circled in red 14 days ahead, 'trial ends'", 248),
    (36.52, 40.5, "weekend daylight, the character at a laptop surrounded by snack wrappers and energy drinks", 200),
    (40.5, 43.91, "a cheap galaxy star projector glowing purple on the desk, shipping box beside it", 280),
    (43.91, 47.5, "a notebook full of math: $6.80 cost, $34.99 price, profit circled several times", 240),
    (47.5, 50.3, "the character smiling at the laptop screen, warm lamp light", 904),
    (50.3, 53.5, "a laptop showing a simple new logo for a store called 'NOVA GLOW'", 280),
    (53.5, 56.96, "the character talking proudly to a roommate (same character style) in a small apartment kitchen", 32),
    (56.96, 62.88, "a university lecture hall, the character sitting among students, phone buzzing on the desk", 752),
    (62.88, 64.15, "phone notification close-up: 'New order: $34.99'", 960),
    (64.15, 68.15, "a woman (same character style) on a porch in Ohio holding a phone, suburban house", 624),
    (68.15, 74.43, "the character in the lecture hall, dazed, smiling at the phone, professor blurred in background", 488),
    (74.43, 78.5, "an ad dashboard on a laptop showing 'cost per purchase: $41.00' in red", 416),
    (78.5, 82.31, "a parcel tracking page: 'estimated delivery: 19 days', small cardboard box", 528),
    (82.31, 85.6, "the character walking out of the university at golden hour, chin up, feeling like a CEO", 992),
]


def title_card(text):
    im = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, 120)
    try:
        f.set_variation_by_axes([700])
    except Exception:
        pass
    lines = text.split("\n")
    hs = [f.getbbox(l)[3] - f.getbbox(l)[1] for l in lines]
    y = H / 2 - (sum(hs) + 20 * (len(lines) - 1)) / 2
    for l, hh in zip(lines, hs):
        w = f.getlength(l)
        d.text(((W - w) / 2, y - f.getbbox(l)[1]), l, font=f, fill=(255, 255, 255))
        y += hh + 20
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


def placeholder(t):
    b = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(REF), "-frames:v", "1", "-f", "rawvideo",
                        "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    f = np.frombuffer(b, np.uint8).reshape(360, 640, 3)
    f = cv2.resize(f, (W, H), interpolation=cv2.INTER_CUBIC)
    cv2.putText(f, "PLACEHOLDER (old image)", (24, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (200, 200, 200), 2)
    return f


def main():
    script = json.loads((HERE / "script.json").read_text())
    shotlist = [dict(shot=i, start=s, end=e, prompt=(STYLE + p) if p != "TITLE" else "TITLE CARD") for i, (s, e, p, _)
                in enumerate(SHOTS)]
    (HERE / "shotlist.json").write_text(json.dumps(shotlist, indent=1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_name("_v.mp4")
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                            "-pix_fmt", "yuv420p", str(tmp)], stdin=subprocess.PIPE)
    for i, (s, e, p, ref_t) in enumerate(SHOTS):
        n = int(round((e - s) * FPS))
        if p == "TITLE":
            img = title_card(script["level"])
            for _ in range(n):
                enc.stdin.write(img.tobytes())
            continue
        own = IMG_DIR / f"shot_{i:02d}.png"
        base = cv2.resize(cv2.imread(str(own)), (W, H)) if own.exists() else placeholder(ref_t)
        for j in range(n):
            z = 1.0 + 0.035 * j / max(1, n)                  # slow push-in
            m = cv2.resize(base, None, fx=z, fy=z)
            oy, ox = (m.shape[0] - H) // 2, (m.shape[1] - W) // 2
            enc.stdin.write(m[oy:oy + H, ox:ox + W].tobytes())
    enc.stdin.close()
    enc.wait()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-i", str(HERE / "vo.wav"), "-map", "0:v",
                    "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-af",
                    "loudnorm=I=-16:TP=-1.5", "-shortest", str(OUT)], check=True)
    tmp.unlink()
    print(OUT)


if __name__ == "__main__":
    main()
