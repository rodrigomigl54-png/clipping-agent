"""Central orchestrator: runs sources and candidates through every stage with checkpoints.

Source stages:  waiting → (rights gate) → importing → transcribing → analyzing → clipping → completed
Clip stages:    clipping → editing → quality_checking → exporting → completed | needs_review | failed

Every stage persists its output (audio/visual feature files under work/, transcripts and
candidates in SQLite), so an interrupted run resumes where it stopped. One failing source or clip
is recorded and never stops the rest of the run.
"""
from __future__ import annotations

import shutil
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from ..config import Settings
from ..core.database import Database, dumps, loads, new_id, now_iso
from ..core.logger import get_logger
from ..core.media import extract_audio_wav
from ..clipping.duplicate_detector import DuplicateDetector
from ..clipping.fingerprints import audio_fingerprint, video_phash
from ..detection.audio_analyzer import AudioFeatures, analyze_wav
from ..detection.cross_stream_detector import CrossStreamDetector
from ..detection.viral_detector import DetectionInputs, ViralDetector
from ..detection.visual_analyzer import VisualFeatures, analyze_video
from ..editing.adaptive_editor import AdaptiveEditor
from ..editing.format_experiment import asset_key
from ..export.export_manager import ExportManager
from ..ingestion.media_ingest import IngestError, ingest, place_source_file
from ..metadata.metadata_builder import build_metadata
from ..metadata.thumbnail_generator import make_thumbnail
from ..models import CandidateStatus, Decision, Stage
from ..quality.content_checks import content_checks
from ..quality.quality_controller import decide
from ..quality.technical_checks import technical_checks
from ..research.google_ai import GeminiClient
from ..research.research_engine import ResearchEngine
from ..research.source_discovery import SourceStore
from ..rights import monetization_check
from ..rights.permission_registry import PermissionRegistry
from ..rights.rights_gate import RightsGate
from ..transcription.transcription_engine import TranscriptionEngine, Transcriber

log = get_logger("orchestrator")

SOURCE_ACTIVE = (Stage.IMPORTING.value, Stage.TRANSCRIBING.value, Stage.ANALYZING.value)
CLIP_ACTIVE = (Stage.CLIPPING.value, Stage.EDITING.value, Stage.QUALITY_CHECKING.value, Stage.EXPORTING.value)


