"""Daily content plan: turn today's trend research + the learned playbook into concrete video slots.

No AI calls. Each slot says what to make (type, series, topic), from what (source to find), how (format
from the style library, hook/headline template from real top performers, target length, trending sound
to cut to) and that it is produced in two variants (A/B) so real results can pick the better approach.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PRIORS = {"streamer_clip": 0.30, "hype_edit": 0.30, "meme_skit": 0.15, "fun_fact": 0.13, "news": 0.12}
PHASE_BOOST = {  # before release there is no gameplay yet; after release streamers flood the feed
    "pre_release": {"hype_edit": 1.4, "news": 1.3, "fun_fact": 1.3, "streamer_clip": 0.8, "meme_skit": 1.0},
    "launch_week": {"streamer_clip": 1.6, "meme_skit": 1.2, "hype_edit": 0.8, "news": 0.9, "fun_fact": 0.9},
    "post_launch": {"streamer_clip": 1.3, "fun_fact": 1.2, "meme_skit": 1.1, "hype_edit": 0.8, "news": 0.8},
}
TYPE_TO_CATEGORY = {"streamer_clip": "streamer_reaction", "hype_edit": "hype_edit", "meme_skit": "meme_skit",
                    "fun_fact": "fun_fact", "news": "news_trailer"}
SERIES = {
    "hype_edit": "Countdown edit — '{days} DAYS' (daily until release), then 'GTA 6 edit of the day'",
    "fun_fact": "Detail of the day — one detail you missed (zoom + circle)",
    "streamer_clip": "Streamer moment of the day",
    "meme_skit": "POV: GTA 6 … (series of POV memes)",
    "news": "GTA 6 news in 15 seconds",
}
SOURCE_HINT = {
    "hype_edit": "newest official trailer / features trailer footage (highest resolution available) + best "
                 "shots from previous trailers",
    "fun_fact": "official trailer frames where a small detail is visible; or a comparison pair (GTA 6 vs real place)",
    "streamer_clip": "VODs/clips of the streamers trending right now on the topic",
    "meme_skit": "gameplay/trailer footage that fits the joke; letterbox + top headline format",
    "news": "the announcement itself (trailer, post, screenshot) — lead with the payoff in the first second",
}


def phase(today: date, release: date | None) -> tuple[str, int | None]:
    if not release:
        return "pre_release", None
    d = (release - today).days
    if d > 0:
        return "pre_release", d
    return ("launch_week" if d > -7 else "post_launch"), d


def make_plan(summary: dict, *, n: int = 12, release: date | None = None, headlines: dict[str, list[str]] | None = None,
              duration_targets: dict | None = None, today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc).date()
    ph, days = phase(today, release)
    types = summary.get("types", {})
    # observed strength: velocity x engagement, normalised; blended with priors and the phase
    raw = {}
    for t, prior in PRIORS.items():
        st = types.get(t)
        obs = (st["median_velocity"] * (1 + 10 * st["median_engagement"])) if st else 0.0
        raw[t] = obs
    top = max(raw.values()) or 1.0
    weight = {t: (0.5 * PRIORS[t] + 0.5 * (raw[t] / top) * 0.3) * PHASE_BOOST[ph].get(t, 1.0) for t in PRIORS}
    total = sum(weight.values())
    alloc = {t: max(1, round(n * w / total)) for t, w in weight.items()}
    while sum(alloc.values()) > n:
        k = max(alloc, key=lambda t: alloc[t] - n * weight[t] / total)
        alloc[k] -= 1
    while sum(alloc.values()) < n:
        k = max(alloc, key=lambda t: n * weight[t] / total - alloc[t])
        alloc[k] += 1

    topics = [t for t, _ in summary.get("topics", []) if len(t) > 3]
    events = [e["title"] for e in summary.get("events", [])]
    # angles taken from the fastest videos' captions (what people are reacting to right now), per type
    angles_by_type: dict[str, list[str]] = {}
    for v in summary.get("top_tiktok", []):
        cap = re.sub(r"#\w+|@\w+", "", v.get("desc") or "").split("|")[0].strip(" .!🔥😭🐐😍")
        lst = angles_by_type.setdefault(v["type"], [])
        if 8 <= len(cap) <= 70 and cap.lower() not in [a.lower() for a in lst]:
            lst.append(cap)
    all_angles = [a for lst in angles_by_type.values() for a in lst]
    sounds_by_type: dict[str, list[dict]] = {}
    for s in summary.get("sounds", []):
        for t in s.get("types", {}):
            sounds_by_type.setdefault(t, []).append(s)
    inspiration: dict[str, list[dict]] = {}
    for v in summary.get("top_tiktok", []):
        inspiration.setdefault(v["type"], []).append(v)

    slots, used_topics = [], set()
    order = sorted(alloc, key=lambda t: -weight[t])
    for t in order:
        for i in range(alloc[t]):
            own = angles_by_type.get(t, [])
            pool = (events + own + topics) if t in ("news", "fun_fact") else (own + all_angles + events + topics)
            topic = next((x for x in pool if x not in used_topics), None)
            if topic:
                used_topics.add(topic)
            cat = TYPE_TO_CATEGORY[t]
            tgt = (duration_targets or {}).get(cat) or (duration_targets or {}).get("*")
            snd = (sounds_by_type.get(t) or [None])[i % max(1, len(sounds_by_type.get(t) or [None]))]
            insp = (inspiration.get(t) or [])[i:i + 1]
            series = SERIES[t].format(days=days if days and days > 0 else "")
            slots.append({
                "slot": len(slots) + 1, "type": t, "category": cat, "series": series, "topic": topic,
                "source_to_find": SOURCE_HINT[t],
                "headline_style": (headlines or {}).get(cat, [])[:3],
                "target_length_s": round(tgt["median"]) if tgt else None,
                "sound": ({"title": snd["title"], "author": snd["author"],
                           "why": f"trending now on {snd['videos']} {t.replace('_', ' ')} video(s)"} if snd else
                          ("original audio (stream sound)" if t == "streamer_clip" else "pick a trending sound")),
                "inspiration": [{"url": v["url"], "views": v["views"], "velocity_per_h": v["velocity"]} for v in insp],
                "variants": ["A: headline style 1 / format from the best example",
                             "B: different hook (question or bold claim) / alternative format"],
                "hook_rule": "first 2 s must show motion or a bold line + the headline; otherwise not exported",
            })
    return {"date": today.isoformat(), "phase": ph, "days_to_release": days, "videos": len(slots),
            "allocation": alloc, "slots": slots,
            "adjacent_trends": summary.get("adjacent_trends", {}).get("topics", [])[:5]}


def save_plan(plan: dict, memory_dir: Path) -> Path:
    p = Path(memory_dir) / "plans" / f"plan_{plan['date']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(plan, indent=1, ensure_ascii=False))
    return p
