"""Dynamic research-attention allocation per creator.

Initial priorities come from the profile YAML. Multipliers adapt (within configured bounds) to the
quality of candidate moments found and, when available, real imported performance. These are
attention weights only — never clip quotas. Every adjustment is recorded in ``attention``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..config import Settings
from ..core.database import Database, loads, now_iso


class AttentionAllocator:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings

    def multiplier(self, profile: str, creator: str) -> float:
        r = self.db.one("SELECT multiplier FROM attention WHERE profile=? AND creator=?", (profile, creator))
        return float(r["multiplier"]) if r else 1.0

    def weights(self, profile: str) -> dict[str, float]:
        prof = self.settings.profile(profile)
        raw = {c.name: c.initial_weight * self.multiplier(profile, c.name) for c in prof.creators}
        total = sum(raw.values()) or 1.0
        return {k: v / total for k, v in raw.items()}

    def allocate(self, profile: str, budget: int) -> dict[str, int]:
        """Split a research budget (e.g. number of leads to pursue) by attention weight.
        Every creator keeps at least 1 slot so nobody is starved of discovery."""
        w = self.weights(profile)
        alloc = {k: max(1, round(v * budget)) for k, v in w.items()}
        return dict(sorted(alloc.items(), key=lambda kv: -w[kv[0]]))

    def update_from_evidence(self, profile: str) -> dict[str, float]:
        prof = self.settings.profile(profile)
        if not prof.attention.dynamic:
            return {}
        days = self.settings.global_.research.window_days
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self.db.query("SELECT participants, total_score FROM candidates WHERE profile=? AND created_at>=?",
                             (profile, cutoff))
        per: dict[str, list[float]] = {}
        for r in rows:
            for p in loads(r["participants"], []):
                per.setdefault(p, []).append(float(r["total_score"] or 0))
        perf = self.db.query("SELECT creator, avg_pct_viewed FROM performance WHERE profile=? "
                             "AND avg_pct_viewed IS NOT NULL", (profile,))
        perf_by: dict[str, list[float]] = {}
        for r in perf:
            if r["creator"]:
                perf_by.setdefault(r["creator"], []).append(float(r["avg_pct_viewed"]))
        all_scores = [s for v in per.values() for s in v]
        if len(all_scores) < 5:
            return {}
        mean_all = sum(all_scores) / len(all_scores)
        all_perf = [x for v in perf_by.values() for x in v]
        mean_perf = sum(all_perf) / len(all_perf) if all_perf else None
        changes = {}
        a = prof.attention
        for c in prof.creators:
            scores = per.get(c.name, [])
            if len(scores) < 3:
                continue
            ratio = (sum(scores) / len(scores)) / (mean_all or 1)
            pr = perf_by.get(c.name, [])
            if mean_perf and len(pr) >= 3:
                ratio = 0.5 * ratio + 0.5 * (sum(pr) / len(pr)) / mean_perf
            old = self.multiplier(profile, c.name)
            new = min(a.max_multiplier, max(a.min_multiplier, old + a.learning_rate * (ratio - 1)))
            if abs(new - old) >= 0.01:
                reason = (f"candidate-score ratio {ratio:.2f} over {len(scores)} candidates"
                          + (f", performance n={len(pr)}" if pr else ""))
                self.db.execute(
                    "INSERT INTO attention(profile,creator,multiplier,reason,updated_at) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(profile,creator) DO UPDATE SET multiplier=excluded.multiplier, "
                    "reason=excluded.reason, updated_at=excluded.updated_at",
                    (profile, c.name, round(new, 3), reason, now_iso()))
                changes[c.name] = round(new, 3)
        return changes
