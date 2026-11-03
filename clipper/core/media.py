"""FFmpeg / FFprobe helpers used across modules."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np


class MediaError(RuntimeError):
    pass


def require_binaries() -> dict[str, str | None]:
    return {b: shutil.which(b) for b in ("ffmpeg", "ffprobe")}


def run(cmd: list[str], timeout: float | None = None, check: bool = True,
        input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, input=input_bytes)
    except subprocess.TimeoutExpired as e:
        raise MediaError(f"timeout after {timeout}s: {' '.join(cmd[:4])} ...") from e
    if check and proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[-2000:]
        raise MediaError(f"command failed ({proc.returncode}): {' '.join(cmd[:6])} ...\n{err}")
    return proc


def probe(path: str | Path, timeout: float = 60) -> dict[str, Any]:
    proc = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                "-show_streams", str(path)], timeout=timeout)
    return json.loads(proc.stdout or b"{}")


def media_info(path: str | Path) -> dict[str, Any]:
    data = probe(path)
    fmt = data.get("format", {})
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    info: dict[str, Any] = {
        "duration": float(fmt.get("duration") or 0.0),
        "bit_rate": int(fmt.get("bit_rate") or 0),
        "format_name": fmt.get("format_name"),
        "has_video": v is not None,
        "has_audio": a is not None,
    }
    if v:
        num, _, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1").partition("/")
        try:
            fps = float(num) / float(den or 1)
        except (ValueError, ZeroDivisionError):
            fps = 0.0
        info.update(width=int(v.get("width") or 0), height=int(v.get("height") or 0), fps=fps,
                    video_codec=v.get("codec_name"), pix_fmt=v.get("pix_fmt"),
                    video_duration=float(v.get("duration") or info["duration"]))
    if a:
        info.update(audio_codec=a.get("codec_name"), sample_rate=int(a.get("sample_rate") or 0),
                    channels=int(a.get("channels") or 0),
                    audio_duration=float(a.get("duration") or info["duration"]))
    return info


def extract_audio_wav(src: str | Path, dst: str | Path, sr: int = 16000,
                      start: float | None = None, duration: float | None = None,
                      timeout: float = 3600) -> Path:
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(src)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(sr), "-acodec", "pcm_s16le", str(dst)]
    run(cmd, timeout=timeout)
    return dst


def read_wav_mono(path: str | Path) -> tuple[np.ndarray, int]:
    import wave
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        raw = w.readframes(n)
        ch = w.getnchannels()
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def file_sha256(path: str | Path, limit_bytes: int | None = 64 * 1024 * 1024) -> str:
    """Hash of the first ``limit_bytes`` + file size (fast identity check for large media)."""
    h = hashlib.sha256()
    p = Path(path)
    h.update(str(p.stat().st_size).encode())
    with p.open("rb") as fh:
        remaining = limit_bytes
        while True:
            chunk = fh.read(1024 * 1024 if remaining is None else min(1024 * 1024, remaining))
            if not chunk:
                break
            h.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
                if remaining <= 0:
                    break
    return h.hexdigest()


def read_frames(src: str | Path, start: float, duration: float, fps: float, width: int,
                height: int | None = None, timeout: float = 3600):
    """Yield RGB frames (H, W, 3 uint8) decoded by ffmpeg at a fixed fps and size.

    ``height`` None keeps aspect ratio (rounded to even)."""
    if height is None:
        info = media_info(src)
        sw, sh = info.get("width") or 16, info.get("height") or 9
        height = int(round(width * sh / sw / 2) * 2)
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-i", str(src),
           "-t", f"{duration:.3f}", "-an", "-vf", f"fps={fps},scale={width}:{height}:flags=area",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    frame_bytes = width * height * 3
    try:
        assert proc.stdout is not None
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 3)
    finally:
        if proc.stdout:
            proc.stdout.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
