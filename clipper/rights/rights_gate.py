"""Rights gate: decides whether a source may be processed and whether a clip may be exported.

GOLDEN RULE: publicly accessible does not mean free to use. The gate fails closed — anything not
positively covered by a valid permission record is PENDING_VERIFICATION, never approved.
A viral score can never override this gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import Settings
from ..core.database import loads
from ..models import RightsStatus
from .permission_registry import Permission, PermissionRegistry

_OK = (RightsStatus.APPROVED.value, RightsStatus.APPROVED_WITH_CONDITIONS.value)


@dataclass
class RightsDecision:
    status: str
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    attribution: list[str] = field(default_factory=list)
    restrictions: list[dict[str, Any]] = field(default_factory=list)
    permission_ids: list[int] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status in _OK

    def summary(self) -> str:
        head = self.status
        if self.reasons:
            head += ": " + "; ".join(self.reasons)
        return head

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reasons": self.reasons, "missing": self.missing,
                "attribution": self.attribution, "restrictions": self.restrictions,
                "permission_ids": self.permission_ids}


class RightsGate:
    def __init__(self, registry: PermissionRegistry, settings: Settings):
        self.registry = registry
        self.settings = settings
        self.policy = settings.rights

    # ----------------------------------------------------------------- helpers
    def _canonical(self, profile: str, name: str) -> str:
        prof = self.settings.profiles.get(profile)
        c = prof.creator(name) if prof else None
        return (c.name if c else name).strip().lower()

    def _names_for(self, profile: str, holder: str) -> set[str]:
        prof = self.settings.profiles.get(profile)
        c = prof.creator(holder) if prof else None
        names = {holder.strip().lower()}
        if c:
            names |= {c.name.lower(), *(a.lower() for a in c.aliases)}
        return names

    def _source_level(self, source: dict) -> list[Permission]:
        profile = source["profile"]
        perms: list[Permission] = []
        keys = [source.get("id"), source.get("url"), source.get("content_hash")]
        for k in filter(None, keys):
            perms += self.registry.find("source", k, profile)
            perms += self.registry.find("user_owned", k, profile)
        if source.get("channel"):
            perms += self.registry.find("channel", source["channel"], profile)
        if source.get("category"):
            perms += self.registry.find("category", source["category"], profile)
        return perms

    def _creator_level(self, profile: str, holder: str) -> list[Permission]:
        out: list[Permission] = []
        for n in self._names_for(profile, holder):
            out += self.registry.find("creator", n, profile)
        return out

    @staticmethod
    def _perm_applies_to_holder(p: Permission, names: set[str]) -> bool:
        if p.covers_all_participants:
            return True
        return p.rights_holder.strip().lower() in names or p.scope_type == "creator"

    # ----------------------------------------------------------------- main
    def evaluate(self, source: dict, stage: str = "processing", *, clip_duration: float | None = None,
                 assets: list[str] | None = None, metadata_text: str | None = None) -> RightsDecision:
        """Evaluate a source (DB row dict) for ``stage`` in {"processing", "export"}."""
        profile = source["profile"]
        ops_key = "required_operations_for_export" if stage == "export" else "required_operations_for_processing"
        required_ops: list[str] = list(self.policy.get(ops_key, []))
        reasons: list[str] = []
        missing: list[str] = []
        attribution: list[str] = []
        restrictions: list[dict] = []
        used: list[int] = []
        conditional = False

        participants = loads(source.get("participants"), []) or loads(source.get("creators"), []) or []
        participants = sorted({p.strip() for p in participants if p and p.strip()})

        source_perms = self._source_level(source)
        holder_perms = {h: self._creator_level(profile, h) for h in participants}
        all_perms = source_perms + [p for ps in holder_perms.values() for p in ps]

        # 1. explicit rejections win
        rejected = [p for p in all_perms if p.status == RightsStatus.REJECTED.value]
        if rejected:
            return RightsDecision(RightsStatus.REJECTED.value,
                                  [f"permission #{p.id} for '{p.rights_holder}' is REJECTED" for p in rejected],
                                  permission_ids=[p.id for p in rejected if p.id])

        # 2. who must be covered?
        blanket = [p for p in source_perms if p.covers_all_participants]
        if not participants and not blanket:
            return RightsDecision(
                self.policy.get("treat_missing_participants_as", RightsStatus.PENDING_VERIFICATION.value),
                ["participants unknown: list every creator/guest in the source so permissions can be checked"],
                missing=["participants"])

        holders = participants or ["(all participants)"]
        expired_seen = False
        for holder in holders:
            names = self._names_for(profile, holder) if holder != "(all participants)" else set()
            cands = [p for p in source_perms if self._perm_applies_to_holder(p, names) and
                     (p.covers_all_participants or p.rights_holder.strip().lower() in names)]
            cands += holder_perms.get(holder, [])
            if not cands:
                missing.append(f"{holder}: no permission record")
                continue
            valid = None
            problems: list[str] = []
            for p in cands:
                eff = p.effective_status()
                if eff == RightsStatus.EXPIRED.value:
                    expired_seen = True
                    problems.append(f"permission #{p.id} expired {p.expires_at}")
                    continue
                if eff not in _OK:
                    problems.append(f"permission #{p.id} is {eff}")
                    continue
                allowed_profiles = p.restrictions.get("allowed_profiles")
                if allowed_profiles and profile not in allowed_profiles:
                    problems.append(f"permission #{p.id} not valid for profile {profile}")
                    continue
                lacking = p.missing_ops(required_ops)
                if lacking:
                    problems.append(f"permission #{p.id} does not grant {', '.join(lacking)}")
                    continue
                valid = p
                break
            if not valid:
                missing.append(f"{holder}: " + "; ".join(problems))
                continue
            if valid.id:
                used.append(valid.id)
            if valid.status == RightsStatus.APPROVED_WITH_CONDITIONS.value or valid.restrictions:
                conditional = True
            if valid.attribution_required:
                conditional = True
                attribution.append(valid.attribution_text or f"Credit: {valid.rights_holder}")
            if valid.restrictions:
                restrictions.append({"permission_id": valid.id, **valid.restrictions})

        if missing:
            status = RightsStatus.EXPIRED.value if expired_seen and all("expired" in m for m in missing) \
                else RightsStatus.PENDING_VERIFICATION.value
            reasons += missing
            return RightsDecision(status, reasons, missing=missing, permission_ids=used)

        # 3. export-only checks
        if stage == "export":
            tpc = source.get("third_party_content") or "unknown"
            if tpc == "present_uncleared":
                return RightsDecision(RightsStatus.REJECTED.value,
                                      ["source contains uncleared third-party content (music/media)"],
                                      missing=["third_party_clearance"], permission_ids=used)
            if tpc == "unknown":
                return RightsDecision(RightsStatus.PENDING_VERIFICATION.value,
                                      ["third-party content (music, video, overlays) not verified for this source"],
                                      missing=["third_party_content_verification"], permission_ids=used)
            for r in restrictions:
                mx = r.get("max_clip_seconds")
                if mx and clip_duration and clip_duration > float(mx):
                    return RightsDecision(RightsStatus.REJECTED.value,
                                          [f"clip {clip_duration:.0f}s exceeds licensed max {mx}s"],
                                          permission_ids=used)
            for asset in assets or []:
                ad = self.evaluate_asset(asset, profile)
                if not ad.passed:
                    return RightsDecision(ad.status, [f"asset not cleared: {asset}"] + ad.reasons,
                                          missing=["asset:" + asset], permission_ids=used)
            if attribution and metadata_text is not None:
                absent = [a for a in attribution if a not in metadata_text]
                if absent:
                    return RightsDecision(RightsStatus.PENDING_VERIFICATION.value,
                                          ["required attribution missing from metadata"],
                                          missing=absent, attribution=attribution, permission_ids=used)

        status = RightsStatus.APPROVED_WITH_CONDITIONS.value if conditional else RightsStatus.APPROVED.value
        return RightsDecision(status, reasons, attribution=attribution, restrictions=restrictions,
                              permission_ids=used)

    def evaluate_asset(self, asset_key: str, profile: str | None = None) -> RightsDecision:
        """Assets (gameplay footage, fonts, music) need their own APPROVED asset permission that
        grants editing + distribution + commercial use."""
        perms = self.registry.find("asset", asset_key, profile)
        if not perms:
            return RightsDecision(RightsStatus.PENDING_VERIFICATION.value,
                                  ["no asset permission record"], missing=[asset_key])
        for p in perms:
            if p.status == RightsStatus.REJECTED.value:
                return RightsDecision(RightsStatus.REJECTED.value, [f"asset permission #{p.id} REJECTED"])
        for p in perms:
            if p.effective_status() in _OK and not p.missing_ops(["edit", "distribute", "commercial_use"]):
                return RightsDecision(p.status, permission_ids=[p.id] if p.id else [])
        return RightsDecision(RightsStatus.PENDING_VERIFICATION.value,
                              ["asset permission lacks edit/distribute/commercial_use or is expired"])
