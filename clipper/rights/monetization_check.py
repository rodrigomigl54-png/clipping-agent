"""Monetization-suitability assessment (internal heuristic, not a platform decision).

Passing this check does NOT guarantee YouTube Partner Program or TikTok monetization approval.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

DISCLAIMER = ("Internal heuristic assessment only. It does not guarantee YouTube Partner Program "
              "or TikTok monetization approval.")


@dataclass
class MonetizationAssessment:
    risk_level: str                     # low | medium | high | blocked
    flags: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    transformative_elements: list[str] = field(default_factory=list)
    blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"risk_level": self.risk_level, "flags": self.flags, "notes": self.notes,
                "transformative_elements": self.transformative_elements, "blocked": self.blocked,
                "disclaimer": DISCLAIMER}


def _term_hits(text: str, terms: list[str]) -> int:
    low = " " + re.sub(r"[^a-z0-9.\s]", " ", text.lower()) + " "
    hits = 0
    for t in terms:
        t = t.strip().lower()
        if not t:
            continue
        hits += len(re.findall(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", low))
    return hits


def assess(transcript_text: str, *, lexicons: dict[str, list[str]], rights_status: str,
           third_party_content: str, transformative_elements: list[str], clip_duration: float,
           source_duration: float | None, policy: dict[str, Any],
           profile_policy: dict[str, Any] | None = None) -> MonetizationAssessment:
    words = max(1, len(transcript_text.split()))
    flags: dict[str, float] = {}
    notes: list[str] = []
    for cat in ("gambling", "violence", "sexual", "harassment", "hate", "drugs"):
        hits = _term_hits(transcript_text, lexicons.get(cat, []))
        if hits:
            # density per 100 words, capped at 1.0 for readability
            flags[cat] = round(min(1.0, hits * 100 / words / 5), 3)

    risk = 0.0
    if rights_status not in ("APPROVED", "APPROVED_WITH_CONDITIONS"):
        notes.append(f"rights status {rights_status}: not monetizable until verified")
        risk += 3
    if third_party_content in ("unknown", "present_uncleared"):
        notes.append(f"third-party content (music/media) is {third_party_content}")
        risk += 1.5 if third_party_content == "unknown" else 3
    if len(transformative_elements) < 2:
        notes.append("limited transformative editing: reused-content risk")
        risk += 1.5
    if source_duration and source_duration > 0 and clip_duration / source_duration > 0.5:
        notes.append("clip covers more than half of the source: reused-content risk")
        risk += 1.0
    for cat, v in flags.items():
        weight = {"hate": 3, "harassment": 2, "sexual": 2, "violence": 1.5, "gambling": 2, "drugs": 1.5}[cat]
        risk += weight * (0.5 + v)
        notes.append(f"advertiser-suitability flag: {cat} ({v:.2f})")

    blocked = False
    block_thr = float(policy.get("gambling_score_block", 0.5))
    if flags.get("gambling", 0) >= block_thr and (
            policy.get("block_gambling_promotion", True)
            or (profile_policy or {}).get("block_gambling_primary", False)):
        blocked = True
        notes.append("gambling/casino is a primary theme of this clip: blocked by policy")
    if flags.get("hate", 0) > 0:
        blocked = True
        notes.append("hate-lexicon match: blocked pending human review")

    level = "blocked" if blocked else ("high" if risk >= 4 else "medium" if risk >= 2 else "low")
    return MonetizationAssessment(level, flags, notes, list(transformative_elements), blocked)
