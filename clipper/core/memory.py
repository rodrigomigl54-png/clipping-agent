"""Long-term memory kept in the repository (``memory/``), so a fresh machine/session continues where the
last one stopped: what was already clipped/exported (duplicate prevention), imported performance,
research snapshots and plans (written there directly by the research module) and the style library
(``config/style_examples``). The SQLite database stays the working store; this is its durable copy.
"""
from __future__ import annotations

import json
from pathlib import Path

from .database import Database

TABLES = {
    "export_registry": "clip_id",
    "performance": "id",
    "recommendations": "id",
    "config_changes": "id",
    "format_assignments": "clip_id",
}


def save(db: Database, memory_dir: Path) -> dict[str, int]:
    memory_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for table in TABLES:
        rows = db.query(f"SELECT * FROM {table}")
        (memory_dir / f"{table}.json").write_text(json.dumps(rows, indent=0, ensure_ascii=False, default=str))
        counts[table] = len(rows)
    clips = db.query("SELECT c.id, c.profile, c.source_id, c.decision, c.format, c.layout, c.duration, c.quality_score, "
                     "c.viral_score, c.export_path, c.created_at, k.start, k.\"end\", k.category, k.hook_type "
                     "FROM clips c LEFT JOIN candidates k ON k.id = c.candidate_id")
    (memory_dir / "clips_index.json").write_text(json.dumps(clips, indent=0, ensure_ascii=False, default=str))
    counts["clips_index"] = len(clips)
    return counts


def load(db: Database, memory_dir: Path) -> dict[str, int]:
    """Restore tables that are empty in this database from the durable copy."""
    counts = {}
    for table, key in TABLES.items():
        f = memory_dir / f"{table}.json"
        if not f.exists() or db.one(f"SELECT count(*) n FROM {table}")["n"]:
            continue
        rows = json.loads(f.read_text())
        for r in rows:
            cols = ", ".join(f'"{c}"' for c in r)
            db.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({', '.join('?' for _ in r)})", tuple(r.values()))
        counts[table] = len(rows)
    return counts
