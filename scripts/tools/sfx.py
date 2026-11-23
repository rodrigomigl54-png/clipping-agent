"""Our own meme-style sound effects, synthesized in code (no third-party audio -> no Content ID risk).

Each function returns stereo float32 at 48 kHz. Run this file to write assets/sfx/<name>.wav for listening.
  boom      deep "vine boom"-style hit (sub sweep + saturated body + short tail)       -> reveal / punchline
  whoosh    filtered noise sweep                                                        -> transition / slot fill
  pop       short bubbly pop                                                            -> label appears
  ding      bright bell                                                                 -> point scored
  kaching   cash-register: bell + rattle                                                -> money
  fail      sad "wah wah wah wahhh" trombone-like descending notes                      -> fail / crash
  scratch   record scratch                                                              -> sudden stop / interruption
  riser     rising noise + tone, 1.6 s                                                  -> build-up before #1
  punch     low thud + crack                                                            -> hit / fight
  dun       dramatic "dun dun dunnn" sting                                              -> twist
"""
from pathlib import Path

import numpy as np

SR = 48000
OUT = Path(__file__).resolve().parents[2] / "assets/sfx"


def _t(d):
    return np.arange(int(d * SR)) / SR


def _env(n, a=0.005, r=0.2):
    e = np.ones(n)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, na)
    e[-nr:] *= np.linspace(1, 0, nr) ** 2
    return e


def _st(x, g=0.9):
    x = x / (np.max(np.abs(x)) + 1e-9) * g
    return np.stack([x, x], 1).astype(np.float32)


def _lp(x, k):
    k = max(1, int(k))
    return np.convolve(x, np.ones(k) / k, mode="same")


def _reverb(x, decay=0.35, n=6):
    y = x.copy()
    for i in range(1, n + 1):
        d = int(SR * 0.023 * i * 1.7)
        y[d:] += x[:-d] * (decay ** i)
    return y


def boom():
    t = _t(1.3)
    f = 95 * np.exp(-t * 2.2) + 38
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.tanh(3.2 * np.sin(ph)) * np.exp(-t * 2.3)
    click = np.random.default_rng(1).normal(0, 1, len(t)) * np.exp(-t * 60) * 0.5
    return _st(_reverb(body + click, 0.3))


def whoosh(d=0.45):
    t = _t(d)
    n = np.random.default_rng(2).normal(0, 1, len(t))
    out = np.zeros_like(n)
    for i, k in enumerate(np.linspace(40, 4, 12)):          # sweep: dark -> bright
        seg = slice(int(i * len(t) / 12), int((i + 1) * len(t) / 12))
        out[seg] = (n - _lp(n, k))[seg]
    return _st(out * np.sin(np.pi * t / d) ** 2, 0.6)


def pop():
    t = _t(0.12)
    f = 900 - 5000 * t
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 40)
    return _st(x, 0.7)


def ding(f0=1568):
    t = _t(0.9)
    x = sum(a * np.sin(2 * np.pi * f0 * m * t) for a, m in ((1, 1), (0.4, 2.76), (0.2, 5.4))) * np.exp(-t * 5)
    return _st(x * _env(len(t), 0.002, 0.05), 0.6)


def kaching():
    t = _t(1.0)
    bell = sum(a * np.sin(2 * np.pi * f * t) for a, f in ((1, 2093), (0.6, 2637), (0.4, 3136))) * np.exp(-t * 4)
    rng = np.random.default_rng(3)
    rattle = rng.normal(0, 1, len(t)) * (np.sin(2 * np.pi * 28 * t) > 0.6) * np.exp(-t * 9) * 0.35
    x = np.concatenate([np.zeros(int(0.06 * SR)), bell])[:len(t)] + rattle
    return _st(x, 0.7)


def fail():
    notes = [(392, 0.32), (370, 0.32), (349, 0.32), (330, 1.1)]
    out = []
    for i, (f, d) in enumerate(notes):
        t = _t(d)
        vib = 1 + (0.012 * np.sin(2 * np.pi * 5.5 * t) if i == 3 else 0 * t)
        ph = 2 * np.pi * np.cumsum(f * vib * (1 - (0.06 * t / d if i == 3 else 0))) / SR
        x = sum(np.sin(k * ph) / k for k in range(1, 9))          # brassy saw-ish
        x = _lp(x, 6) * _env(len(t), 0.02, 0.08 if i < 3 else 0.5)
        out.append(x)
    return _st(np.concatenate(out), 0.6)


def scratch():
    t = _t(0.55)
    rng = np.random.default_rng(4)
    n = rng.normal(0, 1, len(t))
    speed = np.abs(np.sin(2 * np.pi * 3.2 * t)) * 30 + 2
    out = np.zeros_like(n)
    for i in range(0, len(t), 240):
        out[i:i + 240] = _lp(n, speed[i])[i:i + 240]
    tone = np.sin(2 * np.pi * np.cumsum(400 + 900 * np.sin(2 * np.pi * 3.2 * t)) / SR) * 0.4
    return _st((out * 3 + tone) * _env(len(t), 0.005, 0.1), 0.65)


def riser(d=1.6):
    t = _t(d)
    n = np.random.default_rng(5).normal(0, 1, len(t))
    tone = np.sin(2 * np.pi * np.cumsum(200 + 900 * (t / d) ** 2) / SR)
    x = (n - _lp(n, 12)) * 0.5 + tone * 0.6
    return _st(x * (t / d) ** 2.2, 0.55)


def punch():
    t = _t(0.45)
    f = 140 * np.exp(-t * 18) + 50
    thud = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14)
    crack = np.random.default_rng(6).normal(0, 1, len(t)) * np.exp(-t * 80)
    return _st(np.tanh(2.5 * (thud + 0.6 * crack)), 0.9)


def dun():
    out = []
    for f, d in ((98, 0.28), (98, 0.28), (92.5, 1.4)):
        t = _t(d)
        ph = 2 * np.pi * f * t
        x = sum(np.sin(k * ph) / k for k in range(1, 12)) + 0.5 * np.sin(ph / 2)
        out.append(_lp(x, 4) * _env(len(t), 0.01, 0.06 if d < 1 else 0.9))
    return _st(_reverb(np.concatenate(out), 0.25), 0.7)


LIB = dict(boom=boom, whoosh=whoosh, pop=pop, ding=ding, kaching=kaching, fail=fail, scratch=scratch,
           riser=riser, punch=punch, dun=dun)
_cache = {}


def get(name):
    if name not in _cache:
        _cache[name] = LIB[name]()
    return _cache[name]


if __name__ == "__main__":
    import wave
    OUT.mkdir(parents=True, exist_ok=True)
    for k in LIB:
        a = get(k)
        w = wave.open(str(OUT / f"{k}.wav"), "wb")
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
        w.close()
        print(k, round(len(a) / SR, 2))
