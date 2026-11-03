"""Research engine: rolling seven-day discovery across all adapters.

Steps per profile: discover eligible sources → skip already-indexed → record metadata →
(optionally) grounded Gemini research for leads + trends → evaluate rights for every new source.
Nothing here downloads media.
"""
from __future__ import annotations

import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import Settings
from ..core.database import Database, dumps, now_iso
from ..core.logger import get_logger
from .attention import AttentionAllocator
from .google_ai import GeminiClient, GeminiUnavailable
from .source_discovery import LocalInboxDiscovery, SourceStore, YouTubeRSSDiscovery, _parse_dt
from .trend_analysis import TrendAnalyzer

log = get_logger("research")

LEADS_PROMPT = """You are a research assistant. Using Google Search, list long-form streams,
VODs and videos published by {creator}{group} between {start} and {end}.

Rules:
- Only include items you found in search results, with their real URL. Never invent titles,
  URLs, dates, quotes or events. If unsure about a field, use null.
- Do not include more than {limit} items.
Return ONLY JSON:
{{"items":[{{"title":str,"url":str,"platform":str|null,"published_at":"YYYY-MM-DD"|null,
"participants":[str],"summary":str|null,"notable_moments":[{{"description":str,"approx_timestamp":str|null}}]}}]}}"""


