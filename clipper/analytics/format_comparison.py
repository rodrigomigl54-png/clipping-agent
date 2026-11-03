"""LosPollosTV Format A/B/C comparison with length adjustment and sample-size gating."""
from __future__ import annotations

import math
from statistics import mean, stdev

from ..config import Settings
from ..core.database import Database, dumps, now_iso
from .analytics_engine import rows

COMPARE = ("avg_pct_viewed", "avg_view_duration", "completion_rate", "shares_per_k", "comments_per_k",
           "follows_per_k", "rewatches")


def _linfit(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    return my - b * mx, b


def compare_formats(db: Database, settings: Settings, profile: str = "lospollostv", record: bool = True) -> dict:
    fe = settings.profile(profile).format_experiment
    data = [r for r in rows(db, profile) if r.get("format")]
    primary = fe.primary_metric
    # length adjustment: residual of the primary metric after a linear fit on video length
    pts = [(r["video_length"], r[primary]) for r in data if r["video_length"] is not None and r[primary] is not None]
    a, b = _linfit([p[0] for p in pts], [p[1] for p in pts]) if len(pts) >= 3 else (None, None)
    by: dict[str, list[dict]] = {}
    for r in data:
        if a is not None and r["video_length"] is not None and r[primary] is not None:
            r["adjusted"] = r[primary] - (a + b * r["video_length"])
        else:
            r["adjusted"] = None
        by.setdefault(r["format"], []).append(r)
    table = {}
    for f in sorted(fe.formats):
        g = by.get(f, [])
        stats = {"n": len(g)}
        for m in COMPARE + ("adjusted",):
            v = [r[m] for r in g if r.get(m) is not None]
            stats[m] = round(mean(v), 3) if v else None
            if m == "adjusted":
                stats["adjusted_se"] = round(stdev(v) / math.sqrt(len(v)), 3) if len(v) >= 2 else None
        table[f] = stats
    need = fe.min_samples_per_format
    enough = all(table[f]["n"] >= need for f in table) and len(table) >= 2
    verdict = {"status": "insufficient_data",
               "message": f"Need ≥{need} published clips with data per format "
                          f"(have {', '.join(f'{f}={table[f]['n']}' for f in table)})."}
    if enough:
        ranked = sorted(table, key=lambda f: -(table[f]["adjusted"] if table[f]["adjusted"] is not None else -1e9))
        best, second = ranked[0], ranked[1]
        bse, sse = table[best]["adjusted_se"] or 0, table[second]["adjusted_se"] or 0
        diff = (table[best]["adjusted"] or 0) - (table[second]["adjusted"] or 0)
        z = diff / math.sqrt(bse ** 2 + sse ** 2) if (bse or sse) else 0
        if z >= 2:
            verdict = {"status": "recommend", "format": best,
                       "message": f"Format {best} leads on length-adjusted {primary} by {diff:.2f} pts (z={z:.1f}) "
                                  f"over Format {second}. Check shares/follows before switching."}
        else:
            verdict = {"status": "no_clear_winner",
                       "message": f"Format {best} is ahead by {diff:.2f} pts (z={z:.1f}) — not yet conclusive."}
    out = {"profile": profile, "primary_metric": primary, "length_fit": {"intercept": a, "slope": b},
           "formats": table, "verdict": verdict,
           "caveats": ["Topic, publish time and audience differences are not fully controlled.",
                       "Views alone are not used; metrics are imported manually and may be incomplete."]}
    if record and verdict["status"] == "recommend":
        exists = db.one("SELECT id FROM recommendations WHERE profile=? AND kind='format_choice' AND status='pending'",
                        (profile,))
        if not exists:
            db.insert("recommendations", {"profile": profile, "kind": "format_choice", "description": verdict["message"],
                                          "evidence": dumps(table), "proposed_change": dumps({"preferred_format": verdict["format"]}),
                                          "status": "pending", "created_at": now_iso()})
    return out
