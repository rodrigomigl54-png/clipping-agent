"""End-to-end pipeline tests on synthetic media (real FFmpeg renders)."""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from clipper.config import load_settings
from clipper.core.media import media_info
from clipper.core.orchestrator import Orchestrator
from clipper.rights.permission_registry import Permission

from conftest import write_transcript

FULL = dict(commercial_use=True, editing=True, distribution=True, download=True)


@pytest.fixture()
def fast_project(project):
    (project / "config" / "local_overrides.yaml").write_text(
        yaml.safe_dump({"editing": {"output": {"preset": "ultrafast"}}}))
    return project


def _orch(root):
    return Orchestrator(load_settings(root))


def _add_source(orch, root, video, profile="amp", name="stream", creators=("Kai Cenat", "Fanum"), tpc="none",
                recorded_start=None):
    inbox = root / "sources" / "inbox" / profile
    inbox.mkdir(parents=True, exist_ok=True)
    dst = inbox / f"{name}.mp4"
    shutil.copy(video, dst)
    write_transcript(dst)
    meta = {"creators": list(creators), "third_party_content": tpc, "title": f"{name} test"}
    if recorded_start:
        meta["recorded_start"] = recorded_start
    (inbox / f"{name}.source.yaml").write_text(yaml.safe_dump(meta))
    orch.research.research_profile(profile, use_gemini=False)
    return orch.db.one("SELECT * FROM sources WHERE title=?", (f"{name} test",))


def _approve(orch, *names):
    for n in names:
        orch.registry.add(Permission("creator", n, n, status="APPROVED", evidence="test agreement", **FULL))


def test_rights_gate_blocks_unpermitted_source(fast_project, sample_video):
    orch = _orch(fast_project)
    src = _add_source(orch, fast_project, sample_video)
    res = orch.process_profile("amp")
    assert res["sources"][0]["stage"] == "blocked_rights"
    assert orch.db.one("SELECT count(*) n FROM candidates")["n"] == 0
    assert orch.db.one("SELECT count(*) n FROM transcripts")["n"] == 0
    # pending files are kept in the pending folder, never processed
    assert "/sources/pending/amp/" in orch.store.get(src["id"])["local_path"]


def test_end_to_end_export_and_duplicate_prevention(fast_project, sample_video):
    orch = _orch(fast_project)
    _approve(orch, "Kai Cenat", "Fanum")
    _add_source(orch, fast_project, sample_video)
    res = orch.process_profile("amp")
    exported = [c["export"] for c in res["clips"] if c.get("export")]
    assert exported, res
    e = exported[0]
    f = Path(e["file"])
    assert f.exists() and "/outputs/AMP/" in str(f)
    info = media_info(f)
    assert (info["width"], info["height"]) == (1080, 1920)
    assert info["video_codec"] == "h264" and info["audio_codec"] == "aac"
    assert 15 <= info["duration"] <= 180
    meta_files = list(f.parent.parent.glob("metadata/*.json"))
    meta = json.loads(meta_files[0].read_text())
    for k in ("title", "description", "hashtags", "summary", "creators", "source", "original_timestamp",
              "duration", "viral_potential_score", "quality_score", "rights_status", "monetization"):
        assert k in meta
    assert list(f.parent.parent.glob("thumbnails/*.jpg"))
    # the clip contains the full story setup, not just the loud reaction
    cand = orch.db.one("SELECT * FROM candidates WHERE status='exported'")
    assert cand["start"] < 10 and cand["end"] > 47
    assert orch.db.one("SELECT count(*) n FROM export_registry")["n"] == 1

    # same footage arriving again as a different source must not be exported twice
    shutil.copy(sample_video, fast_project / "copy.mp4")
    src2 = _add_source(orch, fast_project, fast_project / "copy.mp4", name="reupload")
    res2 = orch.process_profile("amp")
    assert not any(c.get("export") for c in res2["clips"])
    statuses = {r["status"] for r in orch.db.query("SELECT status FROM candidates WHERE source_id=?", (src2["id"],))}
    assert statuses <= {"duplicate", "below_threshold", "superseded"}


def test_unknown_third_party_goes_to_review_then_human_approval(fast_project, sample_video):
    orch = _orch(fast_project)
    _approve(orch, "Kai Cenat", "Fanum")
    src = _add_source(orch, fast_project, sample_video, tpc="unknown")
    res = orch.process_profile("amp")
    review = [c for c in res["clips"] if c.get("decision") == "NEEDS_REVIEW"]
    assert review and not any(c.get("export") for c in res["clips"])
    assert not list((fast_project / "outputs").rglob("*.mp4"))
    cid = review[0]["clip_id"]
    with pytest.raises(ValueError):      # human approval cannot override an unresolved rights issue
        orch.approve_review(cid)
    orch.store.update(src["id"], third_party_content="none")
    e = orch.approve_review(cid, "checked audio: streamer voice only")
    assert Path(e["file"]).exists()


def test_crash_recovery(fast_project, sample_video):
    orch = _orch(fast_project)
    _approve(orch, "Kai Cenat", "Fanum")
    src = _add_source(orch, fast_project, sample_video)
    orch.process_source(src["id"])
    cand = orch.db.one("SELECT * FROM candidates WHERE status='new'")
    assert cand
    # simulate a crash mid-edit and mid-transcription
    orch.db.insert("clips", {"id": "clip_crash", "candidate_id": cand["id"], "profile": "amp", "source_id": src["id"],
                             "stage": "editing", "created_at": "x"})
    orch.db.update("candidates", "id", cand["id"], {"status": "queued"})
    orch.store.set_stage(src["id"], "transcribing")
    rec = _orch(fast_project).recover()
    assert rec == {"sources_reset": 1, "clips_reset": 1}
    assert orch.db.one("SELECT status FROM candidates WHERE id=?", (cand["id"],))["status"] == "new"
    # transcript checkpoint is reused, not recomputed
    assert orch.db.one("SELECT count(*) n FROM transcripts")["n"] == 1


