"""Thumbnails for LF2 from official Rockstar 4K screenshots: big '50' BEHIND the cut-out characters (modern style)."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

ROOT = Path(__file__).resolve().parents[3]
G = ROOT / "assets/official/gta6/launch_gallery/People"
OUT = ROOT / "outputs/longform/thumbs"
ANTON = str(ROOT / "assets/fonts/Anton-Regular.ttf")
W, H = 1280, 720


def cutout(img):
    from rembg import new_session, remove
    sess = new_session("u2net_human_seg")
    return remove(img, session=sess)


def make(src, name, big_x, line1, line2, shift=0):
    base = Image.open(G / src).convert("RGB").resize((W, H), Image.LANCZOS)
    base = ImageEnhance.Color(base).enhance(1.25)
    base = ImageEnhance.Contrast(base).enhance(1.1)
    fg = cutout(base)
    # darken the background a bit so the subjects pop
    bg = ImageEnhance.Brightness(base).enhance(0.62).filter(ImageFilter.GaussianBlur(1.2))
    canvas = bg.convert("RGBA")
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(ANTON, 560)
    d.text((big_x, -95), "50", font=f, fill=(255, 214, 0, 255), stroke_width=10, stroke_fill=(0, 0, 0, 255))
    # glow around the subjects
    a = np.array(fg)[..., 3]
    glow = Image.fromarray(a).filter(ImageFilter.GaussianBlur(14))
    glow_l = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    glow_l.putalpha(glow.point(lambda v: int(v * 0.55)))
    canvas = Image.alpha_composite(canvas, glow_l)
    canvas = Image.alpha_composite(canvas, fg)
    d = ImageDraw.Draw(canvas)
    f1 = ImageFont.truetype(ANTON, 92)
    f2 = ImageFont.truetype(ANTON, 70)
    for txt, fnt, y, col, boxcol in [(line1, f1, H - 205, (255, 255, 255), None), (line2, f2, H - 100, (255, 255, 255), (220, 30, 40))]:
        l, t, r, b = d.textbbox((0, 0), txt, font=fnt)
        x = 40 + shift
        if boxcol:
            d.rectangle((x - 12, y + t - 10, x + r + 12, y + b + 10), fill=boxcol)
        d.text((x, y), txt, font=fnt, fill=col, stroke_width=0 if boxcol else 6, stroke_fill=(0, 0, 0))
    OUT.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(OUT / name, quality=95)
    print(OUT / name)


if __name__ == "__main__":
    make("Jason and Lucia/Jason_and_Lucia_09.jpg", "LF2_A_moto.jpg", 40, "THINGS YOU NEED TO KNOW", "BEFORE YOU PLAY GTA 6")
    make("Lucia Caminos/Lucia_Caminos_10.jpg", "LF2_B_lucia.jpg", 60, "THINGS YOU NEED TO KNOW", "BEFORE YOU PLAY GTA 6")
    make("Jason and Lucia/Jason_and_Lucia_01.jpg", "LF2_C_duo.jpg", 700, "THINGS YOU NEED TO KNOW", "BEFORE YOU PLAY GTA 6")
