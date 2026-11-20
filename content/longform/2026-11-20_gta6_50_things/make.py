"""Render LF2 "50 Things You NEED to Know About GTA 6 (Before You Play)" — 16:9, official Rockstar footage only.

Visual sources: 'el:<sec>' = Rockstar "An Extended Look" (1080p working copy), 'img:<path>' = official 4K launch
screenshots (Rockstar media kit), 'file:<path>@<sec>' = other official clips. Overlays: progress bar + "17/50"
counter, item title in the lower third (never over faces), status chip (confirmed / from previews / reports differ),
3-word captions, chapter cards. No music (owner adds Audio Library music on YouTube).

Usage: python content/longform/2026-11-20_gta6_50_things/make.py [vo_dir] [out] [section ids...]
"""
import json
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from clipper.editing import longform as L  # noqa: E402

W, H, FPS = 1920, 1080, 30
EL = ROOT / "assets/footage/gta6_official/extended_look_1080.mp4"
SHOTS = ROOT / "assets/official/gta6/launch_gallery"
RED, PINK, GREEN, AMBER = (40, 30, 225), (150, 70, 255), (90, 170, 40), (30, 160, 235)
PRE, POST = 0.3, 0.45
P = "img:Places/"
PE = "img:People/"

VIS = {
    "hook": ["el:552.5", "el:1060.5", "el:704.5", "el:1564.5", "el:1128.5", "el:380.5", "el:1040.5", "el:1568.2"],
    "ch1": ["el:1544.5"],
    "1": ["file:assets/footage/gta6_extended/out_now_yt.mp4@0.3", "el:516.5"],
    "2": ["el:380.5", "el:368.5"],
    "3": ["el:516.5", "el:1140.5"],
    "4": ["stamp:99|METACRITIC|tied for the highest score ever|el:1568.2"],
    "5": ["el:1216.5", "el:1224.5"],
    "6": ["el:840.5", "el:862.5"],
    "7": ["region:Vice City/Vice_City_03.jpg|VICE CITY", "region:Leonida Keys/Leonida_Keys_02.jpg|LEONIDA KEYS",
          "region:Grassrivers/Grassrivers_02.jpg|GRASSRIVERS", "region:Port Gellhorn/Port_Gellhorn_02.jpg|PORT GELLHORN",
          "region:Ambrosia/Ambrosia_02.jpg|AMBROSIA", "region:Mount Kalaga National Park/Mount_Kalaga_National_Park_02.jpg|MOUNT KALAGA"],
    "8": ["el:992.5", "stamp:~2x|THE SIZE OF GTA 5|no official number from Rockstar|el:1140.5"],
    "9": [P + "Leonida Keys/Leonida_Keys_01.jpg", P + "Leonida Keys/Leonida_Keys_04.jpg"],
    "10": ["el:1128.5", "el:464.5"],
    "11": ["el:704.5", "el:1080.5"],
    "12": ["el:464.5", "el:468.5", P + "Grassrivers/Grassrivers_05.jpg"],
    "13": [P + "Mount Kalaga National Park/Mount_Kalaga_National_Park_04.jpg", P + "Grassrivers/Grassrivers_07.jpg"],
    "14": ["el:1564.5", "el:572.5"],
    "15": ["el:788.5", "el:1568.2"],
    "ch2": ["el:992.5"],
    "ch3": ["el:1180.5"],
    "16": [PE + "Jason Duval/Jason_Duval_02.jpg", PE + "Lucia Caminos/Lucia_Caminos_02.jpg"],
    "17": ["el:385.5", "el:413.5"],
    "18": ["el:800.5", "el:848.5"],
    "19": ["el:1056.5", "el:1182.5"],
    "20": ["el:1040.5", "el:1032.5"],
    "21": ["el:472.5", "el:1552.5"],
    "ch4": ["el:568.5"],
    "22": ["el:568.5", "el:708.5"],
    "23": ["el:552.5", "el:1061.5"],
    "24": ["el:640.5", "el:688.5"],
    "25": ["el:980.5", "el:1004.5"],
    "ch5": ["el:704.5"],
    "26": ["el:705.5", "el:1068.5"],
    "27": ["el:708.5", "el:712.5"],
    "28": ["el:716.5", "el:720.5"],
    "29": ["el:1080.5", "el:724.5"],
    "30": ["el:1081.5", "el:569.5"],
    "ch6": ["el:1060.5"],
    "31": ["el:556.5", "el:560.5"],
    "32": ["stars:el:1062.5"],
    "33": ["el:752.5", "el:841.5"],
    "34": ["el:862.5", "el:848.5"],
    "35": ["el:1000.5", "el:1092.5"],
    "36": ["el:1093.5", "el:381.5"],
    "37": ["el:1064.5", "el:1063.5"],
    "38": ["el:1396.5", "el:1520.5"],
    "ch7": ["el:484.5"],
    "39": ["el:484.5", "el:369.5"],
    "40": ["el:1432.5", "el:1100.5"],
    "41": ["el:1060.0", "el:753.5"],
    "42": ["el:528.5", "el:1069.5"],
    "43": ["el:1068.0", "el:496.5"],
    "ch8": ["el:696.5"],
    "44": ["el:696.5", "el:1521.5"],
    "45": ["el:842.5", "el:1397.5"],
    "46": ["el:1565.5", "el:1148.5"],
    "47": ["el:1398.0", "el:1522.5"],
    "48": ["el:1216.0", "el:540.5"],
    "49": ["el:1048.5", "el:1036.5", "el:1044.5"],
    "50": ["el:1180.0", "el:1548.5", "el:1568.0"],
    "outro": ["el:1548.0", "el:1572.5"],
}
STATUS = {"confirmed": ("CONFIRMED", GREEN), "reported": ("FROM PREVIEWS & INTERVIEWS", AMBER),
          "conflicting": ("REPORTS DIFFER", RED)}


