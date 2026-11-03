"""Source discovery and the source index.

Discovery adapters only *find* sources and record metadata. They never download media.
Media is acquired exclusively by :mod:`clipper.ingestion.media_ingest`, after the rights gate.

Adapters:
* ``LocalInboxDiscovery`` — recordings the user drops into ``sources/inbox/<profile>/``
  (optionally with a ``<name>.source.yaml`` sidecar describing creators and rights context).
* ``YouTubeRSSDiscovery`` — metadata from official channel RSS feeds (no download).
* Gemini research leads — see :mod:`clipper.research.research_engine`.
"""
from __future__ import annotations

import hashlib
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from ..config import Settings
from ..core.database import Database, dumps, loads, now_iso
from ..core.logger import get_logger
from ..models import RightsStatus, Stage

log = get_logger("discovery")
MEDIA_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".avi"}
THIRD_PARTY_VALUES = ("none", "unknown", "present_cleared", "present_uncleared")


def _parse_dt(v: Any) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        dt = v
    else:
        s = str(v).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def source_id_for(profile: str, key: str) -> str:
    return "src_" + hashlib.sha1(f"{profile}|{key}".encode()).hexdigest()[:12]


class SourceStore:
    """CRUD on the ``sources`` table (the source index)."""

    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings

    def get(self, sid: str) -> dict | None:
        return self.db.one("SELECT * FROM sources WHERE id=?", (sid,))

    def exists(self, sid: str) -> bool:
        return self.get(sid) is not None

    def register(self, *, profile: str, kind: str, key: str, title: str | None = None,
                 url: str | None = None, local_path: str | None = None, channel: str | None = None,
                 creators: list[str] | None = None, participants: list[str] | None = None,
                 category: str | None = None, published_at: Any = None, recorded_start: Any = None,
                 discovery_method: str = "manual", third_party_content: str = "unknown",
                 facecam_region: list[float] | None = None, extra: dict | None = None) -> tuple[str, bool]:
        """Insert a source if not already indexed. Returns (source_id, created)."""
        self.settings.profile(profile)
        if kind not in ("local_file", "authorized_url", "research_lead"):
            raise ValueError(f"invalid kind {kind}")
        if third_party_content not in THIRD_PARTY_VALUES:
            raise ValueError(f"third_party_content must be one of {THIRD_PARTY_VALUES}")
        if facecam_region is not None:
            if len(facecam_region) != 4 or not all(0 <= float(x) <= 1 for x in facecam_region):
                raise ValueError("facecam_region must be 4 normalised numbers x,y,w,h in [0,1]")
        sid = source_id_for(profile, key)
        if self.exists(sid):
            return sid, False
        if url and self.db.one("SELECT id FROM sources WHERE profile=? AND url=?", (profile, url)):
            return self.db.one("SELECT id FROM sources WHERE profile=? AND url=?", (profile, url))["id"], False
        prof = self.settings.profile(profile)
        canon = [(prof.creator(c).name if prof.creator(c) else c.strip()) for c in (creators or []) if c.strip()]
        parts = [(prof.creator(c).name if prof.creator(c) else c.strip()) for c in (participants or []) if c.strip()]
        if canon and not parts:
            parts = list(canon)
        self.db.insert("sources", {
            "id": sid, "profile": profile, "kind": kind, "title": title, "url": url,
            "local_path": local_path, "channel": channel, "creators": dumps(canon),
            "participants": dumps(sorted(set(parts))), "category": category,
            "published_at": _parse_dt(published_at), "recorded_start": _parse_dt(recorded_start),
            "discovered_at": now_iso(), "discovery_method": discovery_method,
            "third_party_content": third_party_content,
            "facecam_region": dumps(facecam_region) if facecam_region else None,
            "stage": Stage.WAITING.value, "rights_status": RightsStatus.PENDING_VERIFICATION.value,
            "extra": dumps(extra or {}), "updated_at": now_iso(),
        })
        self.db.log_event("source", sid, Stage.WAITING.value, f"registered via {discovery_method}", profile)
        return sid, True

    def set_stage(self, sid: str, stage: Stage | str, message: str | None = None, error: str | None = None) -> None:
        vals: dict[str, Any] = {"stage": str(stage), "updated_at": now_iso()}
        if error is not None:
            vals["last_error"] = error[:4000]
        self.db.update("sources", "id", sid, vals)
        src = self.get(sid)
        self.db.log_event("source", sid, str(stage), message or str(stage), src["profile"] if src else None,
                          "error" if error else "info")

    def update(self, sid: str, **values: Any) -> None:
        for k in ("creators", "participants", "extra", "facecam_region"):
            if k in values and not isinstance(values[k], str) and values[k] is not None:
                values[k] = dumps(values[k])
        values["updated_at"] = now_iso()
        self.db.update("sources", "id", sid, values)

    def list(self, profile: str | None = None, stage: str | None = None,
             rights_status: str | None = None) -> list[dict]:
        sql, p = "SELECT * FROM sources WHERE 1=1", []
        if profile:
            sql += " AND profile=?"; p.append(profile)
        if stage:
            sql += " AND stage=?"; p.append(stage)
        if rights_status:
            sql += " AND rights_status=?"; p.append(rights_status)
        return self.db.query(sql + " ORDER BY discovered_at DESC", tuple(p))

    def in_window(self, src: dict, now: datetime | None = None) -> bool:
        if loads(src.get("extra"), {}).get("ignore_window"):
            return True
        days = self.settings.global_.research.window_days
        now = now or datetime.now(timezone.utc)
        ts = src.get("published_at") or src.get("recorded_start") or src.get("discovered_at")
        try:
            dt = datetime.fromisoformat(ts)
        except (TypeError, ValueError):
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= now - timedelta(days=days)


