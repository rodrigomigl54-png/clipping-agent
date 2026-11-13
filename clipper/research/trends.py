"""Trend research (free, no AI quota): what is going viral right now on TikTok (primary) and YouTube.

Sources — public pages only, plain GETs, no logins, no signed/private APIs:
* TikTok creator embed (the official "embed a profile" widget): latest videos of a creator with views.
* TikTok public video page: exact stats (views, likes, shares, saves, comments), post time, sound, size.
* YouTube search results page (this-week filter): fresh videos for a query with views and age.

From these we compute *velocity* (views per hour since posting), engagement and share rates, and an
*outlier score* (views vs the creator's own median) — the signals that something is breaking out now —
then aggregate topics, content types and sounds, and turn them into a ranked daily content plan.
Everything is written to ``memory/research/`` (committed to the repo) so the machine keeps learning.
"""
from __future__ import annotations

import json
import re
import statistics
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.logger import get_logger

log = get_logger("trends")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

TYPE_RULES = [
    ("hype_edit", ["edit", "phonk", "4k", "60fps", "cinematic", "velocity", "#edit", "aftereffects", "ae"]),
    ("meme_skit", ["meme", "pov", "reportedly", "what if", "when you", "be like", "nobody:", "💀", "😭", "funny"]),
    ("streamer_clip", ["stream", "kai", "cenat", "agent", "duke", "fanum", "lacy", "adapt", "xqc", "ishowspeed",
                       "speed", "jynxzi", "clip", "reacts", "reaction", "live"]),
    ("news", ["trailer", "leak", "leaked", "release", "date", "official", "confirmed", "rockstar", "price",
              "preorder", "pre-order", "news", "update", "screenshot"]),
    ("fun_fact", ["detail", "details", "did you know", "easter egg", "secret", "hidden", "missed", "vs", "comparison",
                  "real life", "map"]),
]
NICHE_WORDS = ["gta", "gta6", "gtavi", "grand theft auto", "vice city", "leonida", "lucia", "jason", "rockstar"]


def on_topic(text: str, niche: list[str] = NICHE_WORDS) -> bool:
    t = (text or "").lower()
    return any(w in t for w in niche)


STOP = set("the a an and or of to in on for is it this that with you your i me my we our be are was at as by from "
           "gta gta6 gta5 gtavi gtav gta6edit grandtheftauto6 grandtheftauto fyp foryou foryoupage viral trending "
           "6 vi 5 v x so just like grand theft auto games game rockstar rockstargames now new edit edits trailer "
           "gta6trailer gtavitrailer gta6edit shorts reels capcut ps5 xbox playstation official".split())
OFFICIAL_CHANNELS = ("rockstar games", "playstation", "xbox", "youtube", "ign", "gamespot")


