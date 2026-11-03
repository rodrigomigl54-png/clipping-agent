"""FFmpeg renderer.

Decoder ffmpeg → numpy frame composition (layout, crop, zoom, gameplay panel) → encoder ffmpeg,
which also burns the ASS captions and processes/muxes the source audio in the same pass.
Output: 1080x1920 H.264 (yuv420p) + AAC MP4 with faststart.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..core.media import MediaError, media_info, read_frames
from ..core.logger import get_logger
from .audio_processor import audio_filter
from .layout_engine import LayoutPlan, compose

log = get_logger("renderer")


def _ass_filter(ass_path: Path, fonts_dir: Path | None) -> str:
    p = str(ass_path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    f = f"ass='{p}'"
    if fonts_dir and fonts_dir.exists() and any(fonts_dir.iterdir()):
        fd = str(fonts_dir).replace(":", "\\:").replace("'", "\\'")
        f += f":fontsdir='{fd}'"
    return f


def render(src: str | Path, start: float, end: float, plan: LayoutPlan, out_path: Path, *,
           output_cfg: dict, audio_cfg: dict, ass_path: Path | None = None, gameplay: str | Path | None = None,
           gameplay_offset: float = 0.0, fonts_dir: Path | None = None, timeout: float = 3600) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = end - start
    fps = float(output_cfg.get("fps", 30))
    W, H = plan.out_w, plan.out_h
    info = media_info(src)
    sw, sh = info["width"], info["height"]
    work_w = min(sw, 1920)
    work_h = int(round(sh * work_w / sw / 2) * 2)

    vf = [] if ass_path is None else [_ass_filter(ass_path, fonts_dir)]
    vf.append(f"format={output_cfg.get('pix_fmt', 'yuv420p')}")
    tmp = out_path.with_suffix(".rendering.mp4")
    enc = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", f"{fps}", "-i", "pipe:0",
           "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src),
           "-map", "0:v:0", "-map", "1:a:0",
           "-vf", ",".join(vf),
           "-af", audio_filter(audio_cfg, duration), "-ar", str(output_cfg.get("audio_sample_rate", 48000)),
           "-c:v", output_cfg.get("video_codec", "libx264"), "-preset", output_cfg.get("preset", "medium"),
           "-crf", str(output_cfg.get("crf", 20)), "-profile:v", "high",
           "-c:a", output_cfg.get("audio_codec", "aac"), "-b:a", output_cfg.get("audio_bitrate", "160k"),
           "-ac", "2", "-movflags", "+faststart", "-t", f"{duration:.3f}", str(tmp)]
    proc = subprocess.Popen(enc, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    gp_iter = None
    if plan.needs_gameplay:
        if not gameplay:
            proc.kill()
            raise MediaError("layout needs a licensed gameplay asset but none was provided")
        gp_iter = _gameplay_frames(gameplay, gameplay_offset, duration, fps)
    n = 0
    try:
        assert proc.stdin is not None
        for fr in read_frames(src, start, duration, fps, work_w, work_h, timeout=timeout):
            t = n / fps
            gp = next(gp_iter) if gp_iter is not None else None
            proc.stdin.write(compose(fr, plan, t, gp).tobytes())
            n += 1
        proc.stdin.close()
        _, err = proc.communicate(timeout=timeout)
    except BrokenPipeError:
        _, err = proc.communicate(timeout=60)
    except BaseException:
        proc.kill()
        tmp.unlink(missing_ok=True)
        raise
    if proc.returncode != 0 or n == 0:
        tmp.unlink(missing_ok=True)
        raise MediaError(f"render failed (frames={n}, rc={proc.returncode}): "
                         f"{(err or b'').decode('utf-8', 'replace')[-1500:]}")
    tmp.replace(out_path)
    return out_path


def _gameplay_frames(path, offset: float, duration: float, fps: float):
    """Loop the licensed gameplay clip for as long as needed."""
    info = media_info(path)
    gd = max(0.5, info["duration"])
    w = min(1280, info["width"])
    t = offset % gd
    produced = 0
    need = int(duration * fps) + 2
    while produced < need:
        got = 0
        for fr in read_frames(path, t, min(gd - t, (need - produced) / fps + 1), fps, w):
            yield fr
            got += 1
            produced += 1
            if produced >= need:
                return
        t = 0.0
        if got == 0:
            raise MediaError(f"could not decode gameplay asset {path}")
