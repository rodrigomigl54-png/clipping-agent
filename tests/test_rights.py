from datetime import datetime, timedelta, timezone

import pytest

from clipper.models import RightsStatus
from clipper.research.source_discovery import SourceStore
from clipper.rights.monetization_check import assess
from clipper.rights.permission_registry import Permission, PermissionRegistry
from clipper.rights.rights_gate import RightsGate

FULL = dict(commercial_use=True, editing=True, distribution=True, download=True)


def _setup(settings, db, participants=("Kai Cenat",), tpc="none"):
    store = SourceStore(db, settings)
    sid, _ = store.register(profile="amp", kind="local_file", key="file:/x.mp4", title="t", local_path="/x.mp4",
                            creators=list(participants), participants=list(participants), third_party_content=tpc)
    return store, sid, PermissionRegistry(db), RightsGate(PermissionRegistry(db), settings)


def test_no_permission_is_pending(settings, db):
    store, sid, reg, gate = _setup(settings, db)
    d = gate.evaluate(store.get(sid), "processing")
    assert d.status == RightsStatus.PENDING_VERIFICATION.value
    assert any("Kai Cenat" in m for m in d.missing)


def test_unknown_participants_pending(settings, db):
    store, sid, reg, gate = _setup(settings, db, participants=())
    assert gate.evaluate(store.get(sid)).status == "PENDING_VERIFICATION"


def test_approved_requires_evidence(settings, db):
    reg = PermissionRegistry(db)
    with pytest.raises(ValueError):
        reg.add(Permission("creator", "Kai Cenat", "Kai Cenat", status="APPROVED", **FULL))


def test_creator_permission_alias_and_export(settings, db):
    store, sid, reg, gate = _setup(settings, db)
    reg.add(Permission("creator", "kai", "Kai Cenat", status="APPROVED", evidence="signed.pdf", **FULL))
    src = store.get(sid)
    assert gate.evaluate(src, "processing").passed
    assert gate.evaluate(src, "export").passed


def test_group_content_needs_every_participant(settings, db):
    store, sid, reg, gate = _setup(settings, db, participants=("Kai Cenat", "Fanum", "Some Guest"))
    reg.add(Permission("creator", "Kai Cenat", "Kai Cenat", status="APPROVED", evidence="e", **FULL))
    reg.add(Permission("creator", "Fanum", "Fanum", status="APPROVED", evidence="e", **FULL))
    d = gate.evaluate(store.get(sid))
    assert not d.passed and any("Some Guest" in m for m in d.missing)
    # a source-level license that explicitly covers all participants resolves it
    reg.add(Permission("source", sid, "AMP LLC", status="APPROVED", evidence="license.pdf",
                       covers_all_participants=True, **FULL))
    assert gate.evaluate(store.get(sid)).passed


def test_missing_commercial_use_blocks_export_not_processing(settings, db):
    store, sid, reg, gate = _setup(settings, db)
    reg.add(Permission("creator", "Kai Cenat", "Kai Cenat", status="APPROVED", evidence="e",
                       editing=True, download=True, distribution=True, commercial_use=False))
    src = store.get(sid)
    assert gate.evaluate(src, "processing").passed
    d = gate.evaluate(src, "export")
    assert not d.passed and "commercial_use" in " ".join(d.missing)


def test_rejected_wins_and_expired(settings, db):
    store, sid, reg, gate = _setup(settings, db)
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    reg.add(Permission("creator", "Kai Cenat", "Kai Cenat", status="APPROVED", evidence="e", expires_at=past, **FULL))
    assert gate.evaluate(store.get(sid)).status == "EXPIRED"
    pid = reg.add(Permission("source", sid, "Kai Cenat", status="REJECTED", evidence="takedown"))
    assert gate.evaluate(store.get(sid)).status == "REJECTED"
    assert reg.history(pid)


def test_third_party_and_attribution_at_export(settings, db):
    store, sid, reg, gate = _setup(settings, db, tpc="unknown")
    reg.add(Permission("creator", "Kai Cenat", "Kai Cenat", status="APPROVED_WITH_CONDITIONS", evidence="e",
                       attribution_required=True, attribution_text="Credit: @KaiCenat", **FULL))
    src = store.get(sid)
    assert gate.evaluate(src, "export").status == "PENDING_VERIFICATION"   # music/media unverified
    store.update(sid, third_party_content="none")
    src = store.get(sid)
    assert gate.evaluate(src, "export", metadata_text="no credit").status == "PENDING_VERIFICATION"
    d = gate.evaluate(src, "export", metadata_text="... Credit: @KaiCenat ...")
    assert d.status == "APPROVED_WITH_CONDITIONS" and d.attribution == ["Credit: @KaiCenat"]
    store.update(sid, third_party_content="present_uncleared")
    assert gate.evaluate(store.get(sid), "export").status == "REJECTED"


def test_restrictions_profile_and_duration(settings, db):
    store, sid, reg, gate = _setup(settings, db)
    reg.add(Permission("creator", "Kai Cenat", "Kai Cenat", status="APPROVED", evidence="e",
                       restrictions={"max_clip_seconds": 60}, **FULL))
    src = store.get(sid)
    assert gate.evaluate(src, "export", clip_duration=45).passed
    assert gate.evaluate(src, "export", clip_duration=90).status == "REJECTED"


def test_asset_gate(settings, db):
    reg = PermissionRegistry(db); gate = RightsGate(reg, settings)
    assert not gate.evaluate_asset("assets/approved_gameplay/a.mp4").passed
    reg.add(Permission("asset", "assets/approved_gameplay/a.mp4", "Me", status="APPROVED",
                       evidence="my own capture", **FULL))
    assert gate.evaluate_asset("assets/approved_gameplay/a.mp4").passed


def test_monetization_gambling_block(settings):
    m = assess("let's go to the casino and play slots, casino slots jackpot gamble betting " * 3,
               lexicons=settings.lexicons, rights_status="APPROVED", third_party_content="none",
               transformative_elements=["a", "b", "c"], clip_duration=30, source_duration=3600,
               policy=settings.rights["monetization"])
    assert m.blocked and m.risk_level == "blocked"
    ok = assess("we went to the store and he raced me down the aisle", lexicons=settings.lexicons,
                rights_status="APPROVED", third_party_content="none", transformative_elements=["a", "b", "c"],
                clip_duration=30, source_duration=3600, policy=settings.rights["monetization"])
    assert ok.risk_level == "low" and not ok.blocked
