"""2026-11-17: the owner's 3 reference edits, rebuilt with our footage (GTA 6 in 2 days).

1. og_kissed     @gta6og "This doesn't feel real"  - lyric words, key words huge red, top caption joke
2. og_heaven     @gta6og "This must be heaven"     - words filled with footage on black, growing window, white lyrics
3. kairoxx_lucia @kairoxxofficial "2 DAYS LEFT"    - full-bleed vertical crops, warm glow grade, 60 fps, typed subtitle

Usage: python scripts/manual_edits/2026-11-17_lyric_edits.py [kissed|heaven|lucia ...]
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from clipper.editing import lyric_fx as L  # noqa: E402
from clipper.editing import template_edit as T  # noqa: E402
from clipper.editing.hype_editor import Shot  # noqa: E402

OUT = ROOT / "outputs/_PRIVATE_TEST/GTA6/2026-11-17"
SRC = [ROOT / "assets/footage/gta6" / f for f in ("trailer1.mp4", "trailer2.mp4", "features.mp4", "preload.mp4")] + \
      [ROOT / "assets/footage/gta6_launch/launch.mp4"]
USED = ROOT / "memory/hype_used.json"


def shots_all() -> list[Shot]:
    out = []
    for s in SRC:
        cp = ROOT / "data/shot_cache" / f"{s.parent.name}__{s.name}.shots.json"
        sh = [Shot(**d) for d in json.loads(cp.read_text())]
        T.tag_shots(str(s), sh, ROOT / "config/footage_tags" / s.parent.name)
        out += sh
    return out


def recent() -> set:
    u = json.loads(USED.read_text()) if USED.exists() else {}
    cut = (date.today() - timedelta(days=3)).isoformat()
    return {(x[0], x[1]) for d, xs in u.items() if d >= cut for x in xs}


def remember(used: list) -> None:
    u = json.loads(USED.read_text()) if USED.exists() else {}
    u.setdefault(date.today().isoformat(), []).extend(used)
    USED.write_text(json.dumps(u))


def W(t0, t1, text, style="white", **k):
    return {"type": "word", "t0": t0, "t1": t1, "text": text, "style": style, **k}


def M(t0, t1, text, **k):
    return {"type": "mask", "t0": t0, "t1": t1, "text": text, **k}


KISSED = [W(0.0, 0.375, "I'M"), W(0.375, 0.875, "CU-"), W(0.875, 1.875, "CURI-"), W(1.875, 2.25, "CURIOUS", "red"),
          W(2.25, 2.5, "FOR"), W(2.5, 3.125, "YOU"), W(3.75, 4.5, "CAUGHT", "red"), W(4.625, 5.25, "MY"),
          W(5.5, 6.75, "ATTENTION", "red"), W(7.125, 7.5, "I"), W(7.625, 8.0, "KISSED", "red"), W(8.0, 8.5, "A"),
          W(8.5, 8.875, "GIRL"), W(8.875, 9.125, "AND"), W(9.125, 9.375, "I"), W(9.375, 9.875, "LIKED", "red"),
          W(10.0, 10.5, "IT"), W(10.625, 10.875, "THE"), W(10.875, 11.25, "TASTE"), W(11.25, 11.625, "OF"),
          W(11.625, 11.875, "HER"), W(11.875, 12.125, "CHERRY"), W(12.125, 12.625, "CHERRY", "red"),
          W(12.625, 13.0, "CHAP"), W(13.0, 13.85, "STICK"), M(13.9, 14.4, "2 DAYS", fade=0.3)]

HEAVEN = [M(0.125, 0.25, "I"), M(0.25, 0.375, "THINK"), M(0.375, 0.625, "I"), M(0.625, 0.875, "DIED"),
          M(0.875, 1.0, "IN"), M(1.0, 1.25, "AN"), M(1.25, 1.875, "ACCIDENT"), M(1.875, 2.0, "CUZ"),
          M(2.0, 2.25, "THIS"), M(2.25, 2.5, "MUST"), M(2.5, 2.75, "BE"), M(2.75, 4.0, "HEAVEN", fade=0.8),
          {"type": "window", "t0": 0.0, "t1": 0.125, "from": 0.0, "to": 0.0},
          {"type": "window", "t0": 4.0, "t1": 6.15, "from": 0.0, "to": 0.42},
          W(7.0, 7.333, "GOTTA"), W(7.375, 8.2, "TESTIFY"), W(8.375, 8.5, "COME"), W(8.5, 8.75, "UP"), W(8.75, 8.875, "IN"),
          W(8.875, 9.0, "THE"), W(9.0, 9.375, "SPOT"), W(9.375, 9.625, "LOOKING"), W(9.625, 10.0, "EXTRA"),
          W(10.0, 11.2, "FLY"), W(11.5, 11.75, "FOR"), W(11.75, 11.875, "THE"), W(11.875, 12.125, "DAY"),
          W(12.125, 12.375, "I"), W(12.375, 12.9, "DIE"), W(13.25, 13.6, "I'MMA"), W(13.6, 13.85, "TOUCH"),
          W(13.85, 14.0, "THE"), W(14.0, 14.7, "SKY", "red")]

LUCIA = [{"type": "type", "t0": 0.35, "t1": 2.4, "text": "This is a free call", "dur": 0.8, "y": 0.56},
         {"type": "type", "t0": 2.45, "t1": 3.8, "text": "Lucia from", "hl": "Lucia", "dur": 0.4, "y": 0.56},
         {"type": "type", "t0": 15.25, "t1": 16.9, "text": "2 days left", "hl": "2 days", "dur": 0.5, "y": 0.56}]

LUCIA_GRADE = ("eq=contrast=1.05:brightness=0.015:saturation=1.12:gamma=0.96,"
               "colorbalance=rs=0.04:gs=0.0:bs=-0.04:rh=0.05:gh=0.01:bh=-0.05,"
               "split[a][b];[b]gblur=sigma=22[g];[a][g]blend=all_mode=screen:all_opacity=0.20,unsharp=5:5:0.45,"
               "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")

JOBS = {
    "kissed": dict(tpl="og_kissed", ref="og_kissed.mp4", events=KISSED,
                   caption="“Bro, GTA 6 comes out in 2 days” \U0001F62E‍\U0001F4A8", fps=30),
    "heaven": dict(tpl="og_heaven", ref="og_heaven.mp4", events=HEAVEN,
                   caption="GTA 6 in 2 days btw \U0001F62E‍\U0001F4A8", fps=30, split_first=[2.0, 4.0]),
    "lucia": dict(tpl="kairoxx_lucia", ref="kairoxx_lucia.mp4", events=LUCIA, caption=None, fps=60, grade=LUCIA_GRADE,
                  pin={1: ("launch.mp4", 11.27)}),     # the phone-call shot matches the "free call" dialogue
}


def make(name: str, shots: list[Shot], excl: set) -> dict:
    job = JOBS[name]
    tpl = T.load_template(ROOT, job["tpl"])
    tpl["text"] = []
    if name != "lucia":
        tpl["transition"] = "whip"
    if job.get("split_first"):       # intro: each part of the long first slot gets its own shot
        s0 = tpl["slots"][0]
        edges = [s0["t0"], *job["split_first"], s0["t1"]]
        tpl["slots"] = [{**s0, "t0": a, "t1": b} for a, b in zip(edges, edges[1:])] + tpl["slots"][1:]
    fills = T.assign(tpl, shots, exclude=excl)
    for slot, (fname, start) in job.get("pin", {}).items():
        s = next(x for x in shots if Path(x.src).name == fname and abs(x.start - start) < 0.05)
        f = fills[slot]
        dur = f.t1 - f.t0
        fills[slot] = T.Fill(f.t0, f.t1, s, s.start + 0.1, min(1.0, (s.length - 0.15) / dur))
    if job.get("first_min"):         # the intro window/mask needs one long, moving shot
        f = fills[0]
        dur = f.t1 - f.t0
        cand = [x for x in shots if x.usable and not x.ui and x.length >= job["first_min"]
                and (Path(x.src).name, round(x.start, 2)) not in excl]
        best = max(cand, key=lambda x: x.iconic + x.motion * 10)
        fills[0] = T.Fill(f.t0, f.t1, best, best.start + 0.05, min(1.0, (best.length - 0.1) / dur))
    OUT.mkdir(parents=True, exist_ok=True)
    base = OUT / f"_{name}_base.mp4"
    res = T.render_template(tpl, fills, base, {}, src_size=(1920, 1080), vertical_out=True)
    silent_in = Path(res["file"])
    # where the picture sits inside the vertical canvas
    pic = (0, 1920) if tpl["orientation"] == "vertical" else ((1920 - 608) // 2, 608)
    ev = list(job["events"])
    if job["caption"]:
        ev.append({"type": "caption", "t0": 0.0, "t1": tpl["duration"] - 0.3, "text": job["caption"], "size": 58,
                   "abs_y": pic[0] - 60})
    final_silent = OUT / f"PRIVATE-TEST_gta6_{name}_2d_silent.mp4"
    L.apply(silent_in, final_silent, L.Overlay(ev, pic), fps=job["fps"], grade=job.get("grade"))
    final = OUT / f"PRIVATE-TEST_gta6_{name}_2d.mp4"
    L.mux(final_silent, str(ROOT / "assets/hype_refs" / job["ref"]), final)
    silent_in.unlink(missing_ok=True)
    used = [[Path(f.shot.src).name, round(f.shot.start, 2)] for f in fills]
    return {"name": name, "file": str(final), "silent": str(final_silent), "upscale": res["upscale"], "shots": res["shots"],
            "used": used}


if __name__ == "__main__":
    names = sys.argv[1:] or ["kissed", "heaven", "lucia"]
    shots = shots_all()
    excl = recent()
    for n in names:
        r = make(n, shots, excl)
        excl |= {tuple(u) for u in r["used"]}
        remember(r["used"])
        print(json.dumps({k: r[k] for k in ("name", "file", "silent", "upscale")}))
        print("   shots:", [(s["src"], s["src_t"]) for s in r["shots"]])
