"""Relevant hashtags only: profile base tags + creators actually in the clip + category."""
from __future__ import annotations

import re

from ..config import ProfileCfg

CATEGORY_TAGS = {"challenge": "challenge", "argument_debate": "debate", "reaction": "reaction",
                 "group_reaction": "reaction", "gaming": "gaming", "just_chatting": "justchatting",
                 "conversation": "podcast", "funny_moment": "funnymoments", "funny_interaction": "funnymoments"}


def tag(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def hashtags(prof: ProfileCfg, participants: list[str], category: str, trend_terms_in_clip: list[str]) -> list[str]:
    out: list[str] = []
    for p in participants:
        c = prof.creator(p)
        out += c.hashtags if c else [tag(p)]
    if prof.group_name:
        out.append(tag(prof.group_name))
    if category in CATEGORY_TAGS:
        out.append(CATEGORY_TAGS[category])
    out += [tag(t) for t in trend_terms_in_clip]          # only trends actually spoken in the clip
    out += prof.metadata.get("base_hashtags", [])
    seen, final = set(), []
    for h in out:
        h = tag(h)
        if h and h not in seen:
            seen.add(h); final.append("#" + h)
    return final[: int(prof.metadata.get("max_hashtags", 8))]
