"""Per-profile performance analytics.

Profiles are analysed separately. Within a profile, raw views are normalised by the profile
median so clips are compared to their own audience, never across unrelated audiences.
AI potential scores and real platform performance are reported side by side, never mixed.
"""
from __future__ import annotations

import math
from statistics import mean, median

from ..core.database import Database

METRICS = ("views", "avg_view_duration", "avg_pct_viewed", "completion_rate", "shares", "comments",
           "likes", "rewatches", "follows")


def length_bucket(sec: float | None) -> str:
    if sec is None:
        return "unknown"
    return "15-30s" if sec < 30 else "30-60s" if sec < 60 else "60-120s" if sec < 120 else "120-180s"


def per_k(n, views):
    return None if n is None or not views else 1000.0 * n / views


def rows(db: Database, profile: str) -> list[dict]:
    out = db.query("SELECT * FROM performance WHERE profile=?", (profile,))
    views = [r["views"] for r in out if r["views"]]
    med = median(views) if views else None
    pct = [r["avg_pct_viewed"] for r in out if r["avg_pct_viewed"] is not None]
    med_pct = median(pct) if pct else None
    for r in out:
        r["length_bucket"] = length_bucket(r["video_length"])
        r["views_index"] = (r["views"] / med) if (med and r["views"] is not None) else None
        r["retention_index"] = (r["avg_pct_viewed"] / med_pct) if (med_pct and r["avg_pct_viewed"] is not None) else None
        r["shares_per_k"] = per_k(r["shares"], r["views"])
        r["comments_per_k"] = per_k(r["comments"], r["views"])
        r["follows_per_k"] = per_k(r["follows"], r["views"])
    return out


def _agg(vals):
    v = [x for x in vals if x is not None]
    if not v:
        return None
    return round(mean(v), 3)


def summarize(db: Database, profile: str, by: str) -> list[dict]:
    data = rows(db, profile)
    groups: dict[str, list[dict]] = {}
    for r in data:
        keys = [k.strip() for k in (r.get(by) or "unknown").split(",")] if by == "creator" else [r.get(by) or "unknown"]
        for k in keys:
            groups.setdefault(str(k), []).append(r)
    out = []
    for k, g in groups.items():
        out.append({by: k, "n": len(g),
                    "avg_pct_viewed": _agg(r["avg_pct_viewed"] for r in g),
                    "avg_view_duration": _agg(r["avg_view_duration"] for r in g),
                    "completion_rate": _agg(r["completion_rate"] for r in g),
                    "retention_index": _agg(r["retention_index"] for r in g),
                    "views_index": _agg(r["views_index"] for r in g),
                    "shares_per_k": _agg(r["shares_per_k"] for r in g),
                    "follows_per_k": _agg(r["follows_per_k"] for r in g),
                    "avg_candidate_score": _agg(r["candidate_score"] for r in g)})
    return sorted(out, key=lambda x: -(x["retention_index"] or 0))


def overview(db: Database, profile: str) -> dict:
    data = rows(db, profile)
    return {"profile": profile, "clips_with_data": len(data),
            "metrics_available": {m: sum(1 for r in data if r[m] is not None) for m in METRICS},
            "median_views": median([r["views"] for r in data if r["views"]]) if any(r["views"] for r in data) else None,
            "by_format": summarize(db, profile, "format"), "by_length": summarize(db, profile, "length_bucket"),
            "by_hook_type": summarize(db, profile, "hook_type"), "by_topic": summarize(db, profile, "topic"),
            "by_creator": summarize(db, profile, "creator"),
            "score_vs_retention_spearman": spearman([(r["candidate_score"], r["avg_pct_viewed"]) for r in data])}


def spearman(pairs) -> float | None:
    p = [(a, b) for a, b in pairs if a is not None and b is not None]
    if len(p) < 5:
        return None
    def ranks(xs):
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    ra, rb = ranks([a for a, _ in p]), ranks([b for _, b in p])
    ma, mb = mean(ra), mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return round(num / den, 3) if den else None
