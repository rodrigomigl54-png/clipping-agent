"""Descriptions: what happens (from the transcript), source + timestamp, attribution, hashtags."""
from __future__ import annotations


def fmt_ts(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def description(summary: str, source: dict, start: float, end: float, attribution: list[str],
                tags: list[str]) -> str:
    lines = [summary.strip()] if summary else []
    src_title = source.get("title") or "original stream"
    ref = f"From: {src_title} ({fmt_ts(start)}–{fmt_ts(end)})"
    if source.get("url"):
        ref += f" {source['url']}"
    lines.append(ref)
    lines += attribution
    lines.append(" ".join(tags))
    return "\n\n".join(l for l in lines if l)
