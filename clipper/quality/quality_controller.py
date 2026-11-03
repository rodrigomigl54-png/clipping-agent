"""Final QC decision: APPROVED / NEEDS_REVIEW / REJECTED.

Order of precedence: a failed rights check or a technically broken file can never be overridden
by a high viral score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import Decision
from .technical_checks import CheckReport


@dataclass
class QCResult:
    decision: str
    reasons: list[str]
    quality_score: float
    technical: list[dict] = field(default_factory=list)
    content: list[dict] = field(default_factory=list)
    rights: dict[str, Any] = field(default_factory=dict)
    monetization: dict[str, Any] = field(default_factory=dict)
    duplicate: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"decision": self.decision, "reasons": self.reasons, "quality_score": self.quality_score,
                "technical": self.technical, "content": self.content, "rights": self.rights,
                "monetization": self.monetization, "duplicate": self.duplicate}


def decide(*, technical: CheckReport, content: CheckReport, rights, monetization, duplicate,
           scores: dict, rights_unknown_policy: str = "needs_review") -> QCResult:
    reasons: list[str] = []
    decision = Decision.APPROVED.value

    def worse(d: str):
        nonlocal decision
        order = [Decision.APPROVED.value, Decision.NEEDS_REVIEW.value, Decision.REJECTED.value]
        if order.index(d) > order.index(decision):
            decision = d

    for c in technical.failed("fail"):
        worse(Decision.REJECTED.value); reasons.append(f"technical: {c.name} ({c.detail})")
    for c in technical.failed("review"):
        worse(Decision.NEEDS_REVIEW.value); reasons.append(f"technical: {c.name} ({c.detail})")
    for c in content.failed("fail"):
        worse(Decision.REJECTED.value); reasons.append(f"content: {c.name} ({c.detail})")
    for c in content.failed("review"):
        worse(Decision.NEEDS_REVIEW.value); reasons.append(f"content: {c.name} ({c.detail})")
    if rights.status == "REJECTED":
        worse(Decision.REJECTED.value); reasons.append("rights: " + rights.summary())
    elif not rights.passed:
        unknown_tp = "third_party_content_verification" in rights.missing
        worse(Decision.REJECTED.value if unknown_tp and rights_unknown_policy == "reject" else Decision.NEEDS_REVIEW.value)
        reasons.append("rights: " + rights.summary())
    if monetization.blocked:
        worse(Decision.REJECTED.value); reasons.append("policy: " + "; ".join(monetization.notes[-2:]))
    elif monetization.risk_level == "high":
        worse(Decision.NEEDS_REVIEW.value); reasons.append("monetization risk high: " + "; ".join(monetization.notes[:3]))
    if duplicate.is_duplicate:
        worse(Decision.REJECTED.value); reasons.append("duplicate: " + duplicate.reason)

    comp = [scores.get(k, 5) for k in ("context_completeness", "audio_quality", "visual_quality", "payoff_strength")]
    q = 50 * (0.6 * technical.pass_ratio + 0.4 * content.pass_ratio) + 50 * (sum(comp) / len(comp) / 10)
    return QCResult(decision, reasons, round(q, 1), [c.to_dict() for c in technical.checks],
                    [c.to_dict() for c in content.checks], rights.to_dict(), monetization.to_dict(),
                    {"is_duplicate": duplicate.is_duplicate, "reason": duplicate.reason,
                     "match": duplicate.match_clip_id})