class Orchestrator:
    def __init__(self, settings: Settings, db: Database | None = None, *, transcriber: Transcriber | None = None,
                 gemini: GeminiClient | None = None, rss_fetch: Callable | None = None):
        self.settings = settings
        self.db = db or Database(settings.db_path)
        self.registry = PermissionRegistry(self.db)
        self.gate = RightsGate(self.registry, settings)
        self.gemini = gemini or GeminiClient(settings.global_.google_ai)
        self.store = SourceStore(self.db, settings)
        self.research = ResearchEngine(self.db, settings, self.gemini, self.gate, rss_fetch=rss_fetch)
        self.transcription = TranscriptionEngine(self.db, settings, transcriber)
        self.detector = ViralDetector(settings, self.gemini)
        self.cross = CrossStreamDetector(self.db, settings)
        self.dupes = DuplicateDetector(self.db, settings)
        self.editor = AdaptiveEditor(settings, self.gate, self.db)
        self.exporter = ExportManager(self.db, settings)
        self.should_stop: Callable[[], bool] = lambda: False

    # ================================================================ recovery
    def recover(self) -> dict[str, int]:
        """Reset work interrupted by a crash or shutdown so it resumes from its last checkpoint."""
        n_src = n_clip = 0
        for s in self.db.query(f"SELECT id FROM sources WHERE stage IN ({','.join('?' * len(SOURCE_ACTIVE))})",
                               SOURCE_ACTIVE):
            self.store.set_stage(s["id"], Stage.WAITING, "recovered after interruption (resumes from checkpoint)")
            n_src += 1
        for c in self.db.query(f"SELECT * FROM clips WHERE stage IN ({','.join('?' * len(CLIP_ACTIVE))})",
                               CLIP_ACTIVE):
            if c["stage"] == Stage.EXPORTING.value and c["decision"] == Decision.APPROVED.value:
                try:
                    self.exporter.export(c["id"]); continue
                except Exception as e:
                    self.db.log_error("recovery.export", c["id"], str(e), traceback.format_exc(), c["profile"])
            self.db.update("clips", "id", c["id"], {"stage": Stage.FAILED.value, "error": "interrupted", "updated_at": now_iso()})
            self.db.update("candidates", "id", c["candidate_id"], {"status": CandidateStatus.NEW.value,
                                                                  "status_reason": "retry after interruption"})
            n_clip += 1
        return {"sources_reset": n_src, "clips_reset": n_clip}

    # ================================================================ helpers
    def work(self, *parts: str) -> Path:
        p = self.settings.work_dir.joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _features(self, src: dict, media: Path) -> tuple[AudioFeatures, VisualFeatures | None, Path]:
        wd = self.work("sources", src["id"])
        wav = wd / "audio16k.wav"
        if not wav.exists():
            extract_audio_wav(media, wav, timeout=self.settings.global_.pipeline.stage_timeout_seconds)
        af_path = wd / "audio_features.npz"
        if af_path.exists():
            audio = AudioFeatures.load(af_path)
        else:
            audio = analyze_wav(wav)
            audio.save(af_path)
        return audio, None, wav

    def _visual(self, src: dict, media: Path) -> VisualFeatures | None:
        vf_path = self.work("sources", src["id"]) / "visual_features.npz"
        if vf_path.exists():
            return VisualFeatures.load(vf_path)
        try:
            vis = analyze_video(media, float(src["duration"] or 0), fps=1.0)
            vis.save(vf_path)
            return vis
        except Exception as e:
            log.warning("visual analysis failed for %s: %s (continuing without visual signals)", src["id"], e)
            return None

    # ================================================================ source pipeline
    def process_source(self, sid: str) -> dict[str, Any]:
        src = self.store.get(sid)
        if not src:
            raise KeyError(sid)
        profile = src["profile"]
        decision = self.gate.evaluate(src, "processing")
        self.store.update(sid, rights_status=decision.status, rights_reason=decision.summary())
        place_source_file(self.store, self.settings, self.store.get(sid), decision.status)
        src = self.store.get(sid)
        private = bool(loads(src.get("extra"), {}).get("private_test"))
        if not decision.passed and not private:
            self.store.set_stage(sid, Stage.BLOCKED_RIGHTS, decision.summary())
            return {"source_id": sid, "stage": Stage.BLOCKED_RIGHTS.value, "rights": decision.to_dict()}
        if not self.store.in_window(src):
            return {"source_id": sid, "stage": src["stage"], "skipped": "outside research window"}
        try:
            self.store.set_stage(sid, Stage.IMPORTING)
            media = ingest(self.store, self.settings, src, decision.passed or private)
            src = self.store.get(sid)
            self.store.set_stage(sid, Stage.TRANSCRIBING)
            audio, _, wav = self._features(src, media)
            tr = self.transcription.transcribe_source(src, wav)
            self.store.set_stage(sid, Stage.ANALYZING)
            existing = self.db.one("SELECT count(*) n FROM candidates WHERE source_id=?", (sid,))["n"]
            n_new = 0
            if not existing:
                vis = self._visual(src, media)
                n_new = self.detect_and_store(src, tr, audio, vis)
            self.store.set_stage(sid, Stage.CLIPPING, f"{n_new} new candidates")
            return {"source_id": sid, "stage": Stage.CLIPPING.value, "candidates": n_new}
        except IngestError as e:
            self.store.update(sid, attempts=(src.get("attempts") or 0) + 1)
            self.store.set_stage(sid, Stage.FAILED, f"ingest: {e}", error=str(e))
            self.db.log_error("ingest", sid, str(e), None, profile)
            return {"source_id": sid, "stage": Stage.FAILED.value, "error": str(e)}
        except Exception as e:
            self.store.update(sid, attempts=(src.get("attempts") or 0) + 1)
            self.store.set_stage(sid, Stage.FAILED, str(e)[:300], error=str(e))
            self.db.log_error("process_source", sid, str(e), traceback.format_exc(), profile)
            log.error("source %s failed: %s", sid, e)
            return {"source_id": sid, "stage": Stage.FAILED.value, "error": str(e)}

    def _headlines(self, profile: str, category: str | None) -> list[str] | None:
        try:
            from ..styles.style_library import StyleLibrary
            return StyleLibrary(self.db, self.settings).headline_examples(profile, category) or None
        except Exception:
            return None

    def _duration_targets(self, profile: str) -> dict | None:
        try:
            from ..styles.style_library import StyleLibrary
            return StyleLibrary(self.db, self.settings).duration_targets(profile) or None
        except Exception:
            return None

    def detect_and_store(self, src: dict, tr, audio, vis) -> int:
        prof = self.settings.profile(src["profile"])
        src = dict(src)
        src["participants_list"] = loads(src["participants"], [])
        exported = [r["transcript_text"] or "" for r in self.db.query(
            "SELECT transcript_text FROM export_registry WHERE profile=?", (prof.id,))]
        inp = DetectionInputs(source=src, transcript=tr, audio=audio, visual=vis,
                              media_duration=float(src["duration"] or audio.duration),
                              trend_terms=self.research.trends.trend_terms(prof.id), exported_texts=exported,
                              duration_targets=self._duration_targets(prof.id))
        cands = self.detector.detect(inp, prof, self.settings.global_.pipeline.max_candidates_per_source)
        with self.db.transaction() as c:
            for cand in cands:
                cid = new_id("cand")
                status, reason = CandidateStatus.NEW.value, None
                if cand.total_score < prof.min_quality_threshold:
                    status, reason = CandidateStatus.BELOW_THRESHOLD.value, \
                        f"score {cand.total_score:.1f} < threshold {prof.min_quality_threshold}"
                c.execute("INSERT INTO candidates(id,source_id,profile,start,\"end\",peak,total_score,scores,signals,"
                          "hook_type,category,transcript_text,summary,participants,ai_analysis,status,status_reason,"
                          "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (cid, cand.source_id, cand.profile, cand.start, cand.end, cand.peak, cand.total_score,
                           dumps(cand.scores), dumps(cand.signals), cand.hook_type, cand.category,
                           cand.transcript_text, cand.summary, dumps(cand.participants),
                           dumps(cand.ai_analysis) if cand.ai_analysis else None, status, reason, now_iso(), now_iso()))
        return len(cands)

    # ================================================================ clip pipeline
    def pending_candidates(self, profile: str) -> list[dict]:
        rows = self.db.query("SELECT * FROM candidates WHERE profile=? AND status='new' ORDER BY total_score DESC",
                             (profile,))
        out = []
        maxa = self.settings.global_.pipeline.max_render_attempts
        for r in rows:
            fails = self.db.one("SELECT count(*) n FROM clips WHERE candidate_id=? AND stage='failed'", (r["id"],))["n"]
            if fails >= maxa:
                self.db.update("candidates", "id", r["id"], {"status": CandidateStatus.FAILED.value,
                               "status_reason": f"failed {fails} render attempts", "updated_at": now_iso()})
                continue
            out.append(r)
        return out

    def produce_clip(self, cand: dict) -> dict[str, Any]:
        src = self.store.get(cand["source_id"])
        prof = self.settings.profile(cand["profile"])
        dup = self.dupes.check_candidate(cand)
        if dup.is_duplicate:
            self.db.update("candidates", "id", cand["id"], {"status": CandidateStatus.DUPLICATE.value,
                           "status_reason": dup.reason, "updated_at": now_iso()})
            return {"candidate_id": cand["id"], "status": "duplicate", "reason": dup.reason}
        clip_id = new_id("clip")
        self.db.insert("clips", {"id": clip_id, "candidate_id": cand["id"], "profile": prof.id, "source_id": src["id"],
                                 "stage": Stage.CLIPPING.value, "viral_score": cand["total_score"],
                                 "created_at": now_iso(), "updated_at": now_iso()})
        self.db.update("candidates", "id", cand["id"], {"status": CandidateStatus.QUEUED.value, "updated_at": now_iso()})

        def stage(s: Stage, **extra):
            self.db.update("clips", "id", clip_id, {"stage": s.value, "updated_at": now_iso(), **extra})
            self.db.log_event("clip", clip_id, s.value, s.value, prof.id)

        try:
            tr = self.transcription.get(src["id"])
            af = self.work("sources", src["id"]) / "audio_features.npz"
            audio = AudioFeatures.load(af) if af.exists() else None
            stage(Stage.EDITING)
            cand_full = dict(cand)
            cand_full["ai_analysis"] = loads(cand["ai_analysis"])
            participants = loads(src["participants"], [])
            pre = self.gate.evaluate(src, "export")
            title = build_metadata(self.settings, source=src, candidate=cand_full, participants=participants,
                                   segments_text=[x.text for x in tr.window(cand["start"], cand["end"])],
                                   start=cand["start"], end=cand["end"], attribution=pre.attribution,
                                   trend_terms=self.research.trends.trend_terms(prof.id), gemini=self.gemini,
                                   headline_examples=self._headlines(prof.id, cand_full.get("category")))["title"]
            result = self.editor.edit(source=src, candidate=cand_full, transcript=tr, audio=audio, clip_id=clip_id,
                                      out_dir=self.work("renders", prof.id), title=title, gemini=self.gemini)
            stage(Stage.QUALITY_CHECKING, render_path=str(result.path), duration=result.duration,
                  layout=result.layout, format=result.format)
            phash = video_phash(result.path)
            afp = audio_fingerprint(result.path, self.work("tmp"))
            self.db.update("clips", "id", clip_id, {"phash": dumps(phash), "audio_fp": dumps(afp)})
            participants = loads(src["participants"], [])
            assets = [asset_key(self.settings, Path(result.gameplay_asset))] if result.gameplay_asset else []
            pre_rights = self.gate.evaluate(src, "export", clip_duration=result.duration, assets=assets)
            segs = [s.text for s in tr.window(result.start, result.end)]
            meta = build_metadata(self.settings, source=src, candidate=cand_full, participants=participants,
                                  segments_text=segs, start=result.start, end=result.end,
                                  attribution=pre_rights.attribution,
                                  trend_terms=self.research.trends.trend_terms(prof.id), gemini=self.gemini,
                                  title=title)
            thumb = make_thumbnail(result.path, meta["title"], self.work("renders", prof.id) / f"{clip_id}.jpg",
                                   self.settings.root)
            tech, info = technical_checks(result.path, cfg=self.settings.quality["technical"],
                                          min_dur=prof.duration.min_seconds, max_dur=prof.duration.max_seconds,
                                          caption_report=result.captions if result.captions_enabled else None, caption_size=prof.editing.caption.size)
            scores = loads(cand["scores"], {})
            content = content_checks(transcript=tr, start=result.start, end=result.end, scores=scores,
                                     cfg=self.settings.quality["content"], caption_report=result.captions if result.captions_enabled else None,
                                     ai_analysis=cand_full["ai_analysis"])
            tp = result.text_placement or {}
            content.add("text_clear_of_content", tp.get("ok", True),
                        "; ".join(tp.get("notes", [])) or "title and captions placed outside protected areas", "review")
            rights = self.gate.evaluate(src, "export", clip_duration=result.duration, assets=assets,
                                        metadata_text=meta["description"])
            mon = monetization_check.assess(
                " ".join(segs), lexicons=self.settings.lexicons, rights_status=rights.status,
                third_party_content=src.get("third_party_content") or "unknown",
                transformative_elements=result.transformative_elements, clip_duration=result.duration,
                source_duration=src.get("duration"), policy=self.settings.rights.get("monetization", {}),
                profile_policy=prof.monetization)
            rdup = self.dupes.check_render(prof.id, clip_id, phash, afp)
            qc = decide(technical=tech, content=content, rights=rights, monetization=mon, duplicate=rdup,
                        scores=scores, rights_unknown_policy=self.settings.quality.get("decision", {}).get(
                            "rights_unknown_third_party", "needs_review"))
            meta["monetization_suitability"] = mon.to_dict()
            meta["rights_status"] = rights.status
            meta["viral_potential_score"] = cand["total_score"]
            meta["quality_score"] = qc.quality_score
            meta["layout"] = {"layout": result.layout, "format": result.format, "reason": result.layout_reason,
                              "gameplay_asset": result.gameplay_asset}
            self.db.update("clips", "id", clip_id, {
                "decision": qc.decision, "decision_reasons": dumps(qc.reasons), "qc": dumps(qc.to_dict()),
                "rights_status": rights.status, "monetization": dumps(mon.to_dict()), "metadata": dumps(meta),
                "quality_score": qc.quality_score, "thumbnail_path": str(thumb), "updated_at": now_iso()})
            # keep trimmed boundaries on the candidate so the registry reflects what was exported
            self.db.update("candidates", "id", cand["id"], {"start": result.start, "end": result.end})
            out: dict[str, Any] = {"clip_id": clip_id, "decision": qc.decision, "reasons": qc.reasons}
            if loads(src.get("extra"), {}).get("private_test"):
                # private evaluation: never enters outputs/<BRAND>, never the export registry
                stage(Stage.NEEDS_REVIEW)
                self.db.update("candidates", "id", cand["id"], {"status": CandidateStatus.NEEDS_REVIEW.value,
                               "status_reason": "private test clip — not for publication"})
                technical_ok = not tech.failed("fail")
                out["private_test"] = self.exporter.export_private_test(clip_id) if technical_ok else None
                return out
            if qc.decision == Decision.APPROVED.value:
                stage(Stage.EXPORTING)
                self.db.update("candidates", "id", cand["id"], {"status": CandidateStatus.APPROVED.value})
                out["export"] = self.exporter.export(clip_id)
            elif qc.decision == Decision.NEEDS_REVIEW.value:
                stage(Stage.NEEDS_REVIEW)
                self.db.update("candidates", "id", cand["id"], {"status": CandidateStatus.NEEDS_REVIEW.value,
                               "status_reason": "; ".join(qc.reasons)[:1000]})
            else:
                stage(Stage.COMPLETED)
                self.db.update("candidates", "id", cand["id"], {"status": CandidateStatus.REJECTED.value,
                               "status_reason": "; ".join(qc.reasons)[:1000]})
                if not self.settings.global_.pipeline.keep_rejected_renders:
                    result.path.unlink(missing_ok=True)
            return out
        except Exception as e:
            self.db.update("clips", "id", clip_id, {"stage": Stage.FAILED.value, "error": str(e)[:4000],
                                                    "updated_at": now_iso()})
            self.db.update("candidates", "id", cand["id"], {"status": CandidateStatus.NEW.value,
                           "status_reason": f"render attempt failed: {str(e)[:300]}"})
            self.db.log_error("produce_clip", clip_id, str(e), traceback.format_exc(), prof.id)
            log.error("clip %s failed: %s", clip_id, e)
            return {"clip_id": clip_id, "decision": "FAILED", "error": str(e)}

    def private_test(self, file: str, profile: str, creators: list[str], title: str | None = None,
                     max_clips: int = 5) -> dict[str, Any]:
        """Run the full pipeline on a local recording for private evaluation only. Rights are NOT
        approved: clips go to outputs/_PRIVATE_TEST/ labelled NOT FOR PUBLICATION."""
        from pathlib import Path as _P
        path = str(_P(file).resolve())
        sid, _ = self.store.register(profile=profile, kind="local_file", key=f"private:{path}", title=title or _P(path).stem,
                                     local_path=path, creators=creators, discovery_method="private_test",
                                     extra={"private_test": True, "ignore_window": True})
        res = self.process_source(sid)
        clips = []
        if res.get("stage") == Stage.CLIPPING.value:
            for cand in self.db.query("SELECT * FROM candidates WHERE source_id=? AND status='new' "
                                      "ORDER BY total_score DESC LIMIT ?", (sid, max_clips)):
                clips.append(self.produce_clip(cand))
        return {"source": res, "clips": clips}

    # ================================================================ review workflow
    def approve_review(self, clip_id: str, note: str = "") -> dict:
        """Human approval of a NEEDS_REVIEW clip. Rights and technical checks are re-run and cannot
        be overridden: only content-level review flags are cleared by a human."""
        clip = self.db.one("SELECT * FROM clips WHERE id=?", (clip_id,))
        if not clip or clip["decision"] != Decision.NEEDS_REVIEW.value:
            raise ValueError(f"{clip_id} is not awaiting review")
        src = self.store.get(clip["source_id"])
        meta = loads(clip["metadata"], {})
        assets = [asset_key(self.settings, Path(meta["layout"]["gameplay_asset"]))] \
            if meta.get("layout", {}).get("gameplay_asset") else []
        rights = self.gate.evaluate(src, "export", clip_duration=clip["duration"], assets=assets,
                                    metadata_text=meta.get("description", ""))
        if not rights.passed:
            raise ValueError("rights check still failing — fix the permission records first: " + rights.summary())
        qc = loads(clip["qc"], {})
        tech_fail = [c for c in qc.get("technical", []) if not c["passed"] and c["severity"] == "fail"]
        if tech_fail or not Path(clip["render_path"] or "").exists():
            raise ValueError("technical checks failed or render missing; cannot approve")
        mon = loads(clip["monetization"], {})
        if mon.get("blocked"):
            raise ValueError("blocked by content policy; cannot approve")
        reasons = loads(clip["decision_reasons"], []) + [f"human-approved: {note}".strip()]
        self.db.update("clips", "id", clip_id, {"decision": Decision.APPROVED.value, "rights_status": rights.status,
                                                "decision_reasons": dumps(reasons), "updated_at": now_iso()})
        meta["rights_status"] = rights.status
        self.db.update("clips", "id", clip_id, {"metadata": dumps(meta)})
        self.db.update("candidates", "id", clip["candidate_id"], {"status": CandidateStatus.APPROVED.value})
        return self.exporter.export(clip_id)

    def reject_review(self, clip_id: str, note: str = "") -> None:
        clip = self.db.one("SELECT * FROM clips WHERE id=?", (clip_id,))
        if not clip:
            raise ValueError(clip_id)
        reasons = loads(clip["decision_reasons"], []) + [f"human-rejected: {note}".strip()]
        self.db.update("clips", "id", clip_id, {"decision": Decision.REJECTED.value, "stage": Stage.COMPLETED.value,
                                                "decision_reasons": dumps(reasons), "updated_at": now_iso()})
        self.db.update("candidates", "id", clip["candidate_id"], {"status": CandidateStatus.REJECTED.value})

    # ================================================================ cycles
    def process_profile(self, profile: str, max_clips: int | None = None) -> dict[str, Any]:
        results: dict[str, Any] = {"profile": profile, "sources": [], "clips": [], "events": []}
        # refresh rights for blocked sources (permissions may have been added since)
        for src in self.store.list(profile):
            if self.should_stop():
                break
            if src["stage"] in (Stage.WAITING.value, Stage.BLOCKED_RIGHTS.value) or (
                    src["stage"] == Stage.FAILED.value and (src["attempts"] or 0) < self.settings.global_.pipeline.max_render_attempts):
                results["sources"].append(self.process_source(src["id"]))
        results["events"] = self.cross.resolve(profile)
        n = 0
        for cand in self.pending_candidates(profile):
            if self.should_stop() or (max_clips is not None and n >= max_clips):
                break
            results["clips"].append(self.produce_clip(cand))
            n += 1
        # sources whose candidates are all handled are completed
        for src in self.store.list(profile, stage=Stage.CLIPPING.value):
            open_ = self.db.one("SELECT count(*) n FROM candidates WHERE source_id=? AND status IN ('new','queued')",
                                (src["id"],))["n"]
            if not open_:
                self.store.set_stage(src["id"], Stage.COMPLETED, "all candidates processed")
        return results

    def run_cycle(self, profiles: list[str] | None = None, research: bool = True) -> dict[str, Any]:
        out = {}
        for pid in profiles or list(self.settings.profiles):
            if self.should_stop() or self.db.get_state("paused") == "1":
                break
            self.db.set_state("activity", f"researching {pid}")
            res = self.research.research_profile(pid) if research else None
            self.db.set_state("activity", f"processing {pid}")
            out[pid] = {"research": res, "processing": self.process_profile(pid)}
        self.db.set_state("activity", Stage.WAITING.value)
        self.db.set_state("last_cycle", now_iso())
        return out
