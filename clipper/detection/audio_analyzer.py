"""Audio signal analysis: loudness envelope, arousal spikes, silence, quality proxies.

Loudness is one signal among many — it never decides virality on its own.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..core.media import read_wav_mono

HOP = 0.1  # seconds per envelope frame


@dataclass
class AudioFeatures:
    hop: float
    db: np.ndarray            # loudness per frame (dBFS)
    z: np.ndarray             # loudness relative to a rolling local baseline (robust z-score)
    silence: np.ndarray       # bool per frame
    clipped_fraction: float
    noise_floor_db: float
    speech_level_db: float

    @property
    def duration(self) -> float:
        return len(self.db) * self.hop

    def idx(self, t: float) -> int:
        return int(np.clip(t / self.hop, 0, max(0, len(self.db) - 1)))

    def slice(self, start: float, end: float) -> slice:
        return slice(self.idx(start), max(self.idx(start) + 1, self.idx(end)))

    def peak_z(self, start: float, end: float) -> float:
        s = self.z[self.slice(start, end)]
        return float(s.max()) if s.size else 0.0

    def mean_z(self, start: float, end: float) -> float:
        s = self.z[self.slice(start, end)]
        return float(s.mean()) if s.size else 0.0

    def silence_fraction(self, start: float, end: float) -> float:
        s = self.silence[self.slice(start, end)]
        return float(s.mean()) if s.size else 1.0

    def snr_db(self) -> float:
        return self.speech_level_db - self.noise_floor_db

    def save(self, path: Path) -> None:
        np.savez_compressed(path, db=self.db, z=self.z, silence=self.silence,
                            meta=np.array([self.hop, self.clipped_fraction, self.noise_floor_db,
                                           self.speech_level_db]))

    @classmethod
    def load(cls, path: Path) -> "AudioFeatures":
        d = np.load(path)
        hop, clip, nf, sl = d["meta"].tolist()
        return cls(hop, d["db"], d["z"], d["silence"].astype(bool), clip, nf, sl)


def _rolling_median(x: np.ndarray, win: int) -> np.ndarray:
    if len(x) == 0:
        return x
    # block-wise median (fast for multi-hour streams), linearly interpolated
    step = max(1, win // 4)
    centers = np.arange(0, len(x), step)
    meds = np.array([np.median(x[max(0, c - win // 2): c + win // 2 + 1]) for c in centers])
    return np.interp(np.arange(len(x)), centers, meds)


def analyze_wav(path: str | Path, baseline_seconds: float = 30.0, silence_db: float = -45.0) -> AudioFeatures:
    data, sr = read_wav_mono(path)
    return analyze_samples(data, sr, baseline_seconds, silence_db)


def analyze_samples(data: np.ndarray, sr: int, baseline_seconds: float = 30.0,
                    silence_db: float = -45.0) -> AudioFeatures:
    hop_n = int(sr * HOP)
    n = len(data) // hop_n
    if n == 0:
        z = np.zeros(1)
        return AudioFeatures(HOP, np.full(1, -90.0), z, np.ones(1, bool), 0.0, -90.0, -90.0)
    frames = data[: n * hop_n].reshape(n, hop_n)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    base = _rolling_median(db, int(baseline_seconds / HOP))
    dev = db - base
    mad = np.median(np.abs(dev - np.median(dev))) + 1e-6
    z = np.clip(dev / (1.4826 * mad), -5, 8)
    silence = db < silence_db
    clipped = float(np.mean(np.abs(data) > 0.99))
    voiced = db[~silence]
    nf = float(np.percentile(db, 10))
    sl = float(np.percentile(voiced, 90)) if voiced.size else nf
    return AudioFeatures(HOP, db.astype(np.float32), z.astype(np.float32), silence, clipped, nf, sl)


def envelope_fingerprint(feat: AudioFeatures, start: float, end: float, bins: int = 64) -> list[float]:
    """Coarse normalised loudness contour for near-duplicate / same-event matching."""
    seg = feat.db[feat.slice(start, end)].astype(np.float64)
    if seg.size < 2:
        return [0.0] * bins
    xs = np.linspace(0, seg.size - 1, bins)
    v = np.interp(xs, np.arange(seg.size), seg)
    v = v - v.mean()
    sd = v.std()
    return (v / sd if sd > 1e-6 else v).round(3).tolist()


def fingerprint_similarity(a: list[float], b: list[float], max_shift: int = 6) -> float:
    """Max normalised cross-correlation over small shifts (−1..1)."""
    x, y = np.asarray(a, float), np.asarray(b, float)
    if x.size != y.size or x.size == 0 or x.std() < 1e-6 or y.std() < 1e-6:
        return 0.0
    best = -1.0
    for s in range(-max_shift, max_shift + 1):
        if s >= 0:
            xa, ya = x[s:], y[: len(y) - s]
        else:
            xa, ya = x[: len(x) + s], y[-s:]
        if xa.size < 8:
            continue
        c = float(np.corrcoef(xa, ya)[0, 1])
        best = max(best, c)
    return best