# ---------------------------------------------------------------------------- adapters
class LocalInboxDiscovery:
    """Registers media files dropped into ``sources/inbox/<profile>/``."""

    def __init__(self, store: SourceStore, settings: Settings):
        self.store = store
        self.settings = settings

    def inbox(self, profile: str) -> Path:
        return self.settings.path(self.settings.global_.sources_dir) / "inbox" / profile

    @staticmethod
    def read_sidecar(media: Path) -> dict:
        for cand in (media.with_suffix(".source.yaml"), media.with_suffix(".source.yml"),
                     media.parent / (media.name + ".source.yaml")):
            if cand.exists():
                data = yaml.safe_load(cand.read_text(encoding="utf-8")) or {}
                if not isinstance(data, dict):
                    raise ValueError(f"{cand} must be a mapping")
                return data
        return {}

    def scan(self, profile: str) -> list[str]:
        inbox = self.inbox(profile)
        inbox.mkdir(parents=True, exist_ok=True)
        created = []
        for f in sorted(inbox.iterdir()):
            if not f.is_file() or f.suffix.lower() not in MEDIA_EXTS:
                continue
            try:
                meta = self.read_sidecar(f)
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                sid, new = self.store.register(
                    profile=profile, kind="local_file", key=f"file:{f.resolve()}",
                    title=meta.get("title") or f.stem, url=meta.get("url"), local_path=str(f.resolve()),
                    channel=meta.get("channel"), creators=meta.get("creators") or [],
                    participants=meta.get("participants") or [], category=meta.get("category"),
                    published_at=meta.get("published_at") or mtime,
                    recorded_start=meta.get("recorded_start"),
                    discovery_method="local_inbox",
                    third_party_content=meta.get("third_party_content", "unknown"),
                    facecam_region=meta.get("facecam_region"),
                    extra={"sidecar": bool(meta), "ignore_window": bool(meta.get("ignore_window", False)),
                           "notes": meta.get("notes")},
                )
                if new:
                    created.append(sid)
                    log.info("inbox: registered %s for %s", f.name, profile)
            except Exception as e:  # one bad file must not stop the scan
                log.error("inbox: failed to register %s: %s", f, e)
                self.store.db.log_error("discovery.inbox", str(f), str(e), profile=profile)
        return created


class YouTubeRSSDiscovery:
    """Metadata-only discovery from the official YouTube channel RSS feed.

    Results are research leads (``kind=research_lead``): no media is downloaded. They stay
    PENDING_VERIFICATION until a permission record and an authorized media file exist."""

    FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
    NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
          "media": "http://search.yahoo.com/mrss/"}

    def __init__(self, store: SourceStore, settings: Settings, fetch=None):
        self.store = store
        self.settings = settings
        self.fetch = fetch or self._fetch

    @staticmethod
    def _fetch(url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "local-clipping-machine/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()

    def parse(self, xml_bytes: bytes) -> list[dict]:
        root = ET.fromstring(xml_bytes)
        out = []
        for e in root.findall("a:entry", self.NS):
            link = e.find("a:link", self.NS)
            out.append({
                "video_id": (e.findtext("yt:videoId", default="", namespaces=self.NS) or "").strip(),
                "title": e.findtext("a:title", default="", namespaces=self.NS),
                "url": link.get("href") if link is not None else None,
                "published": e.findtext("a:published", default=None, namespaces=self.NS),
                "channel": e.findtext("a:author/a:name", default=None, namespaces=self.NS),
            })
        return out

    def scan(self, profile: str) -> list[str]:
        prof = self.settings.profile(profile)
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.settings.global_.research.window_days)
        created = []
        for c in prof.creators:
            for cid in c.youtube_channel_ids:
                if not re.fullmatch(r"UC[0-9A-Za-z_-]{22}", cid):
                    log.warning("rss: skipping invalid channel id %r for %s", cid, c.name)
                    continue
                try:
                    entries = self.parse(self.fetch(self.FEED.format(cid=cid)))
                except Exception as e:
                    self.store.db.log_error("discovery.rss", cid, f"RSS fetch failed: {e}", profile=profile)
                    continue
                for en in entries:
                    pub = _parse_dt(en["published"])
                    if not pub or datetime.fromisoformat(pub) < cutoff or not en["url"]:
                        continue
                    sid, new = self.store.register(
                        profile=profile, kind="research_lead", key=f"yt:{en['video_id']}",
                        title=en["title"], url=en["url"], channel=cid, creators=[c.name],
                        published_at=pub, discovery_method="youtube_rss",
                        extra={"channel_name": en["channel"], "note": "metadata only; media not acquired"})
                    if new:
                        created.append(sid)
        return created
