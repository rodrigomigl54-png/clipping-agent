"""Manual performance-data import (CSV). Missing values stay empty — nothing is invented.

Columns (header names, case-insensitive; only `profile` and either `clip_id` or `video_length` +
`published_at` are required):
clip_id, profile, platform, external_id, published_at, views, avg_view_duration, avg_pct_viewed,
completion_rate, shares, comments, likes, rewatches, follows, video_length, format, topic,
hook_type, creator, candidate_score
"""
from __future__ import annotations

import csv
import uuid
from pathlib import Path

from ..config import Settings
from ..core.database import Database, loads, now_iso

INT_COLS = ("views", "shares", "comments", "likes", "rewatches", "follows")
FLOAT_COLS = ("avg_view_duration", "avg_pct_viewed", "completion_rate", "video_length", "candidate_score")
TEXT_COLS = ("clip_id", "profile", "platform", "external_id", "published_at", "format", "topic", "hook_type", "creator")
ALL_COLS = TEXT_COLS[:5] + INT_COLS[:1] + ("avg_view_duration", "avg_pct_viewed", "completion_rate") + INT_COLS[1:] \
    + ("video_length", "format", "topic", "hook_type", "creator", "candidate_score")
ALIASES = {"avg_percentage_viewed": "avg_pct_viewed", "average_percentage_viewed": "avg_pct_viewed",
           "average_view_duration": "avg_view_duration", "follows_gained": "follows", "subscribers_gained": "follows",
           "length": "video_length", "duration": "video_length"}


class ImportErrorRow(ValueError):
    pass


def _num(v: str, kind):
    v = (v or "").strip().replace(",", "")
    if v == "" or v.lower() in ("na", "n/a", "null", "none", "-"):
        return None
    if v.endswith("%"):
        v = v[:-1]
    x = kind(float(v))
    if x < 0:
        raise ValueError("negative value")
    return x


def write_template(db: Database, settings: Settings, profile: str, path: Path) -> int:
    """CSV pre-filled with facts we know about exported clips; metric cells left blank."""
    settings.profile(profile)
    rows = db.query("SELECT c.id, c.format, c.duration, c.viral_score, c.metadata, k.hook_type, k.category "
                    "FROM clips c JOIN candidates k ON k.id=c.candidate_id WHERE c.profile=? AND c.exported_at IS NOT NULL "
                    "ORDER BY c.exported_at", (profile,))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ALL_COLS))
        w.writeheader()
        for r in rows:
            meta = loads(r["metadata"], {})
            w.writerow({"clip_id": r["id"], "profile": profile, "format": r["format"] or "",
                        "video_length": round(r["duration"] or 0, 1), "hook_type": r["hook_type"] or "",
                        "topic": r["category"] or "", "creator": ", ".join(meta.get("creators", [])),
                        "candidate_score": r["viral_score"]})
    return len(rows)


def import_csv(db: Database, settings: Settings, path: Path, default_profile: str | None = None) -> dict:
    batch = uuid.uuid4().hex[:8]
    ok, errors, updated = 0, [], 0
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        for line_no, raw in enumerate(reader, start=2):
            row = {ALIASES.get(k.strip().lower(), k.strip().lower()): (v or "").strip() for k, v in raw.items() if k}
            try:
                rec: dict = {c: (row.get(c) or None) for c in TEXT_COLS}
                rec["profile"] = (rec["profile"] or default_profile or "").lower()
                settings.profile(rec["profile"])
                for c in INT_COLS:
                    rec[c] = _num(row.get(c, ""), int)
                for c in FLOAT_COLS:
                    rec[c] = _num(row.get(c, ""), float)
                for c in ("avg_pct_viewed", "completion_rate"):
                    if rec[c] is not None and rec[c] <= 1.0 and "%" not in row.get(c, ""):
                        rec[c] = rec[c] * 100  # accept 0.45 as 45 %
                    if rec[c] is not None and rec[c] > 100 and c == "completion_rate":
                        raise ValueError(f"{c} > 100%")
                if rec["clip_id"]:
                    clip = db.one("SELECT c.*, k.hook_type, k.category FROM clips c JOIN candidates k ON "
                                  "k.id=c.candidate_id WHERE c.id=?", (rec["clip_id"],))
                    if not clip:
                        raise ValueError(f"unknown clip_id {rec['clip_id']}")
                    if clip["profile"] != rec["profile"]:
                        raise ValueError(f"clip belongs to profile {clip['profile']}")
                    meta = loads(clip["metadata"], {})
                    # fill descriptive fields from our own records (facts, not guesses)
                    rec["format"] = rec["format"] or clip["format"]
                    rec["video_length"] = rec["video_length"] or clip["duration"]
                    rec["hook_type"] = rec["hook_type"] or clip["hook_type"]
                    rec["topic"] = rec["topic"] or clip["category"]
                    rec["creator"] = rec["creator"] or ", ".join(meta.get("creators", [])) or None
                    rec["candidate_score"] = rec["candidate_score"] if rec["candidate_score"] is not None else clip["viral_score"]
                elif rec["video_length"] is None:
                    raise ValueError("rows without clip_id need video_length")
                rec.update({"import_batch": batch, "imported_at": now_iso()})
                if rec["clip_id"]:
                    exist = db.one("SELECT id FROM performance WHERE profile=? AND IFNULL(platform,'')=IFNULL(?, '') "
                                   "AND clip_id=? AND IFNULL(published_at,'')=IFNULL(?, '')",
                                   (rec["profile"], rec["platform"], rec["clip_id"], rec["published_at"]))
                    if exist:
                        db.update("performance", "id", exist["id"], rec); updated += 1; continue
                db.insert("performance", rec)
                ok += 1
            except (ValueError, KeyError) as e:
                errors.append({"line": line_no, "error": str(e)})
    return {"batch": batch, "inserted": ok, "updated": updated, "errors": errors}
