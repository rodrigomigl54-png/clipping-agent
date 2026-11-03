"""Shared enums and data structures passed between modules."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class Stage(StrEnum):
    """Processing states, shown to the user exactly as named."""
    WAITING = "waiting"
    RESEARCHING = "researching"
    IMPORTING = "importing"          # downloading or importing authorized media
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    CLIPPING = "clipping"
    EDITING = "editing"
    QUALITY_CHECKING = "quality_checking"
    EXPORTING = "exporting"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    BLOCKED_RIGHTS = "blocked_rights"   # waiting on permission verification


class RightsStatus(StrEnum):
    APPROVED = "APPROVED"
    APPROVED_WITH_CONDITIONS = "APPROVED_WITH_CONDITIONS"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class Decision(StrEnum):
    APPROVED = "APPROVED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"


class CandidateStatus(StrEnum):
    NEW = "new"
    BELOW_THRESHOLD = "below_threshold"
    DUPLICATE = "duplicate"
    SUPERSEDED = "superseded"        # another source of the same event was chosen
    QUEUED = "queued"
    RENDERED = "rendered"
    APPROVED = "approved"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"
    EXPORTED = "exported"
    FAILED = "failed"


SCORE_KEYS = (
    "hook_strength", "entertainment", "emotional_impact", "context_completeness",
    "story_progression", "payoff_strength", "originality", "shareability",
    "visual_quality", "audio_quality", "platform_suitability", "group_chemistry",
)


@dataclass
class Word:
    start: float
    end: float
    text: str
    probability: float = 1.0
    speaker: str | None = None


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    speaker: str | None = None
    avg_logprob: float | None = None
    no_speech_prob: float | None = None


@dataclass
class Transcript:
    source_id: str
    engine: str
    language: str
    segments: list[Segment]
    word_timing: str = "native"          # native | estimated

    @property
    def words(self) -> list[Word]:
        return [w for s in self.segments for w in s.words]

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments).strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Transcript":
        segs = []
        for s in d.get("segments", []):
            words = [Word(**w) for w in s.get("words", [])]
            segs.append(Segment(**{**s, "words": words}))
        return cls(source_id=d["source_id"], engine=d["engine"], language=d.get("language", "en"),
                   segments=segs, word_timing=d.get("word_timing", "native"))

    def window(self, start: float, end: float) -> list[Segment]:
        return [s for s in self.segments if s.end > start and s.start < end]

    def words_in(self, start: float, end: float) -> list[Word]:
        return [w for w in self.words if w.end > start and w.start < end]


@dataclass
class CandidateMoment:
    source_id: str
    profile: str
    start: float
    end: float
    peak: float
    scores: dict[str, float]
    total_score: float
    hook_type: str
    category: str
    transcript_text: str
    summary: str
    signals: dict[str, Any] = field(default_factory=dict)
    participants: list[str] = field(default_factory=list)
    ai_analysis: dict[str, Any] | None = None
    id: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start