# ------------------------------------------------------------------------------------------- sources
def read_video(path, t, dur):
    n = max(1, int(round(dur * FPS)))
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-t", f"{dur + 0.3:.3f}",
                        "-vf", f"scale={W}:{H}:flags=lanczos,fps={FPS}", "-an", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                       capture_output=True, check=True).stdout
    sz = W * H * 3
    fs = [np.frombuffer(p[i * sz:(i + 1) * sz], np.uint8).reshape(H, W, 3) for i in range(len(p) // sz)]
    while len(fs) < n:
        fs.append(fs[-1] if fs else np.zeros((H, W, 3), np.uint8))
    return fs[:n]


@lru_cache(maxsize=64)
def load_img(rel):
    im = cv2.imread(str(SHOTS / rel))
    return cv2.resize(im, (int(W * 1.12), int(H * 1.12)), interpolation=cv2.INTER_AREA)


def ken_burns(rel, dur, seed=0):
    im = load_img(rel)
    n = max(1, int(round(dur * FPS)))
    ih, iw = im.shape[:2]
    out = []
    for i in range(n):
        k = i / max(1, n - 1)
        z = 1.0 + 0.10 * (k if seed % 2 == 0 else 1 - k)
        cw, ch = int(iw / 1.12 * (1.12 / z)), int(ih / 1.12 * (1.12 / z))
        cw, ch = min(cw, iw), min(ch, ih)
        x = int((iw - cw) * (0.5 + 0.2 * (k - 0.5) * (1 if seed % 3 else -1)))
        y = (ih - ch) // 2
        out.append(cv2.resize(im[y:y + ch, x:x + cw], (W, H), interpolation=cv2.INTER_LINEAR))
    return out


def src_frames(ref, dur, seed=0):
    if ref.startswith("el:"):
        t = float(ref[3:])
        if 352 <= t <= 380:
            t = 380.5
        return read_video(EL, t, dur)
    if ref.startswith("img:"):
        return ken_burns(ref[4:], dur, seed)
    if ref.startswith("file:"):
        path, t = ref[5:].rsplit("@", 1)
        return read_video(ROOT / path, float(t), dur)
    raise ValueError(ref)


# ------------------------------------------------------------------------------------------- timeline
def build(script, vo):
    secs, audio, t = [], [], 0.0
    for sec in script["sections"]:
        sid = sec["id"]
        meta = json.loads((vo / f"{sid}.wav.json").read_text())
        toks = L.align(sec["text"], meta["words"])
        start = t + (0.15 if sid == "hook" else PRE)
        end = start + meta["dur"] + (0.7 if sec.get("chapter") else POST)
        if sid == "outro":
            end += 12.0                                  # end-screen space
        audio.append((str(vo / f"{sid}.wav"), start))
        words = [{**x, "s": x["s"] + start, "e": x["e"] + start} for x in toks]
        secs.append({**sec, "t0": t, "t1": end, "start": start, "words": words, "sents": L.sentences(words)})
        t = end
    return secs, audio, t


def chunks(secs):
    out = []
    for s in secs:
        if s.get("chapter"):
            continue
        for se in s["sents"]:
            tk = se["tokens"]
            for i in range(0, len(tk), 3):
                part = tk[i:i + 3]
                out.append({"t0": part[0]["s"], "t1": part[-1]["e"] + 0.08, "words": [p["w"] for p in part]})
    for a, b in zip(out, out[1:]):
        if 0 < b["t0"] - a["t1"] < 0.25:
            a["t1"] = b["t0"]
    return out


# ------------------------------------------------------------------------------------------- overlays
def lower_title(f, text, t, t0):
    k = L.pop(t, t0, 0.3) * (1 - L.pop(t, t0 + 3.2, 0.3))
    if k <= 0.01:
        return
    im = L.text_rgba(text, "anton", 74, (255, 255, 255))
    x0, y = 70, H - 300
    L.box(f, x0 - 16, y - im.shape[0] / 2 + 8, x0 + im.shape[1] + 16, y + im.shape[0] / 2 - 8, RED, 0.92 * k, 10)
    L.over(f, im, x0 + (1 - k) * -40, y, k, anchor="l")


def counter(f, n, prog):
    cv2.rectangle(f, (0, 0), (W, 8), (40, 40, 40), -1)
    cv2.rectangle(f, (0, 0), (int(W * prog), 8), PINK, -1)
    im = L.text_rgba(f"{n}", "anton", 64, (255, 255, 255))
    sm = L.text_rgba("/ 50", "anton", 34, (200, 200, 200))
    L.box(f, 40, 30, 40 + im.shape[1] + sm.shape[1] + 34, 30 + im.shape[0] - 18, (20, 20, 20), 0.82, 12)
    L.over(f, im, 52, 30 + im.shape[0] / 2 - 9, 1, anchor="l")
    L.over(f, sm, 58 + im.shape[1], 30 + im.shape[0] / 2 - 2, 1, anchor="l")


def status_chip(f, status, t, t0):
    if status not in STATUS:
        return
    txt, col = STATUS[status]
    k = L.pop(t, t0 + 0.6, 0.3)
    L.chip(f, txt, W - 70 - L.text_rgba(txt, "inter", 24, (255, 255, 255), shadow=False).shape[1], 62,
           color=col, size=24, alpha=k)


def chapter_card(f, sec, t, idx):
    f[:] = L.blur_bg(f, 0.38)
    k = L.pop(t, sec["t0"] + 0.05, 0.35)
    a = L.text_rgba(f"CHAPTER {idx}", "inter", 40, PINK)
    b = L.text_rgba(sec["label"], "anton", 150, (255, 255, 255))
    L.over(f, a, W / 2, H / 2 - 110 + (1 - k) * 20, k)
    sc = 1.15 - 0.15 * k
    L.over(f, cv2.resize(b, None, fx=sc, fy=sc), W / 2, H / 2 + 20, k)


def stamp(f, big, mid, small, t, t0):
    f[:] = L.blur_bg(f, 0.45)
    k = L.pop(t, t0 + 0.1, 0.35)
    a = L.text_rgba(big, "anton", 300, RED)
    sc = 1.3 - 0.3 * k
    L.over(f, cv2.resize(a, None, fx=sc, fy=sc), W / 2, H / 2 - 90, k)
    L.over(f, L.text_rgba(mid, "anton", 90, (255, 255, 255)), W / 2, H / 2 + 110, L.pop(t, t0 + 0.35, 0.3))
    L.over(f, L.text_rgba(small, "inter", 34, (210, 210, 210)), W / 2, H / 2 + 190, L.pop(t, t0 + 0.6, 0.3))


def stars(f, t, t0):
    k = L.pop(t, t0 + 0.2, 0.3)
    for i in range(6):
        kk = L.pop(t, t0 + 0.4 + i * 0.22, 0.2)
        im = L.text_rgba("★", "interx", 120, (255, 255, 255) if i < 5 else (60, 200, 255))
        if im is None:
            continue
        L.over(f, im, W / 2 + (i - 2.5) * 150, 190, kk * k)


def title_card(f, t, t0):
    f[:] = L.blur_bg(f, 0.4)
    k = L.pop(t, t0, 0.35)
    L.over(f, L.text_rgba("50 THINGS", "anton", 210, RED), W / 2, H / 2 - 120, k)
    L.over(f, L.text_rgba("YOU NEED TO KNOW ABOUT GTA 6", "anton", 96, (255, 255, 255)), W / 2, H / 2 + 60,
           L.pop(t, t0 + 0.2, 0.3))


# ------------------------------------------------------------------------------------------- render
def render(secs, audio, total, out):
    caps = chunks(secs)
    items = [s for s in secs if s["id"].isdigit()]
    silent = out.with_name(out.stem + "_video.mp4")
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                            "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)
    fi, ci = 0, 0
    chap_idx = 0
    for sec in secs:
        sid = sec["id"]
        if sec.get("chapter"):
            chap_idx += 1
        vis = VIS[sid]
        n_sec = int(round(sec["t1"] * FPS)) - fi
        per = n_sec / len(vis)
        title_t = None
        if sid == "hook":                                   # title card on "So here are fifty things..."
            for se in sec["sents"]:
                if se["text"].lower().startswith("so here are"):
                    title_t = se["t0"]
        for vi, ref in enumerate(vis):
            n = int(round(per * (vi + 1))) - int(round(per * vi))
            kind, arg = (ref.split(":", 1) + [""])[:2] if ref.split(":", 1)[0] in ("stamp", "stars", "region") else ("v", ref)
            if kind == "stamp":
                big, mid, small, bg = arg.split("|", 3)
                frames = src_frames(bg, n / FPS)
            elif kind == "stars":
                frames = src_frames(arg, n / FPS)
            elif kind == "region":
                rel, name = arg.split("|")
                frames = ken_burns("Places/" + rel, n / FPS, vi)
            else:
                frames = src_frames(ref, n / FPS, vi)
            seg_t0 = fi / FPS
            for f in frames[:n]:
                f = f.copy()
                t = fi / FPS
                if sec.get("chapter"):
                    chapter_card(f, sec, t, chap_idx)
                elif kind == "stamp":
                    stamp(f, big, mid, small, t, seg_t0)
                elif title_t is not None and t >= title_t - 0.1 and vi == len(vis) - 1:
                    title_card(f, t, title_t - 0.1)
                if kind == "stars":
                    stars(f, t, seg_t0)
                if kind == "region":
                    kk = L.pop(t, seg_t0 + 0.1, 0.25)
                    im = L.text_rgba(name, "anton", 96, (255, 255, 255))
                    L.box(f, W / 2 - im.shape[1] / 2 - 18, H / 2 - im.shape[0] / 2 + 6, W / 2 + im.shape[1] / 2 + 18,
                          H / 2 + im.shape[0] / 2 - 6, PINK, 0.9 * kk, 12)
                    L.over(f, im, W / 2, H / 2, kk)
                if sid.isdigit():
                    n_item = int(sid)
                    counter(f, n_item, n_item / 50)
                    lower_title(f, sec.get("label", ""), t, sec["start"] + 1.0)
                    status_chip(f, sec.get("status"), t, sec["start"])
                if sid == "outro" and t > sec["start"] + json.loads((Path(audio[-1][0]).with_suffix(".wav.json")).read_text())["dur"]:
                    f[:] = L.blur_bg(f, 0.5)
                    L.over(f, L.text_rgba("SUBSCRIBE FOR MORE GTA 6", "anton", 90, (255, 255, 255)), W / 2, 170, 1)
                while ci < len(caps) and caps[ci]["t1"] < t:
                    ci += 1
                if ci < len(caps) and caps[ci]["t0"] <= t and not sec.get("chapter") and kind != "stamp":
                    L.draw_caption(f, caps[ci], t)
                enc.stdin.write(np.ascontiguousarray(f).tobytes())
                fi += 1
        print(f"{sid:6s} {fi / FPS:7.1f}s", flush=True)
    enc.stdin.close()
    enc.wait()
    inputs, filters = [], []
    for i, (wav, st) in enumerate(audio):
        inputs += ["-i", wav]
        filters.append(f"[{i}:a]aresample=48000,adelay={int(st * 1000)}|{int(st * 1000)}[a{i}]")
    k = len(audio)
    wt = [s["t0"] + 0.05 for s in secs if s.get("chapter")]
    for j, w in enumerate(wt):
        inputs += ["-f", "lavfi", "-t", "0.6", "-i", "anoisesrc=color=pink:amplitude=0.25:sample_rate=48000"]
        filters.append(f"[{k + j}:a]highpass=f=400,lowpass=f=3500,afade=t=in:d=0.25,afade=t=out:st=0.3:d=0.3,volume=0.35,"
                       f"adelay={int(w * 1000)}|{int(w * 1000)}[w{j}]")
    mix = "".join(f"[a{i}]" for i in range(k)) + "".join(f"[w{j}]" for j in range(len(wt)))
    filters.append(f"{mix}amix=inputs={k + len(wt)}:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[out]")
    narr = out.with_name(out.stem + "_audio.m4a")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]",
                    "-t", f"{total:.3f}", "-c:a", "aac", "-b:a", "192k", str(narr)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(narr), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "copy", "-movflags", "+faststart", str(out)], check=True)
    silent.unlink(missing_ok=True)


