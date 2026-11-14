"""Command-line interface — the operating surface used from Claude Code.

Run ``python main.py --help`` for all commands.
"""
from __future__ import annotations

import argparse
import json
import re
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from .config import PROFILE_IDS, load_settings, set_override
from .core.database import Database, dumps, loads, now_iso
from .core.logger import setup_logging


# ----------------------------------------------------------------------------- utils
def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


def table(rows: list[dict], cols: list[str], widths: dict[str, int] | None = None) -> str:
    if not rows:
        return "(none)"
    widths = widths or {}
    def cell(v, c):
        s = "" if v is None else (f"{v:.1f}" if isinstance(v, float) else str(v))
        w = widths.get(c, 40)
        return s if len(s) <= w else s[: w - 1] + "…"
    data = [[cell(r.get(c), c) for c in cols] for r in rows]
    ws = [max(len(c), *(len(d[i]) for d in data)) for i, c in enumerate(cols)]
    line = "  ".join(c.ljust(ws[i]) for i, c in enumerate(cols))
    sep = "  ".join("-" * w for w in ws)
    return "\n".join([line, sep] + ["  ".join(d[i].ljust(ws[i]) for i in range(len(cols))) for d in data])


def jprint(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str, ensure_ascii=False))


class App:
    def __init__(self, root: Path | None = None):
        self.settings = load_settings(root)
        load_dotenv(self.settings.root / ".env")
        setup_logging(self.settings.path(self.settings.global_.logs_dir))
        self._db: Database | None = None
        self._orch = None

    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = Database(self.settings.db_path)
        return self._db

    @property
    def orch(self):
        if self._orch is None:
            from .core.orchestrator import Orchestrator
            self._orch = Orchestrator(self.settings, self.db)
        return self._orch

    def profiles(self, arg: str | None) -> list[str]:
        if not arg or arg == "all":
            return list(self.settings.profiles)
        self.settings.profile(arg)
        return [arg.lower()]


# ----------------------------------------------------------------------------- commands
def cmd_doctor(app: App, a) -> int:
    from .core.media import require_binaries
    ok = True
    print(f"Python        {sys.version.split()[0]}  {'OK' if sys.version_info >= (3, 12) else 'needs 3.12+'}")
    ok &= sys.version_info >= (3, 12)
    for b, p in require_binaries().items():
        print(f"{b:<13} {p or 'MISSING'}")
        ok &= bool(p)
    for mod in ("cv2", "numpy", "pydantic", "yaml", "PIL", "faster_whisper", "google.genai"):
        try:
            __import__(mod)
            print(f"{mod:<13} OK")
        except ImportError:
            print(f"{mod:<13} MISSING{' (required)' if mod not in ('faster_whisper', 'google.genai') else ' (optional)'}")
            ok &= mod in ("faster_whisper", "google.genai")
    du = shutil.disk_usage(app.settings.root)
    print(f"Disk free     {du.free / 1e9:.1f} GB")
    key = app.settings.global_.google_ai.api_key_env
    print(f"Gemini key    {'set' if os.environ.get(key) else f'not set ({key}) — AI research disabled'}")
    wm = os.environ.get(app.settings.global_.transcription.model_path_env)
    print(f"Whisper model {wm or app.settings.global_.transcription.model_size + ' (downloaded on first use)'}")
    print(f"Database      {app.settings.db_path}")
    print("Result:", "READY" if ok else "MISSING REQUIREMENTS")
    return 0 if ok else 1


def cmd_init(app: App, a) -> int:
    app.db  # creates schema
    s = app.settings
    for pid, prof in s.profiles.items():
        (s.path(s.global_.sources_dir) / "inbox" / pid).mkdir(parents=True, exist_ok=True)
        (s.path(s.global_.outputs_dir) / prof.output_folder).mkdir(parents=True, exist_ok=True)
    for d in ("assets/fonts", "assets/approved_gameplay", "work", "logs"):
        s.path(d).mkdir(parents=True, exist_ok=True)
    print(f"Initialised database at {s.db_path} and folders under {s.root}")
    return 0


def cmd_status(app: App, a) -> int:
    from .core.scheduler import RunnerLock
    db = app.db
    pid = RunnerLock(app.settings.work_dir / ".runner.lock").holder()
    print(f"Runner:        {'RUNNING (pid %s)' % pid if pid else 'not running'}")
    print(f"Paused:        {'yes' if db.get_state('paused') == '1' else 'no'}")
    print(f"Activity:      {db.get_state('activity', 'idle')}")
    print(f"Heartbeat:     {db.get_state('heartbeat', '-')}   last cycle: {db.get_state('last_cycle', '-')}")
    print(f"Gemini:        {'enabled' if app.orch.gemini.available() else 'disabled (no API key)'}")
    for pid_, prof in app.settings.profiles.items():
        src = {r["stage"]: r["n"] for r in db.query("SELECT stage, count(*) n FROM sources WHERE profile=? GROUP BY stage", (pid_,))}
        cand = {r["status"]: r["n"] for r in db.query("SELECT status, count(*) n FROM candidates WHERE profile=? GROUP BY status", (pid_,))}
        clips = {r["decision"] or "in_progress": r["n"] for r in db.query("SELECT decision, count(*) n FROM clips WHERE profile=? GROUP BY decision", (pid_,))}
        exp = db.one("SELECT count(*) n FROM clips WHERE profile=? AND exported_at IS NOT NULL", (pid_,))["n"]
        print(f"\n[{prof.display_name}] threshold={prof.min_quality_threshold} duration={prof.duration.min_seconds:g}-{prof.duration.max_seconds:g}s"
              f"  last research: {db.get_state('last_research:' + pid_, '-')}")
        print(f"  sources:    {src or '-'}")
        print(f"  candidates: {cand or '-'}")
        print(f"  clips:      {clips or '-'}   exported files: {exp}")
    errs = db.one("SELECT count(*) n FROM errors WHERE resolved=0")["n"]
    print(f"\nUnresolved errors: {errs}  (python main.py errors)")
    return 0


def cmd_start(app: App, a) -> int:
    from .core.scheduler import Scheduler
    sched = Scheduler(app.orch, a.interval, app.profiles(a.profile) if a.profile else None)
    print("Clipping machine started. Runs while this computer is on and this process is running. Ctrl+C stops cleanly.")
    return sched.run(max_cycles=1 if a.once else None)


def cmd_pause(app: App, a) -> int:
    app.db.set_state("paused", "1"); print("Research and processing paused (current step finishes first).")
    return 0


def cmd_resume(app: App, a) -> int:
    app.db.set_state("paused", "0"); app.db.set_state("run_now", "1"); print("Resumed.")
    return 0


def cmd_research(app: App, a) -> int:
    for pid in app.profiles(a.profile):
        res = app.orch.research.research_profile(pid, use_gemini=a.gemini)
        print(f"[{pid}]")
        for r in res["results"]:
            print(f"  {r['kind']:<14} {r['status']:<8} found={r.get('found', 0)} {r.get('error', '') or ''}")
    blocked = app.db.query("SELECT id, profile, title, rights_status, rights_reason FROM sources WHERE stage='blocked_rights'")
    if blocked:
        print("\nSources awaiting rights verification (not processed):")
        print(table(blocked, ["id", "profile", "title", "rights_status", "rights_reason"], {"rights_reason": 70}))
    return 0


