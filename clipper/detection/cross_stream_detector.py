"""Cross-streamer moment detection.

Groups candidates from different sources that capture the same event (e.g. several AMP members
reacting to the same incident on their own streams), picks the best source, and suppresses
redundant versions. A second perspective is kept only when the profile allows it, it adds
substantially different content, and its own rights are independently cleared.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..config import Settings
from ..core.database import Database, dumps, loads, new_id, now_iso
from .text_signals import containment, shingles


def _abs_interval(src: dict, start: float, end: float):
    rs = src.get("recorded_start")
    if not rs:
        return None
    t0 = datetime.fromisoformat(rs)
    return t0 + timedelta(seconds=start), t0 + timedelta(seconds=end)


class CrossStreamDetector:
    def __init__(self, db: Database, settings: Settings, text_threshold: float = 0.25,
                 time_overlap: float = 0.3):
        self.db, self.settings = db, settings
        self.text_threshold = text_threshold
        self.time_overlap = time_overlap

    def related(self, a: dict, b: dict, sa: dict, sb: dict) -> tuple[bool, str]:
        if a["source_id"] == b["source_id"]:
            return False, ""
        ia, ib = _abs_interval(sa, a["start"], a["end"]), _abs_interval(sb, b["start"], b["end"])
        if ia and ib:
            ov = (min(ia[1], ib[1]) - max(ia[0], ib[0])).total_seconds()
            shorter = min((ia[1] - ia[0]).total_seconds(), (ib[1] - ib[0]).total_seconds())
            if shorter > 0 and ov / shorter >= self.time_overlap:
                return True, f"same wall-clock time ({ov / shorter:.0%} overlap)"
        sim = containment(shingles(a["transcript_text"] or ""), shingles(b["transcript_text"] or ""))
        if sim >= self.text_threshold:
            return True, f"shared dialogue ({sim:.0%})"
        return False, ""

    @staticmethod
    def quality(c: dict) -> float:
        s = loads(c["scores"], {})
        return (float(c["total_score"] or 0) + 2.0 * s.get("audio_quality", 5) + 1.5 * s.get("visual_quality", 5)
                + 2.0 * s.get("context_completeness", 5))

    def resolve(self, profile: str) -> list[dict]:
        prof = self.settings.profile(profile)
        if not prof.feature("cross_stream_detection"):
            return []
        cands = self.db.query("SELECT * FROM candidates WHERE profile=? AND status='new' AND event_group_id IS NULL",
                              (profile,))
        srcs = {r["id"]: r for r in self.db.query("SELECT * FROM sources WHERE profile=?", (profile,))}
        parent = list(range(len(cands)))
        why: dict[tuple[int, int], str] = {}

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                ok, reason = self.related(cands[i], cands[j], srcs.get(cands[i]["source_id"], {}),
                                          srcs.get(cands[j]["source_id"], {}))
                if ok:
                    parent[find(j)] = find(i)
                    why[(i, j)] = reason
        groups: dict[int, list[int]] = {}
        for i in range(len(cands)):
            groups.setdefault(find(i), []).append(i)
        results = []
        for members in groups.values():
            if len(members) < 2:
                continue
            ms = sorted((cands[i] for i in members), key=lambda c: -self.quality(c))
            best = ms[0]
            gid = new_id("evt")
            kept = [best["id"]]
            for other in ms[1:]:
                distinct = containment(shingles(best["transcript_text"] or ""),
                                       shingles(other["transcript_text"] or "")) < 0.3
                if prof.feature("allow_multiple_perspectives") and distinct and \
                        float(other["total_score"]) >= prof.min_quality_threshold:
                    kept.append(other["id"])
                    self.db.update("candidates", "id", other["id"], {"event_group_id": gid,
                                   "status_reason": f"additional perspective of event {gid}", "updated_at": now_iso()})
                else:
                    self.db.update("candidates", "id", other["id"], {
                        "event_group_id": gid, "status": "superseded", "updated_at": now_iso(),
                        "status_reason": f"same event as {best['id']} (better source chosen)"})
            self.db.update("candidates", "id", best["id"], {"event_group_id": gid, "updated_at": now_iso()})
            reasons = sorted({r for (i, j), r in why.items() if i in members and j in members})
            self.db.insert("event_groups", {"id": gid, "profile": profile, "label": best["summary"],
                                            "members": dumps([c["id"] for c in ms]), "chosen_candidate_id": best["id"],
                                            "reason": "; ".join(reasons), "created_at": now_iso()})
            results.append({"event_group": gid, "chosen": best["id"], "kept": kept,
                            "members": [c["id"] for c in ms], "reason": reasons})
        return results
