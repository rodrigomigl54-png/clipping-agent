"""LosPollosTV format experiment (A: split GTA, B: streamer focus, C: hybrid).

Each *distinct* moment gets exactly one format — the same moment is never rendered three times.
Assignment balances sample counts across the formats that are currently available. Formats A and
C are only available when at least one gameplay asset has an APPROVED asset permission.
"""
from __future__ import annotations

import random
from pathlib import Path

from ..config import Settings
from ..core.database import Database, now_iso
from ..core.media import media_info
from .renderer import MediaError

MEDIA_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def licensed_gameplay(settings: Settings, rights_gate, profile: str) -> list[Path]:
    fe = settings.profile(profile).format_experiment
    gdir = settings.path(fe.gameplay_dir if fe else "assets/approved_gameplay")
    out = []
    if not gdir.exists():
        return out
    for f in sorted(gdir.iterdir()):
        if f.suffix.lower() in MEDIA_EXTS and rights_gate.evaluate_asset(asset_key(settings, f), profile).passed:
            out.append(f)
    return out


def asset_key(settings: Settings, path: Path) -> str:
    """Assets are keyed by their path relative to the project root."""
    try:
        return str(path.resolve().relative_to(settings.root.resolve()))
    except ValueError:
        return str(path.resolve())


class FormatExperiment:
    def __init__(self, db: Database, settings: Settings, rights_gate, profile: str = "lospollostv",
                 rng: random.Random | None = None):
        self.db, self.settings, self.gate, self.profile = db, settings, rights_gate, profile
        self.cfg = settings.profile(profile).format_experiment
        self.rng = rng or random.Random()

    def available_formats(self) -> tuple[list[str], list[Path]]:
        gameplay = licensed_gameplay(self.settings, self.gate, self.profile)
        fmts = []
        for name, spec in (self.cfg.formats if self.cfg else {}).items():
            if spec.get("layout") in ("split_gta", "hybrid") and not gameplay:
                continue
            fmts.append(name)
        return fmts, gameplay

    def counts(self) -> dict[str, int]:
        rows = self.db.query("SELECT format, count(*) n FROM format_assignments WHERE profile=? GROUP BY format",
                             (self.profile,))
        return {r["format"]: r["n"] for r in rows}

    def existing(self, candidate_id: str) -> str | None:
        r = self.db.one("SELECT format FROM format_assignments WHERE candidate_id=?", (candidate_id,))
        return r["format"] if r else None

    def assign(self, candidate_id: str, clip_id: str) -> tuple[str, dict, Path | None]:
        fmts, gameplay = self.available_formats()
        if not fmts:
            raise MediaError("no LosPollosTV formats available")
        fmt = self.existing(candidate_id)
        if fmt not in fmts:
            counts = self.counts()
            low = min(counts.get(f, 0) for f in fmts)
            fmt = self.rng.choice([f for f in fmts if counts.get(f, 0) == low])
        spec = dict(self.cfg.formats[fmt])
        gp = self.rng.choice(gameplay) if spec.get("layout") in ("split_gta", "hybrid") else None
        self.db.execute("INSERT OR REPLACE INTO format_assignments(clip_id,candidate_id,profile,format,assigned_at) "
                        "VALUES(?,?,?,?,?)", (clip_id, candidate_id, self.profile, fmt, now_iso()))
        return fmt, spec, gp

    def gameplay_offset(self, gp: Path) -> float:
        d = media_info(gp)["duration"]
        return self.rng.uniform(0, max(0.0, d - 5))