def cmd_process(app: App, a) -> int:
    app.orch.recover()
    for pid in app.profiles(a.profile):
        res = app.orch.process_profile(pid, max_clips=a.max_clips)
        print(f"[{pid}] sources processed: {len(res['sources'])}, event groups: {len(res['events'])}, clip attempts: {len(res['clips'])}")
        for s in res["sources"]:
            print(f"  source {s['source_id']}: {s['stage']} {s.get('error') or s.get('skipped') or ''}")
        for c in res["clips"]:
            _print_clip_result(c)
    return 0


def _print_clip_result(c: dict) -> None:
    if c.get("export"):
        e = c["export"]
        print(f"  ✔ EXPORTED [{e['profile']}] {e['title']}\n     duration {e['duration']}s | quality {e['quality_score']} | "
              f"viral potential {e['viral_potential_score']} | rights {e['rights_status']}\n     file: {e['file']}")
    elif c.get("decision") == "NEEDS_REVIEW":
        print(f"  ? NEEDS_REVIEW {c['clip_id']}: {'; '.join(c['reasons'])[:300]}")
    elif c.get("decision") == "REJECTED":
        print(f"  ✘ REJECTED {c['clip_id']}: {'; '.join(c['reasons'])[:300]}")
    elif c.get("status") == "duplicate":
        print(f"  = duplicate candidate {c['candidate_id']}: {c['reason']}")
    else:
        print(f"  ! FAILED {c.get('clip_id')}: {c.get('error', '')[:300]}")


def cmd_candidates(app: App, a) -> int:
    sql, p = "SELECT id, profile, source_id, start, \"end\", total_score, hook_type, category, status, summary FROM candidates WHERE 1=1", []
    if a.profile:
        sql += " AND profile=?"; p.append(a.profile)
    if a.status:
        sql += " AND status=?"; p.append(a.status)
    rows = app.db.query(sql + " ORDER BY created_at DESC, total_score DESC LIMIT ?", (*p, a.limit))
    for r in rows:
        r["dur"] = round(r["end"] - r["start"], 1)
    print(table(rows, ["id", "profile", "total_score", "dur", "hook_type", "category", "status", "summary"], {"summary": 60}))
    return 0


def cmd_candidate(app: App, a) -> int:
    r = app.db.one("SELECT * FROM candidates WHERE id=?", (a.id,))
    if not r:
        print("not found"); return 1
    for k in ("scores", "signals", "participants", "ai_analysis"):
        r[k] = loads(r[k])
    jprint(r)
    return 0


def cmd_clips(app: App, a) -> int:
    sql, p = "SELECT id, profile, decision, stage, format, layout, duration, quality_score, viral_score, rights_status, export_path, render_path, metadata FROM clips WHERE 1=1", []
    if a.profile:
        sql += " AND profile=?"; p.append(a.profile)
    if a.decision:
        sql += " AND decision=?"; p.append(a.decision.upper())
    rows = app.db.query(sql + " ORDER BY created_at DESC LIMIT ?", (*p, a.limit))
    for r in rows:
        r["title"] = loads(r["metadata"], {}).get("title")
        r["file"] = r["export_path"] if r["export_path"] and Path(r["export_path"]).exists() else (
            r["render_path"] if r["decision"] == "NEEDS_REVIEW" and r["render_path"] and Path(r["render_path"]).exists() else None)
    print(table(rows, ["id", "profile", "decision", "title", "duration", "quality_score", "viral_score", "rights_status", "format", "file"],
                {"title": 45, "file": 400}))
    return 0


def cmd_clip(app: App, a) -> int:
    r = app.db.one("SELECT * FROM clips WHERE id=?", (a.id,))
    if not r:
        print("not found"); return 1
    for k in ("decision_reasons", "qc", "monetization", "metadata"):
        r[k] = loads(r[k])
    r.pop("phash", None); r.pop("audio_fp", None)
    jprint(r)
    return 0


def cmd_review(app: App, a) -> int:
    if a.action == "list":
        rows = app.db.query("SELECT id, profile, render_path, decision_reasons, metadata FROM clips WHERE decision='NEEDS_REVIEW' ORDER BY created_at")
        for r in rows:
            r["title"] = loads(r["metadata"], {}).get("title")
            r["reasons"] = "; ".join(loads(r["decision_reasons"], []))
        print(table(rows, ["id", "profile", "title", "reasons", "render_path"], {"reasons": 80, "render_path": 100}))
    elif a.action == "approve":
        try:
            e = app.orch.approve_review(a.id, a.note or "")
            _print_clip_result({"export": e})
        except ValueError as e:
            print(f"Cannot approve: {e}"); return 1
    elif a.action == "reject":
        app.orch.reject_review(a.id, a.note or ""); print(f"{a.id} rejected (history kept).")
    return 0


def cmd_sources(app: App, a) -> int:
    store = app.orch.store
    if a.action == "list":
        rows = store.list(a.profile, rights_status=a.rights)
        print(table(rows, ["id", "profile", "kind", "title", "stage", "rights_status", "published_at", "rights_reason"],
                    {"title": 40, "rights_reason": 70}))
    elif a.action == "show":
        r = store.get(a.id)
        if not r:
            print("not found"); return 1
        for k in ("creators", "participants", "extra", "facecam_region"):
            r[k] = loads(r[k])
        jprint(r)
    elif a.action == "add":
        if not a.file and not a.url:
            print("--file or --url required"); return 1
        kind = "local_file" if a.file else ("authorized_url" if a.direct_download else "research_lead")
        path = str(Path(a.file).resolve()) if a.file else None
        if path and not Path(path).is_file():
            print(f"file not found: {path}"); return 1
        sid, new = store.register(
            profile=a.profile, kind=kind, key=f"file:{path}" if path else f"url:{a.url}", title=a.title or (Path(path).stem if path else None),
            url=a.url, local_path=path, channel=a.channel, creators=_csv(a.creators), participants=_csv(a.participants),
            category=a.category, published_at=a.published, recorded_start=a.recorded_start, discovery_method="manual",
            third_party_content=a.third_party or "unknown", facecam_region=[float(x) for x in a.facecam.split(",")] if a.facecam else None,
            extra={"ignore_window": a.ignore_window})
        d = app.orch.gate.evaluate(store.get(sid), "processing")
        store.update(sid, rights_status=d.status, rights_reason=d.summary(), stage="waiting" if d.passed else "blocked_rights")
        print(f"{'Registered' if new else 'Already indexed'}: {sid}\nRights: {d.summary()}")
    elif a.action == "attach":
        r = store.get(a.id)
        p = Path(a.file).resolve()
        if not r or not p.is_file():
            print("source or file not found"); return 1
        store.update(a.id, local_path=str(p), kind="local_file" if r["kind"] == "research_lead" else r["kind"])
        print(f"Attached {p} to {a.id}. Media is still only processed if the rights gate passes.")
    elif a.action == "set":
        vals = {}
        if a.participants is not None:
            vals["participants"] = _csv(a.participants)
        if a.creators is not None:
            vals["creators"] = _csv(a.creators)
        if a.third_party:
            vals["third_party_content"] = a.third_party
        if a.facecam:
            vals["facecam_region"] = [float(x) for x in a.facecam.split(",")]
        if a.category:
            vals["category"] = a.category
        if a.recorded_start:
            vals["recorded_start"] = a.recorded_start
        store.update(a.id, **vals)
        if store.get(a.id)["stage"] in ("blocked_rights", "failed"):
            store.update(a.id, stage="waiting", attempts=0)
        print(f"Updated {a.id}: {list(vals)}")
    return 0


