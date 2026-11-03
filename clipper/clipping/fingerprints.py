"""Perceptual fingerprints for rendered clips: frame dHash sequence + audio envelope."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..core.media import extract_audio_wav, media_info, read_frames
from ..detection.audio_analyzer import analyze_wav, envelope_fingerprint


def dhash(rgb: np.ndarray, size: int = 8) -> int:
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    small = cv2.resize(g, (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return v


def video_phash(path: str | Path, samples: int = 8) -> list[str]:
    info = media_info(path)
    dur = info["duration"]
    out = []
    for i in range(samples):
        t = dur * (i + 0.5) / samples
        frames = list(read_frames(path, t, 0.05, 25, 160, 284))
        if frames:
            out.append(f"{dhash(frames[0]):016x}")
    return out


def phash_distance(a: list[str], b: list[str]) -> float:
    """Mean Hamming distance (0..64) between aligned frame hashes."""
    n = min(len(a), len(b))
    if n == 0:
        return 64.0
    return float(np.mean([bin(int(a[i], 16) ^ int(b[i], 16)).count("1") for i in range(n)]))


def audio_fingerprint(path: str | Path, work: Path) -> list[float]:
    wav = extract_audio_wav(path, work / (Path(path).stem + ".fp.wav"))
    feat = analyze_wav(wav)
    wav.unlink(missing_ok=True)
    return envelope_fingerprint(feat, 0, feat.duration)
