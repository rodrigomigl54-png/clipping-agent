"""Trend research (Gemini + Google Search grounding) and trend-term lookup for scoring."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ..config import Settings
from ..core.database import Database, dumps, loads, now_iso
from .google_ai import GeminiClient

TREND_PROMPT = """You are a research assistant for a short-form video editor.
Using Google Search, find topics, running jokes, events and challenges that are CURRENTLY being
discussed about these creators: {creators}{group} in the last {days} days (today is {today}).

Rules:
- Only report things supported by the search results. Never invent events or quotes.
- If you cannot find anything reliable, return an empty list.
Return ONLY JSON: {{"trends":[{{"topic":str,"creators":[str],"why":str,"keywords":[str]}}]}}"""


class TrendAnalyzer:
    def __init__(self, db: Database, settings: Settings, gemini: GeminiClient):
        self.db, self.settings, self.gemini = db, settings, gemini

    def research(self, profile: str) -> list[dict]:
        prof = self.settings.profile(profile)
        days = self.settings.global_.research.window_days
        prompt = TREND_PROMPT.format(
            creators=", ".join(c.name for c in prof.creators),
            group=f" (the group {prof.group_name})" if prof.group_name else "",
            days=days, today=datetime.now(timezone.utc).date().isoformat())
        res = self.gemini.grounded_research(prompt)
        trends = (res.data or {}).get("trends", []) if isinstance(res.data, dict) else []
        clean = []
        for t in trends:
            if not isinstance(t, dict) or not t.get("topic"):
                continue
            clean.append({"topic": str(t["topic"])[:200], "creators": [str(x) for x in t.get("creators", [])][:10],
                          "why": str(t.get("why", ""))[:500],
                          "keywords": [str(k).lower()[:40] for k in t.get("keywords", [])][:10]})
        self.db.insert("research_notes", {
            "profile": profile, "creator": None, "kind": "trend",
            "content": dumps({"trends": clean, "grounded": bool(res.citations)}),
            "citations": dumps(res.citations), "model": res.model, "researched_at": now_iso()})
        return clean

    def trend_terms(self, profile: str) -> set[str]:
        days = self.settings.global_.research.window_days
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        terms: set[str] = set()
        for r in self.db.query("SELECT content FROM research_notes WHERE profile=? AND kind='trend' "
                               "AND researched_at>=?", (profile, cutoff)):
            for t in loads(r["content"], {}).get("trends", []):
                for k in t.get("keywords", []):
                    k = re.sub(r"[^a-z0-9 ]", "", k.lower()).strip()
                    if len(k) >= 3:
                        terms.add(k)
        return terms