def chapters_txt(secs):
    out = []
    for s in secs:
        if s["id"] == "hook" or s.get("chapter"):
            m, sc = divmod(int(s["t0"]), 60)
            out.append(f"{m}:{sc:02d} " + ("Intro" if s["id"] == "hook" else s["label"].title()))
        if s["id"] == "outro":
            m, sc = divmod(int(s["t0"]), 60)
            out.append(f"{m}:{sc:02d} Outro")
    return out


def srt(secs):
    def ts(x):
        h, r = divmod(x, 3600)
        m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"
    lines, k = [], 1
    for sec in secs:
        for s in sec["sents"]:
            lines += [str(k), f"{ts(s['t0'])} --> {ts(s['t1'])}", s["text"], ""]
            k += 1
    return "\n".join(lines)


if __name__ == "__main__":
    vo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/claude-0/lf2vo")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "outputs/longform/LF2_GTA6_50_Things.mp4"
    only = sys.argv[3:]
    script = json.loads((HERE / "script.json").read_text())
    if only:
        script["sections"] = [s for s in script["sections"] if s["id"] in only]
    out.parent.mkdir(parents=True, exist_ok=True)
    secs, audio, total = build(script, vo)
    render(secs, audio, total, out)
    out.with_suffix(".srt").write_text(srt(secs))
    out.with_name(out.stem + "_chapters.txt").write_text("\n".join(chapters_txt(secs)))
    print(json.dumps({"file": str(out), "duration": round(total, 1)}))
    print("\n".join(chapters_txt(secs)))