def test_cross_stream_event_grouping(fast_project, sample_video):
    s = load_settings(fast_project)
    orch = Orchestrator(s)
    _approve(orch, "Kai Cenat", "Duke Dennis")
    t0 = datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc).isoformat()
    a = _add_source(orch, fast_project, sample_video, name="kai", creators=("Kai Cenat",), recorded_start=t0)
    b = _add_source(orch, fast_project, sample_video, name="duke", creators=("Duke Dennis",), recorded_start=t0)
    orch.process_source(a["id"]); orch.process_source(b["id"])
    groups = orch.cross.resolve("amp")
    assert len(groups) == 1 and len(groups[0]["members"]) == 2
    assert orch.db.one("SELECT count(*) n FROM candidates WHERE status='superseded'")["n"] == 1


def test_lospollos_split_format_with_licensed_gameplay(fast_project, sample_video, gameplay_video):
    orch = _orch(fast_project)
    _approve(orch, "LosPollosTV")
    gp = fast_project / "assets" / "approved_gameplay" / "my_gta_capture.mp4"
    shutil.copy(gameplay_video, gp)
    orch.registry.add(Permission("asset", "assets/approved_gameplay/my_gta_capture.mp4", "Me", status="APPROVED",
                                 evidence="recorded by me on my own copy of GTA V", **FULL))
    # make Format A the least-sampled so it is chosen
    for i, f in enumerate(["B", "C"]):
        orch.db.insert("format_assignments", {"clip_id": f"x{i}", "candidate_id": f"y{i}", "profile": "lospollostv",
                                              "format": f, "assigned_at": "x"})
    _add_source(orch, fast_project, sample_video, profile="lospollostv", creators=("LosPollosTV",))
    res = orch.process_profile("lospollostv")
    ex = [c["export"] for c in res["clips"] if c.get("export")]
    assert ex and ex[0]["format"] == "A"
    clip = orch.db.one("SELECT * FROM clips WHERE format='A'")
    assert clip["layout"] == "split_gta"
    info = media_info(ex[0]["file"])
    assert info["height"] == 1920 and info["duration"] > 40   # full story, not a teaser


def test_lospollos_without_licensed_gameplay_only_format_b(fast_project, gameplay_video):
    from clipper.editing.format_experiment import FormatExperiment
    orch = _orch(fast_project)
    shutil.copy(gameplay_video, fast_project / "assets" / "approved_gameplay" / "random_download.mp4")
    exp = FormatExperiment(orch.db, orch.settings, orch.gate)
    fmts, gp = exp.available_formats()
    assert fmts == ["B"] and gp == []     # unregistered gameplay is never used


def test_format_assignment_is_balanced_and_one_per_moment(fast_project, gameplay_video):
    import random
    from clipper.editing.format_experiment import FormatExperiment
    orch = _orch(fast_project)
    shutil.copy(gameplay_video, fast_project / "assets" / "approved_gameplay" / "g.mp4")
    orch.registry.add(Permission("asset", "assets/approved_gameplay/g.mp4", "Me", status="APPROVED", evidence="own", **FULL))
    exp = FormatExperiment(orch.db, orch.settings, orch.gate, rng=random.Random(1))
    for i in range(30):
        exp.assign(f"cand{i}", f"clip{i}")
    assert exp.counts() == {"A": 10, "B": 10, "C": 10}
    # re-assigning the same moment keeps its format (no multi-format copies of one moment)
    f1, _, _ = exp.assign("cand0", "clip0b")
    assert f1 == exp.existing("cand0")


def test_core_profile_independent(fast_project, sample_video):
    orch = _orch(fast_project)
    _approve(orch, "Lacy", "Silky")
    _add_source(orch, fast_project, sample_video, profile="core", creators=("Lacy", "Silky"))
    res = orch.process_profile("core")
    ex = [c["export"] for c in res["clips"] if c.get("export")]
    assert ex and "/outputs/CORE/" in ex[0]["file"]
    cand = orch.db.one("SELECT * FROM candidates WHERE status='exported'")
    assert json.loads(cand["scores"])["group_chemistry"] > 5      # two speakers bantering
    # other profiles untouched
    assert orch.db.one("SELECT count(*) n FROM candidates WHERE profile!='core'")["n"] == 0


def test_private_test_never_reaches_real_outputs(fast_project, sample_video):
    orch = _orch(fast_project)
    v = fast_project / "rec.mp4"; shutil.copy(sample_video, v); write_transcript(v)
    res = orch.private_test(str(v), "amp", ["Kai Cenat"], max_clips=1)
    files = [c["private_test"]["file"] for c in res["clips"] if c.get("private_test")]
    assert files and "/outputs/_PRIVATE_TEST/AMP/" in files[0] and Path(files[0]).exists()
    assert not list((fast_project / "outputs" / "AMP").rglob("*.mp4"))
    assert orch.db.one("SELECT count(*) n FROM export_registry")["n"] == 0
    assert orch.db.one("SELECT count(*) n FROM permissions")["n"] == 0
