"""Controlled learning: evidence-based recommendations, never silent production changes.

Recommendations are stored as ``pending``. Only an explicit `learning apply <id>` changes config
(via local_overrides.yaml), and every applied change is written to ``config_changes``.
"""
from __future__ import annotations

from ..config import Settings, load_settings, set_override
from ..core.database import Database, dumps, loads, now_iso
from .analytics_engine import rows, spearman, summarize

MIN_SAMPLES = 8


class LearningEngine:
    def __init__(self, db: Database, settings: Settings, min_samples: int = MIN_SAMPLES):
        self.db, self.settings, self.min_samples = db, settings, min_samples

    def _add(self, profile: str, kind: str, description: str, evidence, change=None) -> int | None:
        dup = self.db.one("SELECT id FROM recommendations WHERE profile=? AND kind=? AND description=? AND status='pending'",
                          (profile, kind, description))
        if dup:
            return None
        return self.db.insert("recommendations", {"profile": profile, "kind": kind, "description": description,
                                                  "evidence": dumps(evidence), "proposed_change": dumps(change),
                                                  "status": "pending", "created_at": now_iso()})

    def analyze(self, profile: str) -> list[dict]:
        prof = self.settings.profile(profile)
        data = rows(self.db, profile)
        created = []
        with_ret = [r for r in data if r["retention_index"] is not None]
        if len(with_ret) < self.min_samples:
            return [{"info": f"only {len(with_ret)} clips with retention data; need {self.min_samples} for learning"}]
        # 1) scoring components vs. real retention
        for r in with_ret:
            c = self.db.one("SELECT k.scores FROM clips c JOIN candidates k ON k.id=c.candidate_id WHERE c.id=?",
                            (r["clip_id"],)) if r["clip_id"] else None
            r["_scores"] = loads(c["scores"], {}) if c else {}
        for comp, w in prof.scoring_weights.items():
            pairs = [(r["_scores"].get(comp), r["avg_pct_viewed"]) for r in with_ret if r["_scores"]]
            rho = spearman(pairs)
            n = sum(1 for a, b in pairs if a is not None and b is not None)
            if rho is None or n < self.min_samples:
                continue
            if rho >= 0.3:
                new = round(min(3.0, w * 1.15), 3)
                rid = self._add(profile, "scoring_weight",
                                f"Increase '{comp}' weight {w} → {new}: correlates with retention (ρ={rho}, n={n})",
                                {"rho": rho, "n": n}, {"path": ["profiles", profile, "scoring_weights", comp], "value": new})
            elif rho <= -0.3:
                new = round(max(0.1, w * 0.87), 3)
                rid = self._add(profile, "scoring_weight",
                                f"Decrease '{comp}' weight {w} → {new}: anti-correlates with retention (ρ={rho}, n={n})",
                                {"rho": rho, "n": n}, {"path": ["profiles", profile, "scoring_weights", comp], "value": new})
            else:
                continue
            if rid:
                created.append({"id": rid, "kind": "scoring_weight", "component": comp, "rho": rho})
        # 2) informational patterns (lengths, hooks, topics, creators, formats)
        for dim in ("length_bucket", "hook_type", "topic", "creator", "format"):
            groups = [g for g in summarize(self.db, profile, dim) if g["n"] >= max(3, self.min_samples // 2)
                      and g["retention_index"] is not None and g[dim] != "unknown"]
            if len(groups) < 2:
                continue
            best, worst = groups[0], groups[-1]
            if best["retention_index"] - worst["retention_index"] >= 0.2:
                rid = self._add(profile, f"pattern_{dim}",
                                f"{dim}: '{best[dim]}' retains best (index {best['retention_index']:.2f}, n={best['n']}); "
                                f"'{worst[dim]}' weakest ({worst['retention_index']:.2f}, n={worst['n']})",
                                {"groups": groups})
                if rid:
                    created.append({"id": rid, "kind": f"pattern_{dim}"})
        return created

    def list(self, profile: str | None = None, status: str | None = None) -> list[dict]:
        sql, p = "SELECT * FROM recommendations WHERE 1=1", []
        if profile:
            sql += " AND profile=?"; p.append(profile)
        if status:
            sql += " AND status=?"; p.append(status)
        return self.db.query(sql + " ORDER BY id DESC", tuple(p))

    def apply(self, rec_id: int) -> dict:
        r = self.db.one("SELECT * FROM recommendations WHERE id=?", (rec_id,))
        if not r or r["status"] != "pending":
            raise ValueError(f"recommendation {rec_id} is not pending")
        change = loads(r["proposed_change"])
        if not change or "path" not in change:
            raise ValueError("this recommendation is informational and has no config change to apply")
        cdir = self.settings.root / "config"
        old = set_override(change["path"], change["value"], cdir)
        try:
            load_settings(self.settings.root)
        except Exception:
            set_override(change["path"], old, cdir)
            raise
        self.db.record_config_change(r["profile"], ".".join(change["path"]), old, change["value"],
                                     f"recommendation #{rec_id}: {r['description']}", "learning")
        self.db.update("recommendations", "id", rec_id, {"status": "applied", "decided_at": now_iso()})
        return {"applied": change, "previous_override": old}

    def dismiss(self, rec_id: int) -> None:
        self.db.update("recommendations", "id", rec_id, {"status": "dismissed", "decided_at": now_iso()})