def _get(url: str, timeout: float = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def classify(desc: str, known_type: str | None = None) -> str:
    if known_type:
        return known_type
    d = (desc or "").lower()
    scores = {t: sum(1 for w in words if w in d) for t, words in TYPE_RULES}
    best = max(scores, key=scores.get)
    return best if scores[best] else "other"


def topics(desc: str) -> list[str]:
    """Hashtags (minus generic ones) + meaningful 1-2 word phrases from the caption."""
    d = (desc or "").lower()
    tags = [t for t in re.findall(r"#(\w+)", d) if t not in STOP and len(t) > 2]
    words = [w for w in re.findall(r"[a-z][a-z']+", re.sub(r"#\w+", " ", d)) if w not in STOP and len(w) > 2]
    bigrams = [f"{a} {b}" for a, b in zip(words, words[1:]) if a not in STOP and b not in STOP]
    return list(dict.fromkeys(tags + words + bigrams))


# ----------------------------------------------------------------------------- sources
class TikTokPublic:
    def __init__(self, delay: float = 1.5, fetch=None):
        self.delay = delay
        self.fetch = fetch or _get

    def creator_videos(self, handle: str) -> list[dict]:
        h = self.fetch(f"https://www.tiktok.com/embed/@{handle.lstrip('@')}")
        m = re.search(r'<script id="__FRONTITY_CONNECT_STATE__"[^>]*>(.*?)</script>', h, re.S)
        if not m:
            return []
        data = json.loads(m.group(1))
        for key, val in (data.get("source", {}).get("data", {}) or {}).items():
            if isinstance(val, dict) and isinstance(val.get("videoList"), list):
                return [{"id": v.get("id"), "desc": v.get("desc"), "views": v.get("playCount"),
                         "author": v.get("authorUniqueId") or handle.lstrip("@"), "w": v.get("width"),
                         "h": v.get("height")} for v in val["videoList"] if v.get("id")]
        return []

    def video(self, handle: str, vid: str) -> dict | None:
        h = self.fetch(f"https://www.tiktok.com/@{handle.lstrip('@')}/video/{vid}")
        m = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>', h, re.S)
        if not m:
            return None
        it = (json.loads(m.group(1)).get("__DEFAULT_SCOPE__", {}).get("webapp.video-detail", {})
              .get("itemInfo", {}).get("itemStruct"))
        if not it or not it.get("id"):
            return None
        st, mu, v = it.get("stats") or {}, it.get("music") or {}, it.get("video") or {}
        return {"id": it["id"], "author": (it.get("author") or {}).get("uniqueId") or handle, "desc": it.get("desc"),
                "created": int(it.get("createTime") or 0), "duration": v.get("duration"), "w": v.get("width"),
                "h": v.get("height"), "views": int(st.get("playCount") or 0), "likes": int(st.get("diggCount") or 0),
                "comments": int(st.get("commentCount") or 0), "shares": int(st.get("shareCount") or 0),
                "saves": int(st.get("collectCount") or 0),
                "sound": {"id": mu.get("id"), "title": mu.get("title"), "author": mu.get("authorName"),
                          "original": bool(mu.get("original"))},
                "url": f"https://www.tiktok.com/@{(it.get('author') or {}).get('uniqueId') or handle}/video/{it['id']}"}


class YouTubePublic:
    WEEK_SHORTS = "EgYIAxABGAE%253D"      # filter: this week, video type

    def __init__(self, fetch=None):
        self.fetch = fetch or _get

    @staticmethod
    def _views(text: str | None) -> int | None:
        if not text:
            return None
        t = text.lower().replace(",", "")
        m = re.search(r"([\d.]+)\s*([km]?)", t)
        if not m or "no views" in t:
            return 0 if text and "no views" in t else None
        return int(float(m.group(1)) * {"k": 1e3, "m": 1e6}.get(m.group(2), 1))

    @staticmethod
    def _age_hours(text: str | None) -> float | None:
        if not text:
            return None
        t = text.lower()
        m = re.search(r"(\d+)\s*(seconds?|sec|s|minutes?|mins?|m(?!o)|hours?|hrs?|h|days?|d|weeks?|w|months?|mo)\b", t)
        if not m:
            return None
        unit = m.group(2)
        mult = (1 / 3600 if unit.startswith("s") else 1 / 60 if unit.startswith("m") and not unit.startswith("mo")
                else 1 if unit.startswith("h") else 24 if unit.startswith("d") else 168 if unit.startswith("w") else 720)
        return int(m.group(1)) * mult

    def search(self, query: str) -> list[dict]:
        h = self.fetch(f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(query)}&sp={self.WEEK_SHORTS}")
        m = re.search(r"var ytInitialData = (\{.*?\});</script>", h, re.S)
        if not m:
            return []
        out, seen = [], set()

        def walk(o):
            if isinstance(o, dict):
                if "videoId" in o and ("title" in o or "headline" in o) and o["videoId"] not in seen:
                    t = o.get("title") or o.get("headline") or {}
                    title = t.get("simpleText") or "".join(r.get("text", "") for r in t.get("runs", []))
                    owner = "".join(r.get("text", "") for r in (o.get("ownerText") or {}).get("runs", []))
                    views = self._views((o.get("viewCountText") or {}).get("simpleText"))
                    age = self._age_hours((o.get("publishedTimeText") or {}).get("simpleText"))
                    if title:
                        seen.add(o["videoId"])
                        out.append({"id": o["videoId"], "title": title, "channel": owner, "views": views,
                                    "age_h": age, "url": f"https://www.youtube.com/watch?v={o['videoId']}"})
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(json.loads(m.group(1)))
        return out


# ----------------------------------------------------------------------------- research
@dataclass
class Snapshot:
    taken_at: str
    tiktok: list[dict] = field(default_factory=list)
    youtube: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def score_video(v: dict, now: float, creator_median: float | None) -> dict:
    age_h = max(1.0, (now - v["created"]) / 3600) if v.get("created") else None
    eng = (v["likes"] + v["comments"] + v["shares"] + v["saves"]) / v["views"] if v.get("views") else 0
    v = dict(v)
    v.update(age_h=round(age_h, 1) if age_h else None,
             velocity=round(v["views"] / age_h) if age_h else None,
             engagement=round(eng, 4), share_rate=round(v["shares"] / v["views"], 4) if v.get("views") else 0,
             outlier=round(v["views"] / creator_median, 2) if creator_median else None)
    return v


class TrendResearch:
    def __init__(self, memory_dir: Path, tiktok: TikTokPublic | None = None, youtube: YouTubePublic | None = None,
                 known_types: dict[str, str] | None = None):
        self.dir = Path(memory_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.tt = tiktok or TikTokPublic()
        self.yt = youtube or YouTubePublic()
        self.known_types = known_types or {}       # creator -> dominant content type from analysed examples
        self.cache_file = self.dir / "video_cache.json"
        self.cache: dict[str, dict] = json.loads(self.cache_file.read_text()) if self.cache_file.exists() else {}

    def run(self, handles: list[str], queries: list[str], *, max_pages_per_creator: int = 5,
            fresh_hours: float = 168, refresh_after_h: float = 6) -> Snapshot:
        now = time.time()
        snap = Snapshot(datetime.now(timezone.utc).replace(microsecond=0).isoformat())
        for handle in handles:
            try:
                listing = self.tt.creator_videos(handle)
            except Exception as e:
                snap.errors.append(f"tiktok embed @{handle}: {str(e)[:120]}")
                continue
            med = statistics.median([x["views"] for x in listing if x.get("views")]) if listing else None
            # newest videos first; only fetch details we don't have or that are stale
            for item in sorted(listing, key=lambda x: -int(x["id"]))[:max_pages_per_creator]:
                c = self.cache.get(item["id"])
                if c and now - c.get("_fetched", 0) < refresh_after_h * 3600:
                    v = c
                else:
                    try:
                        v = self.tt.video(handle, item["id"])
                        time.sleep(self.tt.delay)
                    except Exception as e:
                        snap.errors.append(f"tiktok video {item['id']}: {str(e)[:120]}")
                        continue
                    if not v:
                        continue
                    v["_fetched"] = now
                    self.cache[item["id"]] = v
                if v.get("created") and now - v["created"] > fresh_hours * 3600:
                    continue
                s = score_video(v, now, med)
                s["type"] = classify(s.get("desc"), self.known_types.get(s["author"]))
                s["topics"] = topics(s.get("desc"))
                snap.tiktok.append(s)
            time.sleep(self.tt.delay)
        for q in queries:
            try:
                for r in self.yt.search(q):
                    r["query"] = q
                    r["velocity"] = round(r["views"] / max(1.0, r["age_h"])) if r.get("views") is not None and r.get("age_h") else None
                    r["type"] = classify(r["title"])
                    r["topics"] = topics(r["title"])
                    snap.youtube.append(r)
            except Exception as e:
                snap.errors.append(f"youtube '{q}': {str(e)[:120]}")
            time.sleep(1.0)
        self.cache_file.write_text(json.dumps(self.cache, ensure_ascii=False))
        day = snap.taken_at[:10]
        (self.dir / f"snapshot_{day}.json").write_text(json.dumps(snap.__dict__, indent=1, ensure_ascii=False))
        return snap

    # ------------------------------------------------------------------ analysis
    @staticmethod
    def summarize(snap: Snapshot, top: int = 15, niche: list[str] = NICHE_WORDS) -> dict[str, Any]:
        everything = [v for v in snap.tiktok if v.get("velocity")]
        adjacent = sorted([v for v in everything if not on_topic(v.get("desc"), niche)], key=lambda v: -v["velocity"])
        tt = [v for v in everything if on_topic(v.get("desc"), niche)]
        tt.sort(key=lambda v: -(v["velocity"] or 0))
        by_type: dict[str, list] = defaultdict(list)
        for v in tt:
            by_type[v["type"]].append(v)
        types = {t: {"n": len(vs), "median_velocity": int(statistics.median([x["velocity"] for x in vs])),
                     "median_engagement": round(statistics.median([x["engagement"] for x in vs]), 4),
                     "median_share_rate": round(statistics.median([x["share_rate"] for x in vs]), 4)}
                 for t, vs in by_type.items()}
        topic_w: Counter = Counter()
        for v in tt:
            for t in v["topics"][:12]:
                topic_w[t] += v["velocity"]
        for r in snap.youtube:
            for t in r["topics"][:8]:
                topic_w[t] += (r.get("velocity") or 0) * 0.3     # YouTube counts, TikTok leads
        sounds: dict[str, dict] = {}
        for v in tt:
            s = v.get("sound") or {}
            if s.get("title") and not s.get("original"):
                k = s.get("id") or s["title"]
                e = sounds.setdefault(k, {"title": s["title"], "author": s.get("author"), "videos": 0,
                                          "velocity": 0, "types": Counter()})
                e["videos"] += 1; e["velocity"] += v["velocity"]; e["types"][v["type"]] += 1
        snd = sorted(sounds.values(), key=lambda e: -e["velocity"])
        for e in snd:
            e["types"] = dict(e["types"])
        yt = sorted([r for r in snap.youtube if r.get("velocity") and on_topic(r["title"], niche)], key=lambda r: -r["velocity"])
        events = []
        for r in yt:
            if any(c in (r.get("channel") or "").lower() for c in OFFICIAL_CHANNELS) or "official" in r["title"].lower():
                key = re.sub(r"\s*[|(].*$", "", r["title"]).strip()
                if key and key.lower() not in [e["title"].lower() for e in events]:
                    events.append({"title": key, "channel": r["channel"], "views": r["views"], "age_h": r["age_h"],
                                   "velocity": r["velocity"], "url": r["url"]})
        adj_topics: Counter = Counter()
        for v in adjacent:
            for t in v["topics"][:8]:
                adj_topics[t] += v["velocity"]
        return {"taken_at": snap.taken_at, "tiktok_videos": len(snap.tiktok), "youtube_videos": len(snap.youtube),
                "top_tiktok": [{k: v.get(k) for k in ("url", "author", "type", "views", "velocity", "age_h", "engagement",
                                                     "share_rate", "outlier", "duration", "desc")} for v in tt[:top]],
                "types": dict(sorted(types.items(), key=lambda kv: -kv[1]["median_velocity"])),
                "topics": topic_w.most_common(25), "sounds": snd[:10],
                "top_youtube": [{k: r.get(k) for k in ("url", "title", "channel", "views", "age_h", "velocity")} for r in yt[:top]],
                "events": events[:8],
                "adjacent_trends": {"topics": adj_topics.most_common(10),
                                    "top": [{k: v.get(k) for k in ("url", "author", "type", "views", "velocity", "desc")}
                                            for v in adjacent[:8]]},
                "errors": snap.errors}
