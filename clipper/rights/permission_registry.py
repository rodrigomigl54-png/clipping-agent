"""Local source-permission registry.

Every creator, channel, source, category or asset that the machine may touch needs a permission
record here. Records are never silently changed: every update is written to
``permission_history``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..core.database import Database, dumps, loads, now_iso
from ..models import RightsStatus

SCOPE_TYPES = ("creator", "channel", "source", "category", "asset", "user_owned")
OPERATIONS = ("download_or_import", "edit", "distribute", "commercial_use", "clip")


@dataclass
class Permission:
    scope_type: str
    scope_value: str
    rights_holder: str
    status: str = RightsStatus.PENDING_VERIFICATION.value
    evidence: str | None = None
    allowed_operations: list[str] = field(default_factory=list)
    commercial_use: bool = False
    editing: bool = False
    distribution: bool = False
    download: bool = False
    covers_all_participants: bool = False
    attribution_required: bool = False
    attribution_text: str | None = None
    expires_at: str | None = None
    restrictions: dict[str, Any] = field(default_factory=dict)
    profile: str | None = None
    notes: str | None = None
    id: int | None = None

    def is_expired(self, at: datetime | None = None) -> bool:
        if not self.expires_at:
            return False
        at = at or datetime.now(timezone.utc)
        try:
            exp = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return True  # unparseable expiry: treat as expired (fail closed)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp <= at

    def effective_status(self) -> str:
        if self.status in (RightsStatus.APPROVED, RightsStatus.APPROVED_WITH_CONDITIONS) and self.is_expired():
            return RightsStatus.EXPIRED.value
        return self.status

    def grants(self, op: str) -> bool:
        """Does this permission grant operation ``op``? Flags and the operations list must agree."""
        flag = {
            "commercial_use": self.commercial_use,
            "edit": self.editing,
            "distribute": self.distribution,
            "download_or_import": self.download or "download_or_import" in self.allowed_operations,
        }.get(op)
        listed = op in self.allowed_operations
        if op == "download_or_import":
            return bool(flag)
        return bool(flag) and (listed or not self.allowed_operations)

    def missing_ops(self, ops: list[str]) -> list[str]:
        return [o for o in ops if not self.grants(o)]

    @classmethod
    def from_row(cls, r: dict) -> "Permission":
        return cls(
            id=r["id"], scope_type=r["scope_type"], scope_value=r["scope_value"],
            rights_holder=r["rights_holder"], status=r["status"], evidence=r["evidence"],
            allowed_operations=loads(r["allowed_operations"], []),
            commercial_use=bool(r["commercial_use"]), editing=bool(r["editing"]),
            distribution=bool(r["distribution"]), download=bool(r["download"]),
            covers_all_participants=bool(r["covers_all_participants"]),
            attribution_required=bool(r["attribution_required"]),
            attribution_text=r["attribution_text"], expires_at=r["expires_at"],
            restrictions=loads(r["restrictions"], {}), profile=r["profile"], notes=r["notes"],
        )

    def to_row(self) -> dict:
        return {
            "scope_type": self.scope_type, "scope_value": self.scope_value,
            "profile": self.profile, "rights_holder": self.rights_holder, "status": self.status,
            "evidence": self.evidence, "allowed_operations": dumps(self.allowed_operations),
            "commercial_use": int(self.commercial_use), "editing": int(self.editing),
            "distribution": int(self.distribution), "download": int(self.download),
            "covers_all_participants": int(self.covers_all_participants),
            "attribution_required": int(self.attribution_required),
            "attribution_text": self.attribution_text, "expires_at": self.expires_at,
            "restrictions": dumps(self.restrictions), "notes": self.notes,
        }


class PermissionRegistry:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _norm(v: str) -> str:
        return v.strip().lower()

    def add(self, perm: Permission) -> int:
        if perm.scope_type not in SCOPE_TYPES:
            raise ValueError(f"scope_type must be one of {SCOPE_TYPES}")
        try:
            RightsStatus(perm.status)
        except ValueError as e:
            raise ValueError(f"invalid status {perm.status}") from e
        if perm.status in (RightsStatus.APPROVED, RightsStatus.APPROVED_WITH_CONDITIONS) and not perm.evidence:
            raise ValueError("An APPROVED permission requires evidence (e.g. path to signed agreement, "
                             "license URL, or 'user-owned recording').")
        for op in perm.allowed_operations:
            if op not in OPERATIONS:
                raise ValueError(f"unknown operation '{op}'. Valid: {OPERATIONS}")
        row = perm.to_row()
        row["scope_value"] = self._norm(perm.scope_value) if perm.scope_type != "asset" else perm.scope_value
        row["created_at"] = row["updated_at"] = now_iso()
        with self.db.transaction():
            pid = self.db.insert("permissions", row)
            self.db.insert("permission_history", {"permission_id": pid, "action": "create",
                                                  "old": None, "new": dumps(row), "created_at": now_iso()})
        return pid

    def get(self, pid: int) -> Permission | None:
        r = self.db.one("SELECT * FROM permissions WHERE id=?", (pid,))
        return Permission.from_row(r) if r else None

    def set_status(self, pid: int, status: str, evidence: str | None = None, note: str | None = None) -> None:
        RightsStatus(status)
        cur = self.get(pid)
        if not cur:
            raise KeyError(f"permission {pid} not found")
        new_evidence = evidence or cur.evidence
        if status in (RightsStatus.APPROVED, RightsStatus.APPROVED_WITH_CONDITIONS) and not new_evidence:
            raise ValueError("Approving requires evidence.")
        with self.db.transaction():
            self.db.update("permissions", "id", pid, {"status": status, "evidence": new_evidence,
                                                     "notes": note or cur.notes, "updated_at": now_iso()})
            self.db.insert("permission_history", {"permission_id": pid, "action": "status",
                                                  "old": cur.status, "new": status, "created_at": now_iso()})

    def list(self, scope_type: str | None = None, status: str | None = None,
             profile: str | None = None) -> list[Permission]:
        sql, params = "SELECT * FROM permissions WHERE 1=1", []
        if scope_type:
            sql += " AND scope_type=?"; params.append(scope_type)
        if status:
            sql += " AND status=?"; params.append(status)
        if profile:
            sql += " AND (profile IS NULL OR profile=?)"; params.append(profile)
        return [Permission.from_row(r) for r in self.db.query(sql + " ORDER BY id", tuple(params))]

    def find(self, scope_type: str, scope_value: str, profile: str | None = None) -> list[Permission]:
        value = scope_value if scope_type == "asset" else self._norm(scope_value)
        rows = self.db.query(
            "SELECT * FROM permissions WHERE scope_type=? AND scope_value=? AND (profile IS NULL OR profile=?)",
            (scope_type, value, profile))
        return [Permission.from_row(r) for r in rows]

    def history(self, pid: int) -> list[dict]:
        return self.db.query("SELECT * FROM permission_history WHERE permission_id=? ORDER BY id", (pid,))
