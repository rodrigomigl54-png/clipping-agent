"""Transcript-level signals: hooks, surprise, laughter, arguments, stories, dangling context."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

LEXICON: dict[str, list[str]] = {
    "hook": ["no way", "wait", "hold on", "hold up", "listen", "you won't believe", "watch this",
             "look at this", "look at", "i'm not gonna lie", "ngl", "deadass", "on god", "i swear",
             "why would", "how did", "let me tell you", "what happened", "story time", "chat", "yo", "bro", "nah", "guess what", "real talk", "be honest"],
    "surprise": ["no way", "oh my god", "omg", "what the", "are you serious", "wait what", "huh",
                 "excuse me", "insane", "crazy", "unbelievable", "what just happened", "bro what",
                 "you're lying", "no shot", "how", "what"],
    "laughter": ["haha", "hahaha", "lmao", "lol", "[laughter]", "(laughs)", "[laughs]", "laughing",
                 "i'm crying", "i'm dying", "i'm dead", "bro i'm dead", "that's hilarious", "stop"],
    "emotion": ["scared", "love", "hate", "cry", "crying", "angry", "mad", "happy", "nervous", "hurt",
                "sorry", "proud", "screaming", "oh no", "please", "terrified", "heartbroken", "excited"],
    "argument": ["shut up", "trash", "you lost", "bum", "cap", "stop lying", "that's cap", "nobody asked",
                 "fraud", "you're mad", "be quiet", "no no no", "that's not", "you're wrong", "you're tweaking",
                 "you tweaking", "that's crazy", "say it again", "why are you", "don't lie", "you can't"],
    "roast": ["look at you", "your hair", "you look like", "built like", "ugly", "you smell", "broke",
              "washed", "trash", "bum", "clown", "goofy", "corny"],
    "story": ["so then", "and then", "story time", "one time", "remember when", "so basically",
              "long story", "this one time", "yesterday", "last night", "the other day", "i was like",
              "he was like", "she was like", "i told him", "i told her"],
    "challenge": ["challenge", "bet", "race", "first one", "loser", "winner", "1v1", "who wins",
                  "you lose", "punishment", "dare", "if you lose", "if i win", "for money", "rematch"],
    "confusion": ["what is happening", "what's going on", "i'm confused", "what do you mean",
                  "i don't understand", "what are you doing", "who is that", "why is"],
}
DANGLING_STARTS = {"and", "but", "so", "because", "cause", "that", "which", "who", "then", "also",
                   "he", "she", "they", "it", "this", "those", "these", "him", "her", "them", "or"}
SENTENCE_END = re.compile(r"[.!?…]['\")\]]*$")


def normalize(text: str) -> str:
    t = text.lower().replace("’", "'")
    return " " + re.sub(r"[^a-z0-9'\[\]() ]+", " ", t) + " "


def count_terms(text: str, terms: list[str]) -> int:
    n = normalize(text)
    total = 0
    for term in terms:
        total += len(re.findall(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", n))
    return total


@dataclass
class TextSignals:
    counts: dict[str, int] = field(default_factory=dict)
    questions: int = 0
    exclamations: int = 0
    caps_ratio: float = 0.0
    words: int = 0
    trend_hits: int = 0
    mentions: list[str] = field(default_factory=list)

    def density(self, key: str) -> float:
        return self.counts.get(key, 0) * 100.0 / max(20, self.words)


def text_signals(text: str, trend_terms: set[str] | None = None,
                 creator_aliases: dict[str, list[str]] | None = None) -> TextSignals:
    toks = text.split()
    letters = [c for c in text if c.isalpha()]
    sig = TextSignals(
        counts={k: count_terms(text, v) for k, v in LEXICON.items()},
        questions=text.count("?"),
        exclamations=text.count("!"),
        caps_ratio=(sum(c.isupper() for c in letters) / len(letters)) if letters else 0.0,
        words=len(toks),
    )
    if trend_terms:
        sig.trend_hits = count_terms(text, sorted(trend_terms))
    if creator_aliases:
        n = normalize(text)
        sig.mentions = [name for name, aliases in creator_aliases.items()
                        if any(re.search(r"(?<![a-z0-9])" + re.escape(a.lower()) + r"(?![a-z0-9])", n)
                               for a in aliases + [name])]
    return sig


def starts_dangling(text: str) -> bool:
    first = re.sub(r"[^a-z']", "", (text.strip().split() or [""])[0].lower())
    return first in DANGLING_STARTS


def ends_sentence(text: str) -> bool:
    return bool(SENTENCE_END.search(text.strip()))


def shingles(text: str, k: int = 3) -> set[str]:
    toks = re.findall(r"[a-z0-9']+", text.lower())
    if len(toks) < k:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def containment(a: set[str], b: set[str]) -> float:
    """Fraction of the smaller set contained in the other (robust to different clip lengths)."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))
