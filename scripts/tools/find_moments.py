"""Find clip-worthy moments in a stream/video transcript — free, local, OpusClip-style.

Input: <video>.words.json from faster-whisper ({"rms": per-second loudness, "segs": [{s,e,t,w:[[word,t]]}]}).
How it works (what clipping tools score, done with our own signals):
  1. interest curve per second = loudness vs. the local 60 s baseline (screams, hype)
                               + transcript signals (surprise / laughter / hook / argument / emotion words)
                               + speech speed (fast talking = excitement) + trend words (GTA 6, Mandy, ...)
  2. peaks of the curve -> candidate moments
  3. window around each peak: start at the sentence that SETS UP the moment (not mid-sentence, not on
     "and/so/but"), end after the payoff + reaction (sentence end), 12–55 s
  4. score 0–10 each, like OpusClip:
       HOOK  — energy + hook/surprise words in the first 3 s (does it stop the scroll?)
       FLOW  — starts/ends on sentence boundaries, no long dead air, complete thought
       VALUE — size of the peak, laughs / screams / reactions (emotion = shares)
       TREND — trend words (what people search right now)
     total = 0.35 hook + 0.2 flow + 0.3 value + 0.15 trend  (x10 -> 0–100)
  5. also returns the best 2 s "cold open" (the loudest reaction) to put first if the start is slow.
Usage: python scripts/tools/find_moments.py <words.json> [--top 10] [--trend "gta 6,mandy,lucia"]
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from clipper.detection.text_signals import ends_sentence, starts_dangling, text_signals  # noqa: E402

DEFAULT_TREND = ["gta 6", "gta", "mandy", "lucia", "jason", "cops", "police", "stars", "wanted", "ending",
                 "niko", "rockstar", "chat", "marathon"]


def load(path):
    d = json.loads(Path(path).read_text())
    return np.array(d["rms"], float), d["segs"]


def curve(rms, segs, trend):
    n = len(rms)
    loud = np.zeros(n)
    for i in range(n):
        lo, hi = max(0, i - 30), min(n, i + 30)
        base = np.median(rms[lo:hi]) + 1e-4
        loud[i] = max(0.0, rms[i] / base - 1.0)                 # how much louder than usual here
    loud = np.minimum(loud, 4.0) / 4.0
    text = np.zeros(n)
    speed = np.zeros(n)
    for s in segs:
        sig = text_signals(s["t"], set(trend))
        c = sig.counts
        v = (2.0 * c["surprise"] + 2.0 * c["laughter"] + 1.2 * c["hook"] + 1.0 * c["argument"] +
             1.0 * c["emotion"] + 0.8 * c["confusion"] + 0.5 * sig.exclamations + 0.8 * sig.trend_hits)
        a, b = int(s["s"]), max(int(s["s"]) + 1, int(s["e"]))
        dur = max(0.5, s["e"] - s["s"])
        for i in range(a, min(b, n)):
            text[i] += v / max(1.0, dur / 2)
            speed[i] = max(speed[i], len(s["w"]) / dur)
    text = np.minimum(text, 6) / 6
    speed = np.clip((speed - 2.5) / 2.5, 0, 1)
    c = 0.45 * loud + 0.4 * text + 0.15 * speed
    k = np.array([0.25, 0.5, 1, 0.5, 0.25])
    return np.convolve(c, k / k.sum(), mode="same"), loud


def peaks(c, k, sep=25):
    out = []
    for i in np.argsort(-c):
        if c[i] <= 0:
            break
        if all(abs(i - j) >= sep for j in out):
            out.append(int(i))
        if len(out) >= k:
            break
    return out


def window(segs, peak, lo=12, hi=55):
    idx = [i for i, s in enumerate(segs) if s["s"] <= peak + 1]
    if not idx:
        return None
    i = idx[-1]
    a = i
    # walk back to a clean sentence start, at most ~20 s before the peak
    while a > 0 and peak - segs[a - 1]["s"] < 20 and (starts_dangling(segs[a]["t"]) or peak - segs[a]["s"] < 4):
        a -= 1
    b = i
    # walk forward through the reaction until a sentence ends and the clip is long enough
    while b + 1 < len(segs) and (segs[b]["e"] - segs[a]["s"] < lo or not ends_sentence(segs[b]["t"])) \
            and segs[b + 1]["s"] - segs[b]["e"] < 2.5 and segs[b + 1]["e"] - segs[a]["s"] <= hi:
        b += 1
    return segs[a]["s"], segs[b]["e"], a, b


def score(segs, a, b, start, end, c, loud, trend):
    first = " ".join(s["t"] for s in segs[a:b + 1] if s["s"] < start + 3)
    whole = " ".join(s["t"] for s in segs[a:b + 1])
    s0, s1 = int(start), max(int(start) + 1, int(end))
    f = text_signals(first, set(trend))
    w = text_signals(whole, set(trend))
    hook = min(10, 4 * float(np.mean(loud[s0:s0 + 3])) * 2.5 + 2.5 * (f.counts["hook"] + f.counts["surprise"]) +
               1.0 * f.exclamations + (1.5 if f.questions else 0))
    gaps = [segs[i + 1]["s"] - segs[i]["e"] for i in range(a, b)]
    dead = sum(g for g in gaps if g > 1.2)
    flow = 10 - 3 * starts_dangling(segs[a]["t"]) - 3 * (not ends_sentence(segs[b]["t"])) - min(4, dead / 2)
    value = min(10, 6 * float(np.max(c[s0:s1])) + 1.2 * (w.counts["laughter"] + w.counts["surprise"]) +
                0.6 * (w.counts["emotion"] + w.counts["argument"]))
    tr = min(10, 3 * w.trend_hits)
    total = 10 * (0.35 * hook + 0.2 * max(0, flow) + 0.3 * value + 0.15 * tr)
    # cold open: loudest 2 s inside the window (used as the first shot if the start is weak)
    seg_loud = [(float(np.mean(loud[t:t + 2])), t) for t in range(s0, max(s0 + 1, s1 - 2))]
    cold = max(seg_loud)[1] if seg_loud else s0
    return dict(start=round(start, 1), end=round(end, 1), dur=round(end - start, 1), hook=round(hook, 1),
                flow=round(max(0, flow), 1), value=round(value, 1), trend=round(tr, 1), total=round(total),
                cold_open=cold, first_words=first[:90], text=whole[:400])


def find(path, top=10, trend=DEFAULT_TREND):
    rms, segs = load(path)
    c, loud = curve(rms, segs, trend)
    out, used = [], []
    for p in peaks(c, top * 3):
        w = window(segs, p)
        if not w:
            continue
        start, end, a, b = w
        if end - start < 8 or any(min(end, e) - max(start, s) > 0.5 * (end - start) for s, e in used):
            continue
        used.append((start, end))
        out.append(dict(peak=p, **score(segs, a, b, start, end, c, loud, trend)))
    return sorted(out, key=lambda x: -x["total"])[:top]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("words")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--trend", default=",".join(DEFAULT_TREND))
    a = ap.parse_args()
    for m in find(a.words, a.top, [t.strip() for t in a.trend.split(",") if t.strip()]):
        print(f"{m['total']:3d}  {m['start']:7.1f}-{m['end']:7.1f} ({m['dur']:4.1f}s)  H{m['hook']} F{m['flow']} "
              f"V{m['value']} T{m['trend']}  cold@{m['cold_open']}\n      first: {m['first_words']}\n      {m['text']}\n")
