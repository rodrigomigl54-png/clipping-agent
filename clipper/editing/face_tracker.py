"""Smart face tracking for vertical crops (OpenCV Haar cascade + smoothing).

Produces a smooth camera path (crop centre over time) that follows the primary speaker without
jitter: detections are sampled at a low rate, associated to the previous face, held through
misses, and smoothed with an EMA plus a dead zone.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..core.media import read_frames
from ..detection.visual_analyzer import detect_faces


@dataclass
class CameraPath:
    times: np.ndarray        # seconds relative to clip start
    cx: np.ndarray           # normalised crop centre x (0..1, of source width)
    cy: np.ndarray           # normalised crop centre y
    face_h: np.ndarray       # normalised primary face height (0 if none)
    face_found: float        # fraction of samples with a face
    spread: float            # mean horizontal spread of multiple faces (0..1)
    multi_face: float        # fraction of samples with 2+ faces

    def at(self, t: float) -> tuple[float, float]:
        if self.times.size == 0:
            return 0.5, 0.45
        return float(np.interp(t, self.times, self.cx)), float(np.interp(t, self.times, self.cy))


def track(src: str, start: float, duration: float, *, sample_fps: float = 4, smoothing: float = 0.85,
          dead_zone: float = 0.06, min_face: float = 0.06,
          region: tuple[float, float, float, float] | None = None, width: int = 640) -> CameraPath:
    times, xs, ys, hs = [], [], [], []
    spreads, multi = [], []
    prev = None
    rx, ry, rw, rh = region or (0.0, 0.0, 1.0, 1.0)
    for i, fr in enumerate(read_frames(src, start, duration, sample_fps, width)):
        H, W = fr.shape[:2]
        x0, y0 = int(rx * W), int(ry * H)
        sub = fr[y0:y0 + max(1, int(rh * H)), x0:x0 + max(1, int(rw * W))]
        faces = detect_faces(sub, min_face / max(rh, 1e-3)) if sub.size else []
        faces = [((x0 + x + w / 2) / W, (y0 + y + h / 2) / H, h / H) for x, y, w, h in faces]
        times.append(i / sample_fps)
        if len(faces) >= 2:
            fx = [f[0] for f in faces]
            spreads.append(max(fx) - min(fx))
            multi.append(1)
        else:
            spreads.append(0.0)
            multi.append(0)
        if faces:
            if prev is None:
                pick = max(faces, key=lambda f: f[2])
            else:  # stay on the same person unless someone much larger appears
                pick = min(faces, key=lambda f: abs(f[0] - prev[0]) + abs(f[1] - prev[1]) - 0.5 * f[2])
            prev = pick
            xs.append(pick[0]); ys.append(pick[1]); hs.append(pick[2])
        else:
            xs.append(np.nan); ys.append(np.nan); hs.append(0.0)
    if not times:
        return CameraPath(np.zeros(0), np.zeros(0), np.zeros(0), np.zeros(0), 0.0, 0.0, 0.0)
    x = np.array(xs, float); y = np.array(ys, float)
    found = ~np.isnan(x)
    default_x, default_y = rx + rw / 2, ry + rh * 0.45
    if found.any():
        idx = np.arange(len(x))
        x = np.interp(idx, idx[found], x[found])
        y = np.interp(idx, idx[found], y[found])
    else:
        x[:] = default_x; y[:] = default_y
    # dead zone + EMA smoothing -> steady, deliberate camera
    sx, sy = np.empty_like(x), np.empty_like(y)
    cx, cy = x[0], y[0]
    for i in range(len(x)):
        if abs(x[i] - cx) > dead_zone:
            cx = smoothing * cx + (1 - smoothing) * x[i]
        if abs(y[i] - cy) > dead_zone:
            cy = smoothing * cy + (1 - smoothing) * y[i]
        sx[i], sy[i] = cx, cy
    return CameraPath(np.array(times), sx, sy, np.array(hs), float(found.mean()),
                      float(np.mean(spreads)) if spreads else 0.0, float(np.mean(multi)) if multi else 0.0)
