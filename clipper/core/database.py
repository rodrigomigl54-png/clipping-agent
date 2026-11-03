"""SQLite persistence layer.

One database holds every profile's data; rows are always tagged with a ``profile`` column so the
three brands stay independent. History is never deleted: rejected candidates and clips remain.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS system_state (
    key TEXT PRIMARY KEY, value TEXT, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    profile TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- local_file | authorized_url | research_lead
    title TEXT,
    url TEXT,
    local_path TEXT,
    channel TEXT,
    creators TEXT DEFAULT '[]',         -- JSON list of creator names featured
    participants TEXT DEFAULT '[]',     -- JSON list of every rights-relevant participant
    category TEXT,
    published_at TEXT,
    recorded_start TEXT,                -- wall-clock start of recording (cross-stream sync)
    discovered_at TEXT NOT NULL,
    discovery_method TEXT,
    third_party_content TEXT DEFAULT 'unknown',  -- none | unknown | present_cleared | present_uncleared
    facecam_region TEXT,                -- JSON [x,y,w,h] normalised, optional
    stage TEXT NOT NULL DEFAULT 'waiting',
    rights_status TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION',
    rights_reason TEXT,
    content_hash TEXT,
    duration REAL,
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    extra TEXT DEFAULT '{}',
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sources_profile ON sources(profile, stage);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_url ON sources(profile, url) WHERE url IS NOT NULL;

CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_type TEXT NOT NULL,           -- creator | channel | source | category | asset | user_owned
    scope_value TEXT NOT NULL,
    profile TEXT,                       -- NULL = all profiles
    rights_holder TEXT NOT NULL,
    status TEXT NOT NULL,
    evidence TEXT,
    allowed_operations TEXT DEFAULT '[]',
    commercial_use INTEGER DEFAULT 0,
    editing INTEGER DEFAULT 0,
    distribution INTEGER DEFAULT 0,
    download INTEGER DEFAULT 0,
    covers_all_participants INTEGER DEFAULT 0,
    attribution_required INTEGER DEFAULT 0,
    attribution_text TEXT,
    expires_at TEXT,
    restrictions TEXT DEFAULT '{}',
    notes TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_perm_scope ON permissions(scope_type, scope_value);

CREATE TABLE IF NOT EXISTS permission_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_id INTEGER, action TEXT, old TEXT, new TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS transcripts (
    source_id TEXT PRIMARY KEY,
    engine TEXT, language TEXT, word_timing TEXT,
    data TEXT NOT NULL,
    avg_confidence REAL,
    created_at TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
    source_id UNINDEXED, profile UNINDEXED, t_start UNINDEXED, t_end UNINDEXED, text
);

CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    profile TEXT NOT NULL,
    start REAL, "end" REAL, peak REAL,
    total_score REAL,
    scores TEXT, signals TEXT,
    hook_type TEXT, category TEXT,
    transcript_text TEXT, summary TEXT,
    participants TEXT DEFAULT '[]',
    ai_analysis TEXT,
    event_group_id TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    status_reason TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_cand_profile ON candidates(profile, status);

CREATE TABLE IF NOT EXISTS event_groups (
    id TEXT PRIMARY KEY, profile TEXT, label TEXT, members TEXT,
    chosen_candidate_id TEXT, reason TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    profile TEXT NOT NULL,
    source_id TEXT,
    render_path TEXT,
    export_path TEXT,
    thumbnail_path TEXT,
    metadata_path TEXT,
    format TEXT, layout TEXT,
    duration REAL,
    quality_score REAL, viral_score REAL,
    decision TEXT, decision_reasons TEXT,
    qc TEXT, rights_status TEXT, monetization TEXT, metadata TEXT,
    phash TEXT, audio_fp TEXT,
    stage TEXT DEFAULT 'clipping',
    error TEXT,
    created_at TEXT, updated_at TEXT, exported_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_clips_profile ON clips(profile, decision);

CREATE TABLE IF NOT EXISTS export_registry (
    clip_id TEXT PRIMARY KEY,
    profile TEXT, source_id TEXT, start REAL, "end" REAL,
    transcript_text TEXT, phash TEXT, audio_fp TEXT,
    export_path TEXT, exported_at TEXT
);

CREATE TABLE IF NOT EXISTS format_assignments (
    clip_id TEXT PRIMARY KEY, candidate_id TEXT, profile TEXT, format TEXT, assigned_at TEXT
);

CREATE TABLE IF NOT EXISTS performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id TEXT, profile TEXT NOT NULL, platform TEXT,
    external_id TEXT,
    views INTEGER, avg_view_duration REAL, avg_pct_viewed REAL, completion_rate REAL,
    shares INTEGER, comments INTEGER, likes INTEGER, rewatches INTEGER, follows INTEGER,
    published_at TEXT, video_length REAL, format TEXT, topic TEXT, hook_type TEXT,
    creator TEXT, candidate_score REAL,
    import_batch TEXT, imported_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_perf_unique ON performance(profile, platform, clip_id, published_at)
    WHERE clip_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT, kind TEXT, description TEXT, evidence TEXT, proposed_change TEXT,
    status TEXT DEFAULT 'pending', created_at TEXT, decided_at TEXT
);

CREATE TABLE IF NOT EXISTS config_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT, key TEXT, old_value TEXT, new_value TEXT, reason TEXT, origin TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS attention (
    profile TEXT, creator TEXT, multiplier REAL, reason TEXT, updated_at TEXT,
    PRIMARY KEY (profile, creator)
);

CREATE TABLE IF NOT EXISTS research_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT, kind TEXT, started_at TEXT, finished_at TEXT, status TEXT,
    window_start TEXT, window_end TEXT, found INTEGER DEFAULT 0, error TEXT, details TEXT
);

CREATE TABLE IF NOT EXISTS research_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT, creator TEXT, kind TEXT, content TEXT, citations TEXT,
    model TEXT, researched_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_type TEXT, ref_id TEXT, profile TEXT, stage TEXT, level TEXT, message TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ref ON events(ref_type, ref_id);

CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component TEXT, ref_id TEXT, profile TEXT, message TEXT, traceback TEXT,
    resolved INTEGER DEFAULT 0, created_at TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def dumps(v: Any) -> str:
    return json.dumps(v, default=str, ensure_ascii=False)


def loads(v: str | None, default: Any = None) -> Any:
    if v is None or v == "":
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


class Database:
    """Thin, thread-safe wrapper around sqlite3 with transactions and JSON helpers."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False,
                                    isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.init_schema()

    def init_schema(self) -> None:
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)",
                              (str(SCHEMA_VERSION),))

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            else:
                self.conn.execute("COMMIT")

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, params)

    def query(self, sql: str, params: tuple | dict = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | dict = ()) -> dict | None:
        with self._lock:
            r = self.conn.execute(sql, params).fetchone()
            return dict(r) if r else None

    def insert(self, table: str, row: dict) -> int:
        cols = ", ".join(f'"{c}"' for c in row)
        qs = ", ".join("?" for _ in row)
        cur = self.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", tuple(row.values()))
        return cur.lastrowid

    def update(self, table: str, key: str, key_value: Any, values: dict) -> None:
        if not values:
            return
        sets = ", ".join(f'"{c}"=?' for c in values)
        self.execute(f'UPDATE {table} SET {sets} WHERE "{key}"=?', (*values.values(), key_value))

    # ---------------------------------------------------------------- state helpers
    def get_state(self, key: str, default: str | None = None) -> str | None:
        r = self.one("SELECT value FROM system_state WHERE key=?", (key,))
        return r["value"] if r else default

    def set_state(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO system_state(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now_iso()),
        )

    def log_event(self, ref_type: str, ref_id: str, stage: str, message: str,
                  profile: str | None = None, level: str = "info") -> None:
        self.insert("events", {"ref_type": ref_type, "ref_id": ref_id, "profile": profile,
                               "stage": stage, "level": level, "message": message,
                               "created_at": now_iso()})

    def log_error(self, component: str, ref_id: str | None, message: str,
                  tb: str | None = None, profile: str | None = None) -> None:
        self.insert("errors", {"component": component, "ref_id": ref_id, "profile": profile,
                               "message": message[:4000], "traceback": (tb or "")[:20000],
                               "created_at": now_iso()})

    def record_config_change(self, profile: str | None, key: str, old: Any, new: Any,
                             reason: str, origin: str) -> None:
        self.insert("config_changes", {"profile": profile, "key": key, "old_value": dumps(old),
                                       "new_value": dumps(new), "reason": reason,
                                       "origin": origin, "created_at": now_iso()})

    def close(self) -> None:
        with self._lock:
            self.conn.close()
