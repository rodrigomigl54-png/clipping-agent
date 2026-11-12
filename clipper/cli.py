"""Command-line interface — the operating surface used from Claude Code.

Run ``python main.py --help`` for all commands.
"""
from __future__ import annotations

import argparse
import json
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
    s = sub.add_parser("examples", help="example clips the machine learns editing formats from")
    s.add_argument("action", choices=["add", "list", "show", "set-category", "remove", "choose", "export", "import"])
    s.add_argument("target", nargs="?", help="video file / URL (add) or example id")
    s.add_argument("--profile", choices=PROFILE_IDS); s.add_argument("--category"); s.add_argument("--label")
    s.add_argument("--notes"); s.add_argument("--no-ai", action="store_true", help="skip Gemini vision (saves quota)")
    s.set_defaults(fn=cmd_examples)
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
