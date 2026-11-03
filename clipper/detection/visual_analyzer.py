"""Visual analysis with OpenCV: scene changes, motion, faces, sharpness, black frames."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ..core.media import read_frames

_CASCADE = None


def face_detector():
    global _CASCADE
    if _CASCADE is None:
        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        _CASCADE = cv2.CascadeClassifier(str(path))
        if _CASCADE.empty():
            raise RuntimeError(f"could not load Haar cascade {path}")
    return _CASCADE


def detect_faces(rgb: np.ndarray, min_size_frac: float = 0.06) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    ms = max(16, int(rgb.shape[0] * min_size_frac))
    faces = face_detector().detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(ms, ms))
    return [tuple(int(v) for v in f) for f in faces] if len(faces) else []


@dataclass
class VisualFeatures:
    fps: float
    width: int
    height: int
    scene: np.ndarray = field(default_factory=lambda: np.zeros(0))     # 0..1 change score per sample
    motion: np.ndarray = field(default_factory=lambda: np.zeros(0))
    faces: np.ndarray = field(default_factory=lambda: np.zeros(0))     # face count
    sharpness: np.ndarray = field(default_factory=lambda: np.zeros(0))
    brightness: np.ndarray = field(default_factory=lambda: np.zeros(0))
    face_spread: np.ndarray = field(default_factory=lambda: np.zeros(0))  # horizontal spread of faces (0..1)

    def _sl(self, start: float, end: float) -> slice:
        a = int(max(0, start * self.fps))
        b = int(max(a + 1, end * self.fps))
        return slice(a, min(b, len(self.scene)))

    def stat(self, name: str, start: float, end: float, fn=np.mean) -> float:
        arr = getattr(self, name)[self._sl(start, end)]
        return float(fn(arr)) if arr.size else 0.0

    def save(self, path: Path) -> None:
        np.savez_compressed(path, scene=self.scene, motion=self.motion, faces=self.faces,
                            sharpness=self.sharpness, brightness=self.brightness,
                            face_spread=self.face_spread, meta=np.array([self.fps, self.width, self.height]))

    @classmethod
    def load(cls, path: Path) -> "VisualFeatures":
        d = np.load(path)
        fps, w, h = d["meta"].tolist()
        return cls(fps, int(w), int(h), d["scene"], d["motion"], d["faces"], d["sharpness"],
                   d["brightness"], d["face_spread"])


def analyze_video(path: str | Path, duration: float, fps: float = 1.0, width: int = 480,
                  face_every: int = 1) -> VisualFeatures:
    scene, motion, faces, sharp, bright, spread = [], [], [], [], [], []
    prev_hist, prev_gray = None, None
    h = 0
    for i, fr in enumerate(read_frames(path, 0, duration, fps, width)):
        h = fr.shape[0]
        hsv = cv2.cvtColor(fr, cv2.COLOR_RGB2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        gray = cv2.cvtColor(fr, cv2.COLOR_RGB2GRAY)
        scene.append(0.0 if prev_hist is None else float(
            min(1.0, cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA))))
        motion.append(0.0 if prev_gray is None else float(np.mean(cv2.absdiff(gray, prev_gray)) / 255.0))
        sharp.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
        bright.append(float(gray.mean() / 255.0))
        if i % face_every == 0:
            fs = detect_faces(fr)
            faces.append(len(fs))
            if len(fs) >= 2:
                xs = [x + w / 2 for x, y, w, hh in fs]
                spread.append((max(xs) - min(xs)) / width)
            else:
                spread.append(0.0)
        else:
            faces.append(faces[-1] if faces else 0)
            spread.append(spread[-1] if spread else 0.0)
        prev_hist, prev_gray = hist, gray
    return VisualFeatures(fps, width, h, np.array(scene, np.float32), np.array(motion, np.float32),
                          np.array(faces, np.int16), np.array(sharp, np.float32),
                          np.array(bright, np.float32), np.array(spread, np.float32))
