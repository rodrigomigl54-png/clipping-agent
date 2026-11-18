"""2026-11-18: the owner's 3 reference edits, rebuilt (vertical 1080x1920, sharp sources only).

A  gavrik_boy "THE BEGINNING"   -> ChatGPT joke on the official GTA VI cover art, GTA V logo, GTA V montage (4:3 window)
B  zae_editzs "GTA 6 is gonna be lit" -> fast full-screen Launch-trailer cuts, dissolves, GTA VI logo pops, end logo
C  mqueen.edits "GTA 6 McQueen | GTA 5 McQueen" -> same idea with GTA footage: "Me when GTA 6 drops 😔 / GTA 5 dropped 🗿"

Usage: python scripts/manual_edits/2026-11-18_edits.py [A B C]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from clipper.editing import sequence as S  # noqa: E402

OUT = ROOT / "outputs/_PRIVATE_TEST/GTA6/2026-11-18"
OFF = ROOT / "assets/official/gta6"
REF = ROOT / "assets/hype_refs"
LOGO6, LOGO5 = str(OFF / "logo_gta6.png"), str(OFF / "logo_gta5.png")
COVER = str(OFF / "GTAVI_FOB_StandardEdition_Desktop.09clbpu8-nv8i.jpg")


def seq(bounds, items, **common):
    return [{"t0": a, "t1": b, **common, **it} for (a, b), it in zip(zip(bounds, bounds[1:]), items)]


def edit_a():
    cuts = [14.13, 15.37, 16.4, 17.5, 18.6, 19.73, 21.0, 22.1, 23.2, 24.3, 26.1, 26.6, 27.7, 28.57]
    montage = ["v:tr:6.33", "v:tr:38.07", "v:tr:39.4", "v:gp:70.67", "v:tr:67.07", "v:tr:68.2", "v:tr:69.47",
               "v:of:7.73", "v:of:11.2", "v:tr:45.8", "v:gp:251.13", "v:gp:58.27", "v:gp:24.07"]
    segs = [
        {"t0": 0.0, "t1": 2.4, "image": COVER, "cy": 0.42, "zoom": (1.0, 1.05)},
        {"t0": 2.4, "t1": 4.2, "image": COVER, "cy": 0.42, "zoom": (1.05, 1.08), "fx": {"sepia": 0.85, "grain": 9}, "trans": "flash"},
        {"t0": 4.2, "t1": 7.2, "image": COVER, "cy": 0.42, "zoom": (1.08, 1.1), "fx": {"sepia": 1.0, "pixel": (3, 16), "grain": 6},
         "trans": "flash"},
        {"t0": 7.2, "t1": 9.5, "image": COVER, "cy": 0.42, "zoom": (1.1, 1.12), "fx": {"gray": 1.0, "pixel": (16, 30), "fade_out": 0.5},
         "trans": "flash"},
        {"t0": 9.5, "t1": 14.13, "ref": "v:tr:70.67", "zoom": (1.0, 1.08), "trans": "dissolve"},
    ] + seq(cuts, [{"ref": r} for r in montage], trans="dissolve", zoom=(1.0, 1.05))
    caps = [
        {"t0": 0.1, "t1": 2.4, "text": "“ChatGPT, make GTA 6 a little older”", "y": 0.86},
        {"t0": 2.4, "t1": 4.2, "text": "“No bro, like WAY older”", "y": 0.86},
        {"t0": 4.2, "t1": 7.2, "text": "“Noo bro, I mean go back in time”", "y": 0.86},
        {"t0": 7.2, "t1": 9.5, "text": "“Noo bro, all the way back to the beginning”", "y": 0.86},
    ]
    spec = {"layout": "window", "duration": 28.57, "segments": segs, "captions": caps, "vivid": 1.08}
    return S.render(spec, OUT / "PRIVATE-TEST_gta6_beginning.mp4", str(REF / "gavrik_beginning.mp4"))


def edit_b():
    b = [0.0, 0.70, 1.33, 2.08, 2.92, 3.33, 3.95, 4.70, 5.55, 6.33, 6.90, 7.45, 8.15, 8.95, 9.90, 10.25, 10.95, 11.58,
         12.33, 13.22, 13.72]
    items = [{"image": str(OFF / "89834o94713o21.04n287k6o2lh9.jpg"), "cx": 0.55, "zoom": (1.0, 1.12)},
             {"ref": "6:la:54.53"}, {"ref": "6:la:20.53"}, {"ref": "6:la:34.4"}, {"ref": "6:la:27.2"}, {"ref": "6:la:37.33"},
             {"ref": "6:la:39.8"}, {"ref": "6:la:25.73"}, {"ref": "6:la:44.4"},
             {"image": str(OFF / "desktop.0iky3x6.hl8fo.jpg"), "cx": 0.42, "zoom": (1.05, 1.15)},
             {"ref": "6:la:48.27"}, {"ref": "6:la:46.33"}, {"ref": "6:la:52.33"}, {"ref": "6:la:56.4"}, {"ref": "6:la:59.27"},
             {"ref": "6:la:61.07"}, {"ref": "6:la:71.4"}, {"ref": "6:la:67.87"}, {"ref": "6:la:72.13"}, {"ref": "6:la:73.13"}]
    segs = seq(b, items, trans="dissolve", zoom=(1.0, 1.06))
    navy = OUT / "_navy.png"
    g = np.zeros((2160, 3840, 3), np.uint8)
    for y in range(2160):
        g[y] = (int(40 + 20 * y / 2160), int(18 + 8 * y / 2160), int(22 + 10 * y / 2160))
    cv2.imwrite(str(navy), g)
    segs.append({"t0": 13.72, "t1": 15.63, "image": str(navy), "zoom": (1.0, 1.0), "trans": "flash"})
    logos = [{"t0": 1.70, "t1": 2.05, "img": LOGO6, "scale": (0.30, 0.30), "pop": True},
             {"t0": 2.60, "t1": 2.88, "img": LOGO6, "scale": (0.34, 0.34), "pop": True},
             {"t0": 5.10, "t1": 5.45, "img": LOGO6, "scale": (0.30, 0.30), "pop": True},
             {"t0": 5.85, "t1": 6.30, "img": LOGO6, "scale": (0.42, 0.42), "pop": True},
             {"t0": 13.75, "t1": 15.63, "img": LOGO6, "scale": (0.55, 0.62), "pop": True}]
    spec = {"layout": "full", "duration": 15.63, "segments": segs, "logos": logos, "vivid": 1.15}
    return S.render(spec, OUT / "PRIVATE-TEST_gta6_lit.mp4", str(REF / "zae_lit.mp4"))


def edit_c():
    b = [0, 1.2, 1.7, 3.2, 4.03, 5.53, 6.67, 8.03, 8.73, 9.47, 10.2, 10.97, 11.53, 12.33, 12.83, 13.6, 14.23, 15.0, 15.57,
         16.77, 18.13, 18.87, 19.67, 21.37]
    six = ["6:la:57.87", "6:la:11.27", "6:t1:6.53", "6:la:50.73", "6:fe:12.4", "6:t2:97.67", "6:t1:8.47", "6:la:42.8", "6:t2:88.27"]
    five = ["v:of:11.2", "v:tr:68.2", "v:gp:201.33", "v:of:39.4", "v:gp:93.47", "v:tr:45.8", "v:gp:251.13", "v:of:7.73",
            "v:gp:87.53", "v:of:46.8", "v:gp:58.27", "v:tr:69.47", "v:gp:260.07", "v:gp:24.07"]
    segs = seq(b, [{"ref": r} for r in six + five], trans="cut", zoom=(1.0, 1.05))
    segs[9]["trans"] = "flash"
    logos = [{"t0": 0, "t1": 9.47, "img": LOGO6, "scale": (0.17, 0.17), "pos": (0.86, 0.86), "in_window": True},
             {"t0": 9.47, "t1": 21.37, "img": LOGO5, "scale": (0.19, 0.19), "pos": (0.86, 0.86), "in_window": True}]
    caps = [{"t0": 0, "t1": 9.47, "text": "Me when GTA 6 drops 😔", "y": 455, "abs": True, "size": 64},
            {"t0": 9.47, "t1": 21.37, "text": "Me when GTA 5 dropped 🗿", "y": 455, "abs": True, "size": 64}]
    spec = {"layout": "window", "duration": 21.37, "segments": segs, "logos": logos, "captions": caps, "vivid": 1.08,
            "window_dy": 40}
    return S.render(spec, OUT / "PRIVATE-TEST_gta6_me_then_now.mp4", str(REF / "mqueen_gta.mp4"))


if __name__ == "__main__":
    for k in sys.argv[1:] or ["A", "B", "C"]:
        print(k, {"A": edit_a, "B": edit_b, "C": edit_c}[k]())
