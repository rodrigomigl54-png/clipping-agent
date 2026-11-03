"""Technical QC on the rendered file."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..core.media import MediaError, media_info, run


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""
    severity: str = "fail"          # fail | review | warn

    def to_dict(self):
        return {"name": self.name, "passed": self.passed, "detail": self.detail, "severity": self.severity}


@dataclass
class CheckReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "", severity: str = "fail") -> None:
        self.checks.append(Check(name, bool(passed), detail, severity))

    def failed(self, severity: str | None = None) -> list[Check]:
        return [c for c in self.checks if not c.passed and (severity is None or c.severity == severity)]

    @property
    def pass_ratio(self) -> float:
        return sum(c.passed for c in self.checks) / len(self.checks) if self.checks else 0.0


def scan_signal(path: Path, black_d: float, noise_db: float, timeout: float = 1800) -> dict:
    proc = run(["ffmpeg", "-hide_banner", "-nostats", "-v", "info", "-i", str(path),
                "-vf", f"blackdetect=d={black_d}:pix_th=0.10", "-af", f"silencedetect=n={noise_db}dB:d=1.0",
                "-f", "null", "-"], timeout=timeout, check=False)
    err = proc.stderr.decode("utf-8", "replace")
    black = sum(float(m) for m in re.findall(r"black_duration:\s*([\d.]+)", err))
    silence = sum(float(m) for m in re.findall(r"silence_duration:\s*([\d.]+)", err))
    # silence still open at EOF has a start but no duration
    starts = re.findall(r"silence_start:\s*([\d.]+)", err)
    ends = re.findall(r"silence_end:\s*([\d.]+)", err)
    decode_errors = [l for l in err.splitlines() if re.search(r"(?i)(corrupt|invalid data|error while decoding|non-existing)", l)]
    return {"black": black, "silence": silence, "open_silence_start": float(starts[-1]) if len(starts) > len(ends) else None,
            "decode_errors": decode_errors[:5], "returncode": proc.returncode}


def technical_checks(path: Path, *, cfg: dict, min_dur: float, max_dur: float, caption_report=None,
                     caption_size: int = 72, speech_expected: bool = True) -> tuple[CheckReport, dict]:
    rep = CheckReport()
    if not path.exists() or path.stat().st_size == 0:
        rep.add("file_exists", False, f"{path} missing or empty")
        return rep, {}
    rep.add("file_exists", True, f"{path.stat().st_size / 1e6:.1f} MB")
    try:
        info = media_info(path)
    except MediaError as e:
        rep.add("playable", False, f"ffprobe failed: {e}")
        return rep, {}
    rep.add("has_video", info.get("has_video"), info.get("video_codec") or "none")
    rep.add("has_audio", info.get("has_audio"), info.get("audio_codec") or "none")
    if not info.get("has_video"):
        return rep, info
    w, h = info["width"], info["height"]
    rep.add("resolution", (w, h) == (cfg["expected_width"], cfg["expected_height"]), f"{w}x{h}")
    aspect = w / h if h else 0
    rep.add("aspect_ratio", abs(aspect - 9 / 16) <= cfg.get("aspect_tolerance", 0.01), f"{aspect:.4f}")
    rep.add("codecs", info.get("video_codec") == "h264" and info.get("audio_codec") == "aac"
            and info.get("pix_fmt") == "yuv420p", f"{info.get('video_codec')}/{info.get('audio_codec')}/{info.get('pix_fmt')}")
    d = info["duration"]
    rep.add("duration_limits", min_dur - 0.5 <= d <= max_dur + 0.5, f"{d:.2f}s (limits {min_dur}-{max_dur})")
    if info.get("has_audio"):
        diff = abs(info.get("video_duration", d) - info.get("audio_duration", d))
        rep.add("av_sync", diff <= cfg.get("max_av_duration_diff", 0.25), f"stream duration diff {diff:.3f}s")
    kbps = info.get("bit_rate", 0) / 1000
    rep.add("bitrate", kbps >= cfg.get("min_bitrate_kbps", 400), f"{kbps:.0f} kbps", "review")
    sig = scan_signal(path, cfg.get("black_min_duration", 1.0), cfg.get("silence_noise_db", -45))
    rep.add("decodes_cleanly", sig["returncode"] == 0 and not sig["decode_errors"],
            "; ".join(sig["decode_errors"]) or "full decode OK")
    bf = sig["black"] / d if d else 1
    rep.add("no_black_screen", bf <= cfg.get("max_black_fraction", 0.15), f"black {bf:.0%}")
    silence = sig["silence"] + ((d - sig["open_silence_start"]) if sig["open_silence_start"] is not None else 0)
    sf = silence / d if d else 1
    rep.add("no_empty_sections", sf <= cfg.get("max_silence_fraction", 0.5), f"silence {sf:.0%}")
    if caption_report is not None:
        has = caption_report.chunks > 0
        rep.add("captions_present", has or not speech_expected, f"{caption_report.chunks} caption chunks")
        rep.add("captions_readable", caption_size >= 48, f"font size {caption_size}px @ {h}p", "review")
    return rep, {**info, "signal": sig}
