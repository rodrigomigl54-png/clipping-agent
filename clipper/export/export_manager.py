"""Local export manager. Only APPROVED clips are written to outputs/<BRAND>/<YYYY-MM-DD>/.

A clip is only reported as exported after the copy exists and its checksum matches the render.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..config import Settings
from ..core.database import Database, dumps, loads, now_iso


def slugify(s: str, n: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:n].rstrip("-") or "clip"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class ExportError(RuntimeError):
    pass


class ExportManager:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings

    def folder(self, profile: str, when: datetime | None = None) -> Path:
        prof = self.settings.profile(profile)
        day = (when or datetime.now(timezone.utc)).strftime(self.settings.global_.export.get("date_format", "%Y-%m-%d"))
        return self.settings.path(self.settings.global_.outputs_dir) / prof.output_folder / day

    def export(self, clip_id: str) -> dict:
        clip = self.db.one("SELECT * FROM clips WHERE id=?", (clip_id,))
        if not clip:
            raise ExportError(f"clip {clip_id} not found")
        if clip["decision"] != "APPROVED":
            raise ExportError(f"clip {clip_id} is {clip['decision']}; only APPROVED clips are exported")
        if clip["exported_at"] and clip["export_path"] and Path(clip["export_path"]).exists():
            return self.summary(clip_id)
        render = Path(clip["render_path"] or "")
        if not render.is_file():
            raise ExportError(f"render missing: {render}")
        meta = loads(clip["metadata"], {})
        base = self.folder(clip["profile"])
        name = f"{base.name}_{clip['profile']}_{slugify(meta.get('title', 'clip'))}_{clip_id[-6:]}"
        dst = base / "clips" / f"{name}.mp4"
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".part")
        shutil.copy2(render, tmp)
        if sha256(tmp) != sha256(render):
            tmp.unlink(missing_ok=True)
            raise ExportError("integrity check failed while copying clip")
        tmp.replace(dst)
        thumb_dst = None
        if clip["thumbnail_path"] and Path(clip["thumbnail_path"]).exists():
            thumb_dst = base / "thumbnails" / f"{name}.jpg"
            thumb_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(clip["thumbnail_path"], thumb_dst)
        meta_dst = base / "metadata" / f"{name}.json"
        meta_dst.parent.mkdir(parents=True, exist_ok=True)
        record = {
            **meta, "clip_id": clip_id, "file": str(dst.resolve()),
            "thumbnail": str(thumb_dst.resolve()) if thumb_dst else None,
            "viral_potential_score": clip["viral_score"], "quality_score": clip["quality_score"],
            "rights_status": clip["rights_status"], "monetization": loads(clip["monetization"], {}),
            "format": clip["format"], "layout": clip["layout"], "qc_decision": clip["decision"],
            "note": "Scores are AI-estimated potential, not predictions of platform performance. "
                    "Publish manually; nothing is uploaded automatically.",
            "exported_at": now_iso(),
        }
        meta_dst.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        cand = self.db.one("SELECT * FROM candidates WHERE id=?", (clip["candidate_id"],))
        with self.db.transaction() as c:
            c.execute("UPDATE clips SET export_path=?, metadata_path=?, exported_at=?, stage='completed', updated_at=? "
                      "WHERE id=?", (str(dst.resolve()), str(meta_dst.resolve()), now_iso(), now_iso(), clip_id))
            c.execute("INSERT OR REPLACE INTO export_registry(clip_id,profile,source_id,start,\"end\",transcript_text,"
                      "phash,audio_fp,export_path,exported_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (clip_id, clip["profile"], clip["source_id"], meta.get("original_timestamp", {}).get("start"),
                       meta.get("original_timestamp", {}).get("end"), cand["transcript_text"] if cand else "",
                       clip["phash"], clip["audio_fp"], str(dst.resolve()), now_iso()))
            c.execute("UPDATE candidates SET status='exported', updated_at=? WHERE id=?", (now_iso(), clip["candidate_id"]))
        return self.summary(clip_id)

    def export_private_test(self, clip_id: str) -> dict:
        """Copy a clip to outputs/_PRIVATE_TEST/<BRAND>/<date>/ for private evaluation only."""
        clip = self.db.one("SELECT * FROM clips WHERE id=?", (clip_id,))
        meta = loads(clip["metadata"], {})
        prof = self.settings.profile(clip["profile"])
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        base = self.settings.path(self.settings.global_.outputs_dir) / "_PRIVATE_TEST" / prof.output_folder / day
        base.mkdir(parents=True, exist_ok=True)
        name = f"PRIVATE-TEST_{clip['profile']}_{slugify(meta.get('title', 'clip'))}_{clip_id[-6:]}"
        dst = base / f"{name}.mp4"
        shutil.copy2(clip["render_path"], dst)
        if clip["thumbnail_path"] and Path(clip["thumbnail_path"]).exists():
            shutil.copy2(clip["thumbnail_path"], base / f"{name}.jpg")
        record = {**meta, "clip_id": clip_id, "file": str(dst.resolve()),
                  "WARNING": "PRIVATE TEST — NOT FOR PUBLICATION. No permission from the rights holders.",
                  "qc_decision": clip["decision"], "qc_reasons": loads(clip["decision_reasons"], [])}
        (base / f"{name}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"clip_id": clip_id, "profile": prof.display_name, "title": meta.get("title"),
                "duration": round(clip["duration"] or 0, 1), "quality_score": clip["quality_score"],
                "viral_potential_score": clip["viral_score"], "rights_status": clip["rights_status"],
                "format": clip["format"], "file": str(dst.resolve())}

    def summary(self, clip_id: str) -> dict:
        clip = self.db.one("SELECT * FROM clips WHERE id=?", (clip_id,))
        meta = loads(clip["metadata"], {})
        path = clip["export_path"]
        return {"clip_id": clip_id, "profile": self.settings.profile(clip["profile"]).display_name,
                "title": meta.get("title"), "duration": round(clip["duration"] or 0, 1),
                "quality_score": clip["quality_score"], "viral_potential_score": clip["viral_score"],
                "rights_status": clip["rights_status"], "format": clip["format"],
                "file": path if path and Path(path).exists() else None}
