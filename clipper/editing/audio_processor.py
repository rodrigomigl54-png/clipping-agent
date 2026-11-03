"""Audio processing filter chain: high-pass, EBU R128 loudness normalisation, edge fades."""
from __future__ import annotations


def audio_filter(cfg: dict, duration: float) -> str:
    parts = []
    hp = cfg.get("highpass_hz")
    if hp:
        parts.append(f"highpass=f={int(hp)}")
    if cfg.get("loudnorm", True):
        parts.append(f"loudnorm=I={cfg.get('target_lufs', -14)}:TP={cfg.get('true_peak', -1.5)}:"
                     f"LRA={cfg.get('lra', 11)}")
    parts.append("afade=t=in:st=0:d=0.05")
    parts.append(f"afade=t=out:st={max(0.0, duration - 0.08):.3f}:d=0.08")
    return ",".join(parts)