def _csv(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def cmd_rights(app: App, a) -> int:
    from .rights.permission_registry import Permission
    reg = app.orch.registry
    if a.action == "list":
        rows = [{**p.__dict__, "ops": ",".join(o for o, f in (("edit", p.editing), ("distribute", p.distribution),
                                                                ("commercial", p.commercial_use), ("download", p.download)) if f)}
                for p in reg.list(a.scope, a.status, a.profile)]
        print(table(rows, ["id", "scope_type", "scope_value", "profile", "rights_holder", "status", "ops", "expires_at", "evidence"],
                    {"evidence": 50}))
        pend = app.db.query("SELECT id, profile, title, rights_status, rights_reason FROM sources WHERE rights_status NOT IN ('APPROVED','APPROVED_WITH_CONDITIONS')")
        print("\nSources not cleared for processing/export:")
        print(table(pend, ["id", "profile", "title", "rights_status", "rights_reason"], {"rights_reason": 90}))
    elif a.action == "add":
        ops = _csv(a.ops)
        p = Permission(scope_type=a.scope, scope_value=a.value, rights_holder=a.holder, status=a.status.upper(),
                       evidence=a.evidence, allowed_operations=[o for o in ops if o in ("download_or_import", "edit", "distribute", "commercial_use", "clip")],
                       commercial_use="commercial_use" in ops, editing="edit" in ops, distribution="distribute" in ops,
                       download="download_or_import" in ops, covers_all_participants=a.all_participants,
                       attribution_required=bool(a.attribution), attribution_text=a.attribution, expires_at=a.expires,
                       restrictions=json.loads(a.restrictions) if a.restrictions else {}, profile=a.profile, notes=a.notes)
        try:
            pid = reg.add(p)
        except ValueError as e:
            print(f"Rejected: {e}"); return 1
        print(f"Permission #{pid} recorded.")
        if app.orch.research.rights_gate:
            for r in app.orch.research.refresh_rights():
                print(f"  re-checked {r['source_id']}: {r['status']}")
    elif a.action == "set-status":
        try:
            reg.set_status(a.id, a.status.upper(), a.evidence, a.notes)
        except (ValueError, KeyError) as e:
            print(f"Rejected: {e}"); return 1
        print(f"Permission #{a.id} → {a.status.upper()}")
        app.orch.research.refresh_rights()
    elif a.action == "check":
        src = app.orch.store.get(a.id)
        if not src:
            print("source not found"); return 1
        for stage in ("processing", "export"):
            d = app.orch.gate.evaluate(src, stage)
            print(f"{stage:<11} {d.status}")
            for r in d.reasons:
                print(f"   - {r}")
            for at in d.attribution:
                print(f"   attribution: {at}")
    elif a.action == "history":
        print(table(reg.history(a.id), ["id", "action", "old", "new", "created_at"], {"new": 80}))
    return 0


def cmd_errors(app: App, a) -> int:
    rows = app.db.query("SELECT id, component, ref_id, profile, message, created_at FROM errors WHERE resolved=? ORDER BY id DESC LIMIT ?",
                        (1 if a.resolved else 0, a.limit))
    print(table(rows, ["id", "created_at", "component", "ref_id", "profile", "message"], {"message": 100}))
    if a.clear:
        app.db.execute("UPDATE errors SET resolved=1 WHERE resolved=0"); print("marked resolved")
    return 0


def cmd_analytics(app: App, a) -> int:
    from .analytics import analytics_engine, performance_import
    if a.action == "import":
        res = performance_import.import_csv(app.db, app.settings, Path(a.file), a.profile)
        print(f"batch {res['batch']}: inserted {res['inserted']}, updated {res['updated']}, errors {len(res['errors'])}")
        for e in res["errors"]:
            print(f"  line {e['line']}: {e['error']}")
        return 0 if not res["errors"] else 2
    if a.action == "template":
        out = Path(a.file or f"analytics_{a.profile}_template.csv")
        n = performance_import.write_template(app.db, app.settings, a.profile, out)
        print(f"Wrote {out.resolve()} with {n} exported clips. Fill in the metrics you have; leave unknown cells blank.")
        return 0
    for pid in app.profiles(a.profile):
        ov = analytics_engine.overview(app.db, pid)
        print(f"\n[{app.settings.profile(pid).display_name}] clips with performance data: {ov['clips_with_data']} "
              f"(median views {ov['median_views']})")
        if not ov["clips_with_data"]:
            print("  No data yet. Export a template: python main.py analytics template --profile", pid)
            continue
        print(f"  AI score vs. real retention (Spearman): {ov['score_vs_retention_spearman']}")
        for key in ("by_format", "by_length", "by_hook_type", "by_topic", "by_creator"):
            dim = {"by_format": "format", "by_length": "length_bucket", "by_hook_type": "hook_type",
                   "by_topic": "topic", "by_creator": "creator"}[key]
            print(f"\n  {key.replace('_', ' ')}:")
            print("  " + table(ov[key], [dim, "n", "avg_pct_viewed", "retention_index", "views_index", "shares_per_k",
                                        "follows_per_k", "avg_candidate_score"]).replace("\n", "\n  "))
    return 0


def cmd_compare_formats(app: App, a) -> int:
    from .analytics.format_comparison import compare_formats
    res = compare_formats(app.db, app.settings)
    rows = [{"format": f, **v} for f, v in res["formats"].items()]
    print(table(rows, ["format", "n", "avg_pct_viewed", "adjusted", "adjusted_se", "avg_view_duration", "completion_rate",
                       "shares_per_k", "comments_per_k", "follows_per_k"]))
    print(f"\nVerdict: {res['verdict']['status']} — {res['verdict']['message']}")
    exp_counts = {r["format"]: r["n"] for r in app.db.query("SELECT format, count(*) n FROM format_assignments GROUP BY format")}
    print(f"Clips assigned per format so far: {exp_counts or '-'}")
    for c in res["caveats"]:
        print(f"  note: {c}")
    return 0


def cmd_learning(app: App, a) -> int:
    from .analytics.learning_engine import LearningEngine
    le = LearningEngine(app.db, app.settings)
    if a.action == "analyze":
        for pid in app.profiles(a.profile):
            print(f"[{pid}]", le.analyze(pid))
    elif a.action == "list":
        print(table(le.list(a.profile, a.status), ["id", "profile", "kind", "status", "description", "created_at"], {"description": 100}))
    elif a.action == "apply":
        jprint(le.apply(a.id))
    elif a.action == "dismiss":
        le.dismiss(a.id); print("dismissed")
    elif a.action == "history":
        print(table(app.db.query("SELECT * FROM config_changes ORDER BY id DESC LIMIT 50"),
                    ["id", "created_at", "profile", "key", "old_value", "new_value", "origin", "reason"], {"reason": 70}))
    return 0


def _change(app: App, profile: str, path: list[str], value, reason: str) -> int:
    cdir = app.settings.root / "config"
    old = set_override(["profiles", profile] + path, value, cdir)
    try:
        load_settings(app.settings.root)
    except Exception as e:
        set_override(["profiles", profile] + path, old, cdir)
        print(f"Invalid value, change reverted: {e}")
        return 1
    app.db.record_config_change(profile, ".".join(path), old, value, reason, "cli")
    print(f"{profile}.{'.'.join(path)} = {value} (logged in config history)")
    return 0


def cmd_set_threshold(app: App, a) -> int:
    app.settings.profile(a.profile)
    return _change(app, a.profile, ["min_quality_threshold"], float(a.value), a.reason or "manual change")


def cmd_set_duration(app: App, a) -> int:
    prof = app.settings.profile(a.profile)
    rc = 0
    if a.min is not None:
        rc |= _change(app, a.profile, ["duration", "min_seconds"], float(a.min), a.reason or "manual change")
    if a.max is not None:
        rc |= _change(app, a.profile, ["duration", "max_seconds"], float(a.max), a.reason or "manual change")
    if a.min is None and a.max is None:
        print(f"{a.profile}: {prof.duration.min_seconds}-{prof.duration.max_seconds}s")
    return rc


def cmd_search(app: App, a) -> int:
    rows = app.orch.transcription.search(a.query, a.profile, a.limit)
    print(table(rows, ["source_id", "profile", "t_start", "t_end", "text"], {"text": 100}))
    return 0


def cmd_attention(app: App, a) -> int:
    from .research.attention import AttentionAllocator
    al = AttentionAllocator(app.db, app.settings)
    for pid in app.profiles(a.profile):
        w = al.weights(pid)
        rows = [{"creator": c.name, "initial_priority": c.priority, "multiplier": al.multiplier(pid, c.name),
                 "attention_share": f"{w[c.name]:.1%}"} for c in app.settings.profile(pid).creators]
        print(f"[{pid}] (attention weights, not clip quotas)")
        print(table(rows, ["creator", "initial_priority", "multiplier", "attention_share"]))
    return 0


def cmd_research_notes(app: App, a) -> int:
    rows = app.db.query("SELECT id, profile, creator, kind, model, researched_at, content, citations FROM research_notes "
                        + ("WHERE profile=? " if a.profile else "") + "ORDER BY id DESC LIMIT ?",
                        ((a.profile, a.limit) if a.profile else (a.limit,)))
    for r in rows:
        r["citations"] = len(loads(r["citations"], []))
    print(table(rows, ["id", "profile", "creator", "kind", "citations", "researched_at", "content"], {"content": 90}))
    return 0


def cmd_private_test(app: App, a) -> int:
    print("PRIVATE TEST: clips go to outputs/_PRIVATE_TEST/ and must NOT be published (no rights approval).")
    res = app.orch.private_test(a.file, a.profile, _csv(a.creators), a.title, a.max_clips)
    print(f"source: {res['source'].get('stage')} {res['source'].get('error') or ''}")
    for c in res["clips"]:
        t = c.get("private_test")
        if t:
            print(f"  ▶ [{t['profile']}] {t['title']}\n     {t['duration']}s | quality {t['quality_score']} | "
                  f"viral potential {t['viral_potential_score']} | format {t['format'] or '-'}\n     file: {t['file']}")
        else:
            print(f"  ! {c.get('clip_id') or c.get('candidate_id')}: {c.get('error') or c.get('reason') or '; '.join(c.get('reasons', []))[:200]}")
    return 0


def cmd_hype(app: App, a) -> int:
    """Hype edits. make: beat-grid edit (4:5). learn / learn-trending: learn the exact template of a viral edit.
    render: rebuild one template with our footage. daily: the day's edits from the best templates."""
    import json as _json
    from datetime import date as _date, datetime as _dt, timezone as _tz
    from .editing import hype_editor as H
    from .editing import template_edit as T
    prof = app.settings.profile(a.profile)
    hcfg = prof.hype or {}
    root = app.settings.root
    day = _dt.now(_tz.utc).strftime("%Y-%m-%d")
    outdir = app.settings.path(app.settings.global_.outputs_dir) / "_PRIVATE_TEST" / prof.output_folder / day
    refs_dir = app.settings.path(hcfg.get("refs_dir", "assets/hype_refs"))
    footage = sorted(str(p) for p in app.settings.path(hcfg.get("footage_dir", f"assets/footage/{prof.id}")).glob("*.mp4"))
    days = H.days_until(prof.release_date) if prof.release_date else 0

    if a.action == "templates":
        tpls = H.load_templates(app.settings.path("config/style_examples") / f"{prof.id}_hype_measurements.json",
                                hcfg.get("templates", {}))
        print("beat grids (hype make):")
        for t in tpls.values():
            print(f"  {t.id}: '{t.sound}' ({t.sound_author}) {t.bpm:.0f} BPM, drop {t.drop:.2f}s  {t.reference}")
        print("learned templates (hype render / daily), best first:")
        for t in sorted(T.list_templates(root), key=T.template_score, reverse=True):
            print(f"  {t['id']}: {t.get('creator', '?')} {t.get('views') or t.get('views_when_learned') or '?'} views | "
                  f"{t['orientation']} {t['duration']}s {len(t['cuts'])} cuts {t.get('bpm', '?')} BPM | sound "
                  f"'{t.get('sound', '?')}' | text events {len(t.get('text', []))}  {t.get('reference', '')}")
        return 0

    if a.action in ("learn", "learn-trending"):
        from .research.trends import TikTokPublic
        jobs = []
        if a.action == "learn":
            if not a.sources:
                print("usage: hype learn <tiktok url | video file> [--id ID]"); return 1
            src = a.sources[0]
            m = re.search(r"tiktok\.com/@([^/]+)/video/(\d+)", src)
            jobs.append({"file": None if m else src, "author": m.group(1) if m else None, "vid": m.group(2) if m else None,
                         "id": a.id})
        else:
            snaps = sorted((app.settings.path("memory/research")).glob("snapshot_*.json"))
            if not snaps:
                print("no research snapshot: run `trends research` first"); return 1
            have = {t.get("video_id") for t in T.list_templates(root)}
            vids = [v for v in _json.loads(snaps[-1].read_text()).get("tiktok", [])
                    if v.get("type") == "hype_edit" and v.get("id") not in have]
            vids.sort(key=lambda v: (v.get("velocity") or 0) * (1 + 0.3 * (v.get("outlier") or 1)), reverse=True)
            jobs = [{"file": None, "author": v["author"], "vid": v["id"], "meta": v} for v in vids[:a.top]]
        tt = TikTokPublic()
        for j in jobs:
            meta = j.get("meta") or {}
            if j["file"] is None and not meta:
                meta = tt.video(j["author"], j["vid"]) or {}
            tid = j.get("id") or (f"{j['author']}_{j['vid'][-6:]}".replace(".", "_") if j["vid"] else Path(j["file"]).stem)
            ref = Path(j["file"]) if j["file"] else refs_dir / f"{tid}.mp4"
            try:
                if j["file"] is None and not ref.exists():
                    tt.download(j["author"], j["vid"], ref)
                tpl = T.learn_template(str(ref), tid)
                if len(tpl["cuts"]) < 6:
                    print(f"  - {tid}: only {len(tpl['cuts'])} cuts — not a beat edit, skipped"); continue
                snd = meta.get("sound") or {}
                tpl.update({"reference": meta.get("url"), "video_id": j.get("vid"), "creator": meta.get("author") or j.get("author"),
                            "views": meta.get("views"), "created": meta.get("created"), "outlier": meta.get("outlier"),
                            "sound": snd.get("title"), "sound_author": snd.get("author"), "category": "hype_edit",
                            "reference_file": ref.name})
                if not a.no_ai and app.orch.gemini.available():
                    try:
                        tpl["text"] = T.learn_text(str(ref), tpl, app.orch.gemini)
                        handle = (tpl.get("creator") or "").lower().replace(".", "").replace("_", "")
                        tpl["text"] = [e for e in tpl["text"] if not (handle and handle[-6:] in
                                       (e.get("text") or "").lower().replace(".", "").replace("_", "").replace(" ", ""))]
                        # lines other than countdowns are the other creator's words: check they fit our footage
                        tpl["text_review"] = any(e["type"] == "line" and "{days}" not in e["text"] for e in tpl["text"])
                    except Exception as e:                      # quota / model errors: template still usable
                        tpl["text_error"] = str(e)[:200]
                T.save_template(root, tpl)
                print(f"  + {tid}: {tpl['orientation']} {tpl['duration']}s, {len(tpl['cuts'])} cuts, {tpl.get('bpm', '?')} BPM, "
                      f"{len(tpl.get('text', []))} text events, sound '{tpl.get('sound')}'")
            except Exception as e:
                print(f"  ! {tid}: {e}")
        return 0

    if a.action in ("render", "daily"):
        if not footage:
            print(f"no footage in {hcfg.get('footage_dir', f'assets/footage/{prof.id}')} (official trailers): import it first")
            return 1
        tpls = sorted(T.list_templates(root), key=T.template_score, reverse=True)
        if a.action == "render":
            tpls = [t for t in tpls if t["id"] in (a.sources or [])] or tpls[:1]
        else:
            tpls = [t for t in tpls if not t.get("disabled")
                    and not (days < 1 and any(e.get("type") == "counter" for e in t.get("text", [])))]
            want = a.n or int(hcfg.get("daily", 3))
            tpls = [tpls[i % len(tpls)] for i in range(want)] if tpls else []   # cycle: each pass uses fresh shots
        used_f = app.settings.path("memory/hype_used.json")
        used = _json.loads(used_f.read_text()) if used_f.exists() else {}
        from datetime import timedelta as _td
        cutoff = (_date.today() - _td(days=3)).isoformat()
        recent = {(x[0], x[1]) for d, xs in used.items() if d >= cutoff for x in xs}
        made = []
        for t in tpls:
            ref = refs_dir / t.get("reference_file", f"{t['id']}.mp4")
            if not ref.exists() and t.get("video_id") and t.get("creator"):
                try:
                    from .research.trends import TikTokPublic
                    TikTokPublic.download(t["creator"], t["video_id"], ref)
                except Exception as e:
                    print(f"  (no reference audio for {t['id']}: {e})")
            name = f"PRIVATE-TEST_{prof.id}_{t['id']}_{days}d_{_dt.now(_tz.utc).strftime('%H%M%S')}"
            out = outdir / f"{name}.mp4"
            print(f"rendering {t['id']} ({t.get('creator')}, sound '{t.get('sound')}')…")
            try:
                fdir = t.get("footage") or prof.id                    # e.g. Niko Bellic edits use GTA IV footage
                tfoot = footage if fdir == prof.id else sorted(str(p) for p in app.settings.path(f"assets/footage/{fdir}").glob("*.mp4"))
                res = T.make_template_edit(t, tfoot, out, {"days": days, "watermark": hcfg.get("watermark", "")}, audio_from=str(ref) if ref.exists() else None,
                                           shot_cache=app.settings.path("data/shot_cache"), exclude=recent,
                                           tags_dir=app.settings.path(f"config/footage_tags/{fdir}"),
                                           gemini=app.orch.gemini, vertical_out=bool(hcfg.get("all_vertical", True)))
            except Exception as e:
                print(f"  ! {t['id']}: {e}"); continue
            mu = float(app.settings.quality.get("technical", {}).get("max_upscale", 2.0))
            res["qc"] = {"sharp_enough": res["upscale"] <= mu, "source_720p_or_better": res["source_height"] >= 720}
            res["music"] = {"sound": t.get("sound"), "artist": t.get("sound_author"), "reference_post": t.get("reference"),
                            "bpm": t.get("bpm"), "how": [
                                "TikTok: open the reference post, tap the sound -> Use this sound.",
                                "Start the sound at 0:00 (do not trim): every cut sits on the same frame as in the reference.",
                                "Upload the *_silent.mp4 file and keep the original-video volume at 0."]}
            res["post"] = _post_kit(app, t, days)
            from .metadata.post_kit import as_text as _kit_text
            out.with_suffix(".post.txt").write_text(_kit_text(res["post"], t["id"]), encoding="utf-8")
            res["WARNING"] = "PRIVATE TEST — not an approved export; official trailer footage (rights not recorded)."
            if t.get("text_review"):
                res["text_review"] = "on-screen lines copied from the reference: check they are true for this footage"
            out.with_suffix(".json").write_text(_json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
            used.setdefault(day, []).extend(res["used_shots"])
            recent |= {(x[0], x[1]) for x in res["used_shots"]}          # next video avoids these shots
            made.append(res)
            ok = all(res["qc"].values())
            print(f"  ▶ {res.get('preview_with_sound') or res['file']}\n    {res['duration']}s {res['size']} | "
                  f"upscale {res['upscale']}x | QC {'PASS' if ok else 'FAIL'} | sound '{t.get('sound')}' from 0:00"
                  + (" | CHECK TEXT" if t.get("text_review") else ""))
            print(f"    post: {res['post']['tiktok']['caption']}")
        used_f.parent.mkdir(parents=True, exist_ok=True)
        used_f.write_text(_json.dumps({d: v for d, v in sorted(used.items())[-7:]}, indent=0))
        return 0 if made else 1

    # make: the original beat-grid edit (4:5 picture + bands, silent)
    tpls = H.load_templates(app.settings.path("config/style_examples") / f"{prof.id}_hype_measurements.json",
                            hcfg.get("templates", {}))
    if not a.sources:
        print("usage: hype make <video> [<video> ...] --profile gta6 [--template ID]"); return 1
    tpl = tpls[a.template or hcfg.get("default_template") or next(iter(tpls))]
    text = H.countdown_text(prof.release_date, _date.today()) if prof.release_date else \
        H.HypeText(opener=a.opener or "", main=a.main or "", final=a.final or "")
    for k in ("opener", "main", "final"):
        if getattr(a, k):
            setattr(text, k, getattr(a, k))
    text.watermark = hcfg.get("watermark", "") or ""
    name = f"PRIVATE-TEST_{prof.id}_hype_{text.main.lower().replace(' ', '-')}_{_dt.now(_tz.utc).strftime('%H%M%S')}"
    out = outdir / f"{name}.mp4"
    res = H.make_hype_edit([str(s) for s in a.sources], tpl, text, out)
    mu = float(app.settings.quality.get("technical", {}).get("max_upscale", 2.0))
    res["qc"] = {"decision": "PASS" if res["upscale"] <= mu else "FAIL"}
    res["WARNING"] = "PRIVATE TEST — not registered as an approved export. Third-party footage: rights not recorded."
    (outdir / f"{name}.json").write_text(_json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    m = res["music"]
    print(f"  ▶ {out}\n    {res['duration']}s | upscale {res['upscale']}x | QC {res['qc']['decision']}")
    print(f"    MUSIC: '{m['sound']}' — {m['artist']} | {m['bpm']} BPM | drop at {m['drop_at_s']}s")
    return 0 if res["qc"]["decision"] == "PASS" else 1

def _post_kit(app: App, t: dict, days: int) -> dict:
    """Post texts for one rendered template edit (TikTok / YouTube Shorts / X)."""
    import json as _json
    from .metadata.post_kit import build
    lines = []
    for e in t.get("text", []):
        if e.get("type") == "line":
            lines.append(e["text"].replace("{days}", str(days)))
        elif e.get("type") == "counter":
            lines.append(f"{days} DAYS")
    lines = [l for i, l in enumerate(lines) if l not in lines[:i]]
    topics = []
    sp = app.settings.path("memory/research/summary_latest.json")
    if sp.exists():
        try:
            topics = [x if isinstance(x, str) else x.get("topic", "") for x in _json.loads(sp.read_text()).get("topics", [])][:15]
        except Exception:
            topics = []
    hcfg = app.settings.profile("gta6").hype or {}
    return build(lines=lines, days=days, topics=topics, kind=t.get("category") or "hype_edit", seed=t["id"], sound=t.get("sound"), sound_ref=t.get("reference"),
                 handle=hcfg.get("watermark") or "", orientation=t.get("orientation", "vertical"))



def cmd_meme(app: App, a) -> int:
    """Reaction memes: add <TikTok url|file> learns a clean reaction clip; daily writes new captions (Gemini, one call)
    and renders them; list shows the clip library."""
    import json as _json
    from datetime import date as _date, datetime as _dt, timezone as _tz
    from .editing import meme_maker as M
    from .editing.hype_editor import days_until
    from .metadata.post_kit import as_text, build
    prof = app.settings.profile(a.profile)
    root = app.settings.root
    lib = M.load_library(root, prof.id)
    if a.action == "list":
        for c in lib:
            print(f"  {c['id']}: {c['duration']}s | {c['what']} | used: {len(c.get('used_captions', []))}")
        return 0
    if a.action == "add":
        from .research.trends import TikTokPublic
        src = a.target or ""
        m = re.search(r"tiktok\.com/@([^/]+)/video/(\d+)", src)
        if m:
            f = app.settings.path("assets/meme_refs") / f"{m.group(1)}_{m.group(2)}.mp4"
            if not f.exists():
                TikTokPublic.download(m.group(1), m.group(2), f)
            cid = f"{m.group(1)}_{m.group(2)[-6:]}".replace(".", "_")
        else:
            f, cid = Path(src), Path(src).stem
        r = M.extract_clip(str(f), app.settings.path(f"assets/meme_clips/{cid}.mp4"), start=a.start or 0.0, end=a.end)
        entry = {"id": cid, "file": f"assets/meme_clips/{cid}.mp4", "what": a.what or "", "emotion": _csv(a.emotion or ""),
                 "reference": src if m else None, "duration": r["duration"], "used_captions": []}
        lib = [c for c in lib if c["id"] != cid] + [entry]
        M.save_library(root, prof.id, lib)
        print(f"  + {cid}: {r['duration']}s, crop {r['box']}, upscale {r['upscale']}x — describe it with --what/--emotion")
        return 0
    # daily
    days = days_until(prof.release_date) if prof.release_date else 0
    clips = [c for c in lib if Path(root / c["file"]).exists() and c.get("what")][: a.n or 6]
    if not clips:
        print("meme library is empty: meme add <tiktok url> --what ... --emotion ..."); return 1
    topics, examples = [], []
    sp = app.settings.path("memory/research/summary_latest.json")
    if sp.exists():
        summ = _json.loads(sp.read_text())
        topics = [x if isinstance(x, str) else x.get("topic", "") for x in summ.get("topics", [])]
    try:
        from .styles.style_library import StyleLibrary
        examples = StyleLibrary(app.db, app.settings).headline_examples(prof.id, "meme_skit") or []
    except Exception:
        examples = []
    if not app.orch.gemini.available():
        print("Gemini unavailable: no new captions today"); return 1
    caps = M.write_captions(clips, app.orch.gemini, days=days, topics=topics, examples=examples,
                            today=_date.today().isoformat())
    day = _dt.now(_tz.utc).strftime("%Y-%m-%d")
    outdir = app.settings.path(app.settings.global_.outputs_dir) / "_PRIVATE_TEST" / prof.output_folder / day / "memes"
    made = 0
    for c in clips:
        cap = caps.get(c["id"])
        if not cap:
            continue
        out = outdir / f"MEME_{c['id']}_{_dt.now(_tz.utc).strftime('%H%M%S')}.mp4"
        r = M.render_meme(str(root / c["file"]), cap, out)
        kit = build(lines=[cap], days=days, kind="meme_skit")
        out.with_suffix(".post.txt").write_text(as_text(kit, cap), encoding="utf-8")
        out.with_suffix(".json").write_text(_json.dumps({**r, "clip": c["id"], "post": kit}, indent=2, ensure_ascii=False))
        c.setdefault("used_captions", []).append(cap)
        made += 1
        print(f"  ▶ {out}\n    {r['duration']}s | {cap}")
    M.save_library(root, prof.id, lib)
    return 0 if made else 1


def cmd_examples(app: App, a) -> int:
    from .styles.style_library import StyleLibrary, json_dump
    lib = StyleLibrary(app.db, app.settings)
    if a.action == "add":
        if not a.target:
            print("usage: examples add <video file> --profile gta6 [--category X] [--label ...]"); return 1
        src = a.target
        if src.startswith(("http://", "https://")):
            import urllib.request
            dest_dir = app.settings.path("assets/examples") / a.profile
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"example_{len(list(dest_dir.glob('*.mp4'))) + 1:03d}.mp4"
            with urllib.request.urlopen(src, timeout=300) as r, dest.open("wb") as fh:
                fh.write(r.read())
            src = str(dest)
        if a.category and a.category not in app.settings.profile(a.profile).content_categories:
            print(f"unknown category; choose from: {', '.join(app.settings.profile(a.profile).content_categories)}"); return 1
        res = lib.add(src, a.profile, label=a.label, category=a.category, source=a.target,
                      gemini=None if a.no_ai else app.orch.gemini, notes=a.notes)
        m, p = res["metrics"], res["preset"]
        print(f"Example {res['id']} saved for {a.profile} (category: {res['category'] or 'none yet'})")
        print(f"  measured: {m['duration']}s, {m['width']}x{m['height']}, layout guess {m['layout_guess']}, "
              f"split at {m['seam_y']}, {m['cuts_per_min']} cuts/min, faces/frame {m['faces_per_frame']}")
        if res["vision"] and "error" not in res["vision"]:
            v = res["vision"]
            print(f"  seen by AI: layout {v.get('layout')}, camera {v.get('facecam_position')}, captions "
                  f"{'yes' if v.get('captions_present') else 'no'}, title banner {'yes' if v.get('title_banner_present') else 'no'}"
                  f"{' (' + v['title_text'] + ')' if v.get('title_text') else ''}, effects {v.get('effects')}")
        elif res["vision"]:
            print(f"  AI vision unavailable: {res['vision']['error'][:120]} (local analysis still saved)")
        print("  style preset:", json_dump(p).replace("\n", "\n  "))
    elif a.action == "list":
        rows = lib.list(a.profile)
        for r in rows:
            r["layout"] = r["preset"].get("layout"); r["dur"] = r["metrics"].get("duration")
            r["title_banner"] = (r["preset"].get("title_overlay") or {}).get("enabled")
        print(table(rows, ["id", "profile", "label", "category", "layout", "dur", "title_banner", "created_at"]))
        if a.profile:
            print("\nsummary:", json_dump(lib.summary(a.profile)))
    elif a.action == "show":
        print(json_dump(next((r for r in lib.list() if r["id"] == a.target), None)))
    elif a.action == "set-category":
        lib.set_category(a.target, a.category); print(f"{a.target} -> {a.category}")
    elif a.action == "remove":
        lib.remove(a.target); print(f"removed {a.target}")
    elif a.action == "export":
        path = app.settings.path(f"config/style_examples/{a.profile}.json")
        print(f"exported {lib.export(a.profile, path)} examples to {path}")
    elif a.action == "import":
        print(f"imported {lib.import_file(Path(a.target))} examples")
    elif a.action == "choose":
        c = lib.choose(a.profile, a.category)
        print(json_dump(c.__dict__ if c else None))
    return 0


def cmd_trends(app: App, a) -> int:
    import json as _json
    from datetime import date as _date
    from .research.planner import make_plan, save_plan
    from .research.trends import TrendResearch
    from .styles.style_library import StyleLibrary
    prof = app.settings.profile(a.profile)
    cfg = prof.trend_research
    mem = app.settings.path("memory/research")
    if a.action == "research":
        tr = TrendResearch(mem, known_types=cfg.get("creator_types", {}))
        extra = []
        disc = mem / "discovered_creators.json"
        if disc.exists():
            extra = [h for h, n in _json.loads(disc.read_text()).items() if n >= 2][:25]
        handles = list(dict.fromkeys(cfg.get("tiktok_watchlist", []) + extra))
        snap = tr.run(handles, cfg.get("youtube_queries", []), max_pages_per_creator=int(cfg.get("pages_per_creator", 4)))
        summ = tr.summarize(snap)
        # discover creators mentioned in on-topic captions
        import re as _re
        from .research.trends import on_topic
        counts = _json.loads(disc.read_text()) if disc.exists() else {}
        for v in snap.tiktok:
            if on_topic(v.get("desc")):
                for h in _re.findall(r"@([A-Za-z0-9_.]{3,24})", v.get("desc") or ""):
                    if h.lower() not in [x.lower() for x in handles]:
                        counts[h] = counts.get(h, 0) + 1
        disc.write_text(_json.dumps(counts, indent=1))
        (mem / "summary_latest.json").write_text(_json.dumps(summ, indent=1, ensure_ascii=False))
        _print_trends(summ)
    elif a.action == "show":
        _print_trends(_json.loads((mem / "summary_latest.json").read_text()))
    elif a.action == "plan":
        summ = _json.loads((mem / "summary_latest.json").read_text())
        lib = StyleLibrary(app.db, app.settings)
        heads = {c: lib.headline_examples(prof.id, c) for c in ("streamer_reaction", "hype_edit", "meme_skit", "fun_fact", "news_trailer")}
        rel = _date.fromisoformat(prof.release_date) if prof.release_date else None
        plan = make_plan(summ, n=a.n or int(cfg.get("videos_per_day", 12)), release=rel, headlines=heads,
                         duration_targets=lib.duration_targets(prof.id))
        path = save_plan(plan, app.settings.path("memory"))
        print(f"Plan {plan['date']} — phase {plan['phase']} ({plan['days_to_release']} days to release) — {plan['videos']} videos")
        print("allocation:", plan["allocation"])
        for s_ in plan["slots"]:
            snd = s_["sound"] if isinstance(s_["sound"], str) else f"{s_['sound']['title']} — {s_['sound']['author']}"
            print(f"  {s_['slot']:>2}. {s_['type']:<13} {s_['target_length_s'] or '?':>3}s  topic: {s_['topic']}  |  {s_['series']}\n"
                  f"      sound: {snd}\n      headline style: {(s_['headline_style'] or ['-'])[0]}")
        print(f"\nsaved: {path}")
    return 0


def _print_trends(s: dict) -> None:
    print(f"Research {s['taken_at']}: {s['tiktok_videos']} TikTok + {s['youtube_videos']} YouTube videos")
    print("\nGTA 6 content types right now (median views/hour, engagement):")
    for t, v in s["types"].items():
        print(f"  {t:<14} n={v['n']:<3} {v['median_velocity']:>7}/h  eng {v['median_engagement']:.1%}  shares {v['median_share_rate']:.2%}")
    print("\nFastest GTA 6 TikToks:")
    for v in s["top_tiktok"][:10]:
        print(f"  {v['velocity']:>7}/h  {v['views']:>9} views  {v['age_h']:>5}h old  x{v['outlier']} vs creator  "
              f"{v['type']:<13} @{v['author']}: {(v['desc'] or '')[:55]}")
    print("\nTrending topics:", ", ".join(t for t, _ in s["topics"][:15]))
    print("Trending sounds:", "; ".join(f"{x['title']} — {x['author']}" for x in s["sounds"][:6]))
    if s.get("top_youtube"):
        print("\nFastest GTA 6 YouTube:")
        for r in s["top_youtube"][:6]:
            print(f"  {r['velocity']:>7}/h  {r['views']:>9}  {r['title'][:60]} | {r['channel']}")
    adj = s.get("adjacent_trends", {})
    if adj.get("topics"):
        print("\nAdjacent (non-GTA) trends:", ", ".join(t for t, _ in adj["topics"][:8]))
    if s.get("errors"):
        print("errors:", s["errors"][:5])


def cmd_memory(app: App, a) -> int:
    from .core import memory
    from .styles.style_library import StyleLibrary
    if a.action == "save":
        counts = memory.save(app.db, app.settings.path("memory"))
        lib = StyleLibrary(app.db, app.settings)
        for pid in app.settings.profiles:
            if lib.list(pid):
                lib.export(pid, app.settings.path(f"config/style_examples/{pid}.json"))
        print("saved to memory/:", counts, "(commit and push to keep it)")
    else:
        print("loaded:", memory.load(app.db, app.settings.path("memory")))
    return 0


# ----------------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="main.py", description="Local AI Clipping Machine (AMP / CORE / LosPollosTV)")
    sub = p.add_subparsers(dest="cmd", required=True)
    prof_choices = list(PROFILE_IDS) + ["all"]

    sub.add_parser("doctor", help="check environment and dependencies").set_defaults(fn=cmd_doctor)
    sub.add_parser("init", help="create database and folders").set_defaults(fn=cmd_init)
    sub.add_parser("status", help="system status").set_defaults(fn=cmd_status)
    s = sub.add_parser("start", help="start continuous research + processing")
    s.add_argument("--profile", choices=prof_choices); s.add_argument("--interval", type=float, help="minutes")
    s.add_argument("--once", action="store_true", help="run a single cycle then exit"); s.set_defaults(fn=cmd_start)
    sub.add_parser("pause", help="pause research/processing").set_defaults(fn=cmd_pause)
    sub.add_parser("resume", help="resume research/processing").set_defaults(fn=cmd_resume)
    s = sub.add_parser("research", help="run discovery/research for a profile")
    s.add_argument("profile", choices=prof_choices, nargs="?", default="all")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--gemini", dest="gemini", action="store_true", default=None, help="force Gemini research now")
    g.add_argument("--no-gemini", dest="gemini", action="store_false")
    s.set_defaults(fn=cmd_research)
    s = sub.add_parser("process", help="process approved sources into clips")
    s.add_argument("profile", choices=prof_choices, nargs="?", default="all"); s.add_argument("--max-clips", type=int)
    s.set_defaults(fn=cmd_process)
    s = sub.add_parser("candidates", help="list candidate moments")
    s.add_argument("--profile", choices=PROFILE_IDS); s.add_argument("--status"); s.add_argument("--limit", type=int, default=30)
    s.set_defaults(fn=cmd_candidates)
    s = sub.add_parser("candidate", help="show one candidate with all score components"); s.add_argument("id"); s.set_defaults(fn=cmd_candidate)
    s = sub.add_parser("clips", help="list clips")
    s.add_argument("--profile", choices=PROFILE_IDS); s.add_argument("--decision", choices=["approved", "rejected", "needs_review"])
    s.add_argument("--limit", type=int, default=30); s.set_defaults(fn=cmd_clips)
    s = sub.add_parser("clip", help="show one clip (QC, rights, metadata)"); s.add_argument("id"); s.set_defaults(fn=cmd_clip)
    s = sub.add_parser("review", help="human review of NEEDS_REVIEW clips")
    s.add_argument("action", choices=["list", "approve", "reject"]); s.add_argument("id", nargs="?"); s.add_argument("--note")
    s.set_defaults(fn=cmd_review)

    s = sub.add_parser("sources", help="source index")
    s.add_argument("action", choices=["list", "show", "add", "attach", "set"]); s.add_argument("id", nargs="?")
    s.add_argument("--profile", choices=PROFILE_IDS); s.add_argument("--rights")
    s.add_argument("--file"); s.add_argument("--url"); s.add_argument("--direct-download", action="store_true",
                                                                       help="URL is a direct media file you are authorized to download")
    s.add_argument("--title"); s.add_argument("--channel"); s.add_argument("--creators"); s.add_argument("--participants")
    s.add_argument("--category"); s.add_argument("--published"); s.add_argument("--recorded-start")
    s.add_argument("--third-party", choices=["none", "unknown", "present_cleared", "present_uncleared"], default=None)
    s.add_argument("--facecam", help="x,y,w,h normalised facecam region"); s.add_argument("--ignore-window", action="store_true")
    s.set_defaults(fn=cmd_sources)

    s = sub.add_parser("rights", help="permission registry")
    s.add_argument("action", choices=["list", "add", "set-status", "check", "history"]); s.add_argument("id", nargs="?")
    s.add_argument("--scope", choices=["creator", "channel", "source", "category", "asset", "user_owned"])
    s.add_argument("--value", help="creator name / channel id / source id or url / category / asset path")
    s.add_argument("--holder", help="rights holder"); s.add_argument("--status", default="PENDING_VERIFICATION")
    s.add_argument("--evidence"); s.add_argument("--ops", help="comma list: download_or_import,edit,distribute,commercial_use")
    s.add_argument("--all-participants", action="store_true"); s.add_argument("--attribution")
    s.add_argument("--expires"); s.add_argument("--restrictions", help='JSON, e.g. {"max_clip_seconds": 60, "allowed_profiles": ["amp"]}')
    s.add_argument("--profile", choices=PROFILE_IDS); s.add_argument("--notes")
    s.set_defaults(fn=cmd_rights)

    s = sub.add_parser("errors", help="processing errors"); s.add_argument("--limit", type=int, default=30)
    s.add_argument("--resolved", action="store_true"); s.add_argument("--clear", action="store_true"); s.set_defaults(fn=cmd_errors)
    s = sub.add_parser("analytics", help="performance analytics")
    s.add_argument("action", choices=["show", "import", "template"], nargs="?", default="show")
    s.add_argument("file", nargs="?"); s.add_argument("--profile", choices=PROFILE_IDS); s.set_defaults(fn=cmd_analytics)
    s = sub.add_parser("private-test", help="full pipeline on a local recording, PRIVATE (never for publication)")
    s.add_argument("file"); s.add_argument("--profile", choices=PROFILE_IDS, required=True)
    s.add_argument("--creators", required=True); s.add_argument("--title"); s.add_argument("--max-clips", type=int, default=5)
    s.set_defaults(fn=cmd_private_test)
    s = sub.add_parser("hype", help="beat-synced hype edit from trailer/gameplay files (private test output)")
    s.add_argument("action", choices=["make", "templates", "learn", "learn-trending", "render", "daily"])
    s.add_argument("sources", nargs="*", help="make: videos | learn: TikTok URL or file | render: template ids")
    s.add_argument("--profile", choices=PROFILE_IDS, default="gta6"); s.add_argument("--template")
    s.add_argument("--id"); s.add_argument("--top", type=int, default=3); s.add_argument("--n", type=int)
    s.add_argument("--no-ai", action="store_true", help="learn without Gemini (no text events)")
    s.add_argument("--opener"); s.add_argument("--main"); s.add_argument("--final")
    s.set_defaults(fn=cmd_hype)
    s = sub.add_parser("meme", help="reaction memes: caption + well-known clip (TikTok + YouTube Shorts)")
    s.add_argument("action", choices=["daily", "add", "list"]); s.add_argument("target", nargs="?")
    s.add_argument("--profile", choices=PROFILE_IDS, default="gta6"); s.add_argument("--n", type=int)
    s.add_argument("--what"); s.add_argument("--emotion"); s.add_argument("--start", type=float); s.add_argument("--end", type=float)
    s.set_defaults(fn=cmd_meme)
    s = sub.add_parser("examples", help="example clips the machine learns editing formats from")
    s.add_argument("action", choices=["add", "list", "show", "set-category", "remove", "choose", "export", "import"])
    s.add_argument("target", nargs="?", help="video file / URL (add) or example id")
    s.add_argument("--profile", choices=PROFILE_IDS); s.add_argument("--category"); s.add_argument("--label")
    s.add_argument("--notes"); s.add_argument("--no-ai", action="store_true", help="skip Gemini vision (saves quota)")
    s.set_defaults(fn=cmd_examples)
    s = sub.add_parser("trends", help="trend research (TikTok first) and the daily content plan")
    s.add_argument("action", choices=["research", "show", "plan"]); s.add_argument("--profile", choices=PROFILE_IDS, default="gta6")
    s.add_argument("--n", type=int, help="videos in the plan (default from config)")
    s.set_defaults(fn=cmd_trends)
    s = sub.add_parser("memory", help="save/load the durable memory kept in the repo (memory/)")
    s.add_argument("action", choices=["save", "load"]); s.set_defaults(fn=cmd_memory)
    sub.add_parser("compare-formats", help="compare LosPollosTV formats A/B/C").set_defaults(fn=cmd_compare_formats)
    s = sub.add_parser("learning", help="learning recommendations and config history")
    s.add_argument("action", choices=["analyze", "list", "apply", "dismiss", "history"])
    s.add_argument("id", nargs="?", type=int); s.add_argument("--profile", choices=prof_choices); s.add_argument("--status")
    s.set_defaults(fn=cmd_learning)
    s = sub.add_parser("set-threshold", help="change a profile's min quality threshold")
    s.add_argument("profile", choices=PROFILE_IDS); s.add_argument("value", type=float); s.add_argument("--reason")
    s.set_defaults(fn=cmd_set_threshold)
    s = sub.add_parser("set-duration", help="change adaptive duration limits")
    s.add_argument("profile", choices=PROFILE_IDS); s.add_argument("--min", type=float); s.add_argument("--max", type=float)
    s.add_argument("--reason"); s.set_defaults(fn=cmd_set_duration)
    s = sub.add_parser("search", help="search transcripts"); s.add_argument("query"); s.add_argument("--profile", choices=PROFILE_IDS)
    s.add_argument("--limit", type=int, default=20); s.set_defaults(fn=cmd_search)
    s = sub.add_parser("attention", help="creator research attention"); s.add_argument("--profile", choices=prof_choices)
    s.set_defaults(fn=cmd_attention)
    s = sub.add_parser("research-notes", help="stored Gemini research notes with citations")
    s.add_argument("--profile", choices=PROFILE_IDS); s.add_argument("--limit", type=int, default=20); s.set_defaults(fn=cmd_research_notes)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = App(Path(os.environ["CLIPPER_ROOT"]) if os.environ.get("CLIPPER_ROOT") else None)
    return int(args.fn(app, args) or 0)
