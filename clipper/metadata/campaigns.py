"""Which joined clipping campaigns a clip qualifies for, and the caption those campaigns require.

A clip has one primary streamer (the main focus) and a list of everyone in it. Campaign rules come from
config/campaigns.yaml (read from the campaign pages). This only decides eligibility and text; the owner posts
and submits the links.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

CFG = Path(__file__).resolve().parents[2] / "config" / "campaigns.yaml"
_ALIAS = {"kai": "Kai Cenat", "kaicenat": "Kai Cenat", "kai cenat": "Kai Cenat", "jason": "JasonTheWeen",
          "jasontheween": "JasonTheWeen", "lacy": "Lacy", "silky": "Silky", "stable": "StableRonaldo",
          "stableronaldo": "StableRonaldo", "stable ronaldo": "StableRonaldo", "adapt": "Adapt"}


def load(path: Path = CFG) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def norm(name: str) -> str:
    return _ALIAS.get(name.strip().lower(), name.strip())


def tag(name: str) -> str:
    return "#" + re.sub(r"[^A-Za-z0-9]", "", norm(name))


def eligible(primary: str, present: list[str], *, source: str = "stream", gta6: bool = True,
             cfg: dict | None = None) -> list[str]:
    """Campaign keys this clip can be submitted to.

    source: "stream" (Twitch/YouTube stream or VOD), "core_yt" (a video from the CORE YouTube channel) or "other".
    """
    cfg = cfg or load()
    primary = norm(primary)
    people = {norm(p) for p in present} | {primary}
    members = set(cfg.get("core_members", []))
    out = []
    for key, c in cfg["campaigns"].items():
        if c.get("gta6_only") and not gta6:
            continue
        if key == "core_yt":
            ok = source == "core_yt" and bool(people & members)
        elif key == "core":
            ok = source != "core_yt" and len(people & members) >= c.get("min_core_members", 2)
        else:
            ok = c.get("primary") == primary
        if ok:
            out.append(key)
    return out


def caption(text: str, primary: str, present: list[str], keys: list[str], *, extra: list[str] | None = None,
            cfg: dict | None = None) -> str:
    """Caption with the streamer's name and every hashtag the chosen campaigns require."""
    cfg = cfg or load()
    members = set(cfg.get("core_members", []))
    people = [norm(primary)] + [norm(p) for p in present if norm(p) != norm(primary)]
    tags: list[str] = []
    for k in keys:
        tags += cfg["campaigns"][k].get("hashtags", [])
        if k in ("core", "core_yt"):
            tags += [tag(p) for p in people if p in members]
    tags += [tag(p) for p in people]
    tags += extra or []
    seen, uniq = set(), []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)
    body = text.strip()
    if norm(primary).lower() not in body.lower():
        body = f"{norm(primary)}: {body}"
    return f"{body} {' '.join(uniq)}".strip()


def problems(on_screen: str, caption_text: str, keys: list[str], primary: str, cfg: dict | None = None) -> list[str]:
    """Rule checks a post must pass before it is handed to the owner."""
    cfg = cfg or load()
    out = []
    if norm(primary).lower() not in on_screen.lower():
        out.append(f"on-screen text does not name {norm(primary)}")
    for k in keys:
        for h in cfg["campaigns"][k].get("hashtags", []):
            if h.lower() not in caption_text.lower():
                out.append(f"{k}: caption is missing {h}")
    if re.search(r"[čćšžđČĆŠŽĐЀ-ӿ぀-ヿ]", on_screen + caption_text):
        out.append("non-English characters in the text")
    return out
