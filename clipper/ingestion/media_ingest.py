"""Authorized media ingestion.

Media is only acquired when the rights gate has passed for processing:
* ``local_file``: user-provided recordings — verified, probed and hashed in place.
* ``authorized_url``: a *direct media file* URL whose permission record explicitly grants
  download. Web pages (YouTube/Twitch watch pages, etc.) are refused: this module never scrapes,
  never bypasses DRM, authentication, rate limits or platform protections.
* ``research_lead``: metadata only — cannot be ingested until you supply the recording.
"""
from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path

from ..config import Settings
from ..core.media import file_sha256, media_info
from ..research.source_discovery import SourceStore


class IngestError(RuntimeError):
    pass


def place_source_file(store: SourceStore, settings: Settings, src: dict | None, rights_status: str) -> None:
    """Keep files that live under ``sources/`` in the folder matching their rights status
    (approved / pending / rejected). Files registered from elsewhere are never moved."""
    if not src or not src.get("local_path"):
        return
    p = Path(src["local_path"])
    base = settings.path(settings.global_.sources_dir).resolve()
    try:
        p.resolve().relative_to(base)
    except ValueError:
        return
    if not p.exists():
        return
    bucket = {"APPROVED": "approved", "APPROVED_WITH_CONDITIONS": "approved", "REJECTED": "rejected",
              "EXPIRED": "pending", "PENDING_VERIFICATION": "pending"}.get(rights_status, "pending")
    dest_dir = base / bucket / src["profile"]
    if p.parent.resolve() == dest_dir.resolve():
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / p.name
    moved = []
    for side in [p, *[p.with_suffix(s) for s in (".source.yaml", ".srt", ".vtt", ".json", ".transcript.json")]]:
        if side.exists():
            target = dest_dir / side.name
            shutil.move(str(side), str(target))
            moved.append(target)
    store.update(src["id"], local_path=str(dest.resolve()))


def ingest(store: SourceStore, settings: Settings, src: dict, rights_passed: bool) -> Path:
    if not rights_passed:
        raise IngestError(f"rights gate not passed ({src['rights_status']}): {src.get('rights_reason')}")
    kind = src["kind"]
    if kind == "research_lead" and not src.get("local_path"):
        raise IngestError("research lead has no authorized media: add the recording with "
                          "`sources attach` or register a direct authorized download URL")
    if kind == "authorized_url" and not src.get("local_path"):
        path = _download(settings, src)
        store.update(src["id"], local_path=str(path))
        src = store.get(src["id"])
    path = Path(src["local_path"] or "")
    if not path.is_file():
        raise IngestError(f"media file missing: {path}")
    info = media_info(path)
    if not info.get("has_video") or not info.get("has_audio"):
        raise IngestError("source must contain both video and audio streams")
    if info["duration"] < settings.profile(src["profile"]).duration.min_seconds:
        raise IngestError(f"source shorter than minimum clip duration ({info['duration']:.1f}s)")
    extra_hash = file_sha256(path)
    store.update(src["id"], duration=info["duration"], content_hash=extra_hash)
    return path


def _download(settings: Settings, src: dict) -> Path:
    cfg = settings.rights.get("authorized_download", {})
    if not cfg.get("enabled", True):
        raise IngestError("authorized downloads disabled in rights.yaml")
    url = src["url"]
    if not url or not url.startswith(("https://", "http://")):
        raise IngestError("authorized_url source needs an http(s) URL")
    allowed = set(cfg.get("allowed_content_types", []))
    max_bytes = int(cfg.get("max_bytes", 20 * 1024**3))
    dest_dir = settings.path(settings.global_.sources_dir) / "approved" / src["profile"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{src['id']}.mp4"
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": "local-clipping-machine/1.0"})
    with urllib.request.urlopen(req, timeout=float(cfg.get("timeout_seconds", 120))) as r:
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype not in allowed:
            raise IngestError(f"URL is not a direct media file (Content-Type {ctype or 'unknown'}). "
                              "Page URLs are never scraped; provide the file locally instead.")
        total = 0
        with tmp.open("wb") as fh:
            while chunk := r.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    fh.close(); tmp.unlink(missing_ok=True)
                    raise IngestError("download exceeds configured max_bytes")
                fh.write(chunk)
    tmp.replace(dest)
    return dest.resolve()
