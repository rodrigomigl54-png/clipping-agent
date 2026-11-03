"""Duplicate prevention against the permanent export registry (and in-flight clips)."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..core.database import Database, loads
from ..detection.audio_analyzer import fingerprint_similarity
from ..detection.text_signals import containment, shingles
from .fingerprints import phash_distance


@dataclass
class DuplicateResult:
    is_duplicate: bool
    reason: str = ""
    match_clip_id: str | None = None
    similarity: float = 0.0


class DuplicateDetector:
    def __init__(self, db: Database, settings: Settings, overlap_ratio: float = 0.5,
                 text_threshold: float = 0.6, phash_threshold: float = 10.0, audio_threshold: float = 0.93):
        self.db, self.settings = db, settings
        self.overlap_ratio = overlap_ratio
        self.text_threshold = text_threshold
        self.phash_threshold = phash_threshold
        self.audio_threshold = audio_threshold

    def _registry(self, profile: str) -> list[dict]:
        cross = self.settings.profile(profile).feature("cross_profile_duplicate_check")
        reg = self.db.query("SELECT * FROM export_registry" + ("" if cross else " WHERE profile=?"),
                            () if cross else (profile,))
        # in-flight clips (rendered/approved/needs_review but not yet exported) also count
        inflight = self.db.query(
            "SELECT c.id clip_id, c.profile, c.source_id, k.start, k.\"end\", k.transcript_text, c.phash, c.audio_fp "
            "FROM clips c JOIN candidates k ON k.id=c.candidate_id "
            "WHERE c.decision IN ('APPROVED','NEEDS_REVIEW') AND c.exported_at IS NULL"
            + ("" if cross else " AND c.profile=?"), () if cross else (profile,))
        return reg + inflight

    def check_candidate(self, cand: dict, exclude_clip: str | None = None) -> DuplicateResult:
        mine = shingles(cand.get("transcript_text") or "")
        for r in self._registry(cand["profile"]):
            if exclude_clip and r["clip_id"] == exclude_clip:
                continue
            if r["source_id"] == cand["source_id"] and r["start"] is not None:
                ov = min(cand["end"], r["end"]) - max(cand["start"], r["start"])
                shorter = min(cand["end"] - cand["start"], r["end"] - r["start"])
                if shorter > 0 and ov / shorter >= self.overlap_ratio:
                    return DuplicateResult(True, f"overlaps exported clip {r['clip_id']} ({ov / shorter:.0%})",
                                           r["clip_id"], ov / shorter)
            sim = containment(mine, shingles(r.get("transcript_text") or ""))
            if sim >= self.text_threshold:
                return DuplicateResult(True, f"transcript {sim:.0%} similar to clip {r['clip_id']}", r["clip_id"], sim)
        return DuplicateResult(False)

    def check_render(self, profile: str, clip_id: str, phash: list[str], audio_fp: list[float]) -> DuplicateResult:
        for r in self._registry(profile):
            if r["clip_id"] == clip_id:
                continue
            ph = loads(r.get("phash"), [])
            if ph and phash and phash_distance(ph, phash) <= self.phash_threshold:
                return DuplicateResult(True, f"visually near-identical to clip {r['clip_id']}", r["clip_id"])
            af = loads(r.get("audio_fp"), [])
            if af and audio_fp and fingerprint_similarity(af, audio_fp) >= self.audio_threshold:
                return DuplicateResult(True, f"audio near-identical to clip {r['clip_id']}", r["clip_id"])
        return DuplicateResult(False)