class ResearchEngine:
    def __init__(self, db: Database, settings: Settings, gemini: GeminiClient, rights_gate=None,
                 rss_fetch=None):
        self.db, self.settings, self.gemini = db, settings, gemini
        self.store = SourceStore(db, settings)
        self.inbox = LocalInboxDiscovery(self.store, settings)
        self.rss = YouTubeRSSDiscovery(self.store, settings, fetch=rss_fetch)
        self.trends = TrendAnalyzer(db, settings, gemini)
        self.attention = AttentionAllocator(db, settings)
        self.rights_gate = rights_gate

    def _run(self, profile: str, kind: str, fn) -> dict[str, Any]:
        days = self.settings.global_.research.window_days
        now = datetime.now(timezone.utc)
        rid = self.db.insert("research_runs", {
            "profile": profile, "kind": kind, "started_at": now_iso(), "status": "running",
            "window_start": (now - timedelta(days=days)).isoformat(), "window_end": now.isoformat()})
        try:
            found, details = fn()
            self.db.update("research_runs", "id", rid, {"finished_at": now_iso(), "status": "ok",
                                                         "found": found, "details": dumps(details)})
            return {"kind": kind, "status": "ok", "found": found, "details": details}
        except GeminiUnavailable as e:
            self.db.update("research_runs", "id", rid, {"finished_at": now_iso(), "status": "skipped",
                                                         "error": str(e)})
            return {"kind": kind, "status": "skipped", "error": str(e)}
        except Exception as e:
            self.db.update("research_runs", "id", rid, {"finished_at": now_iso(), "status": "failed",
                                                         "error": str(e)[:2000]})
            self.db.log_error(f"research.{kind}", None, str(e), traceback.format_exc(), profile)
            log.error("research %s/%s failed: %s", profile, kind, e)
            return {"kind": kind, "status": "failed", "error": str(e)}

    # ------------------------------------------------------------------ gemini leads
    def gemini_leads(self, profile: str) -> tuple[int, dict]:
        prof = self.settings.profile(profile)
        days = self.settings.global_.research.window_days
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=days)).date().isoformat()
        alloc = self.attention.allocate(profile, self.settings.global_.research.max_sources_per_cycle)
        created, per_creator = 0, {}
        for creator, limit in alloc.items():
            prompt = LEADS_PROMPT.format(creator=creator,
                                         group=f" (member of {prof.group_name})" if prof.group_name else "",
                                         start=start, end=now.date().isoformat(), limit=limit)
            res = self.gemini.grounded_research(prompt)
            items = (res.data or {}).get("items", []) if isinstance(res.data, dict) else []
            self.db.insert("research_notes", {
                "profile": profile, "creator": creator, "kind": "leads",
                "content": dumps({"items": items[:limit], "grounded": bool(res.citations),
                                  "queries": res.queries}),
                "citations": dumps(res.citations), "model": res.model, "researched_at": now_iso()})
            n = 0
            for it in items[:limit]:
                url = str(it.get("url") or "")
                if not url.startswith(("http://", "https://")):
                    continue
                pub = _parse_dt(it.get("published_at"))
                if pub and datetime.fromisoformat(pub) < now - timedelta(days=days + 1):
                    continue  # outside rolling window
                sid, new = self.store.register(
                    profile=profile, kind="research_lead", key=f"url:{url}", title=it.get("title"),
                    url=url, creators=[creator], participants=[creator, *(it.get("participants") or [])],
                    published_at=pub, discovery_method="gemini_grounded_search",
                    extra={"ai_summary": it.get("summary"), "ai_notable_moments": it.get("notable_moments"),
                           "citations": res.citations[:10], "researched_at": now_iso(),
                           "verified": False,
                           "note": "AI research lead: unverified, media not acquired"})
                if new:
                    n += 1
            per_creator[creator] = n
            created += n
        return created, {"per_creator": per_creator, "allocation": alloc}

    # ------------------------------------------------------------------ public API
    def research_profile(self, profile: str, *, use_gemini: bool | None = None) -> dict[str, Any]:
        self.settings.profile(profile)
        rcfg = self.settings.global_.research
        results = [self._run(profile, "local_inbox", lambda: self._count(self.inbox.scan(profile)))]
        if rcfg.enable_youtube_rss:
            results.append(self._run(profile, "youtube_rss", lambda: self._count(self.rss.scan(profile))))
        want_gemini = rcfg.enable_gemini_research if use_gemini is None else use_gemini
        if want_gemini:
            if not self.gemini.available():
                results.append({"kind": "gemini", "status": "skipped",
                                "error": f"{self.settings.global_.google_ai.api_key_env} not set"})
            elif self._gemini_due(profile) or use_gemini:
                results.append(self._run(profile, "gemini_leads", lambda: self.gemini_leads(profile)))
                results.append(self._run(profile, "trends",
                                         lambda: (len(t := self.trends.research(profile)), {"trends": t})))
        if self.rights_gate is not None:
            self.refresh_rights(profile)
        self.attention.update_from_evidence(profile)
        self.db.set_state(f"last_research:{profile}", now_iso())
        return {"profile": profile, "results": results}

    @staticmethod
    def _count(ids: list[str]) -> tuple[int, dict]:
        return len(ids), {"source_ids": ids}

    def _gemini_due(self, profile: str) -> bool:
        r = self.db.one("SELECT max(started_at) t FROM research_runs WHERE profile=? AND kind='gemini_leads' "
                        "AND status='ok'", (profile,))
        if not r or not r["t"]:
            return True
        last = datetime.fromisoformat(r["t"])
        mins = self.settings.global_.research.gemini_research_interval_minutes
        return datetime.now(timezone.utc) - last >= timedelta(minutes=mins)

    def refresh_rights(self, profile: str | None = None) -> list[dict]:
        """Re-evaluate the processing rights gate for sources not yet past it."""
        from ..ingestion.media_ingest import place_source_file
        out = []
        for src in self.store.list(profile):
            if src["stage"] not in ("waiting", "blocked_rights"):
                continue
            d = self.rights_gate.evaluate(src, "processing")
            stage = "waiting" if d.passed else "blocked_rights"
            self.store.update(src["id"], rights_status=d.status, rights_reason=d.summary(), stage=stage)
            place_source_file(self.store, self.settings, self.store.get(src["id"]), d.status)
            out.append({"source_id": src["id"], "status": d.status, "reasons": d.reasons})
        return out
